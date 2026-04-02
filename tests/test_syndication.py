"""Tests for source syndication detection and evidence deconfliction.

@decision DEC-SYNDICATION-001
@title Domain-based syndication clustering for evidence deconfliction
@status accepted
@rationale Multiple outlets syndicate AP/Reuters/AFP wire stories. When 10 outlets
publish the same AP story, the system sees 10 "independent" sources, inflating
confidence. Clustering by domain family detects this pattern. The cluster summary
is injected into technique prompts so analysts and LLMs can weight accordingly.
Wire service detection is based on a fixed set of known wire domains.

Tests cover:
1. extract_domain - URL normalization and edge cases
2. cluster_by_domain - grouping evidence items by source domain
3. detect_wire_service_items - AP/Reuters/AFP detection
4. build_syndication_summary - human-readable warning generation
5. EvidenceItem.source_urls - backward compatibility (empty default)
6. URL propagation from research claims through _build_items_from_research_result
"""

from __future__ import annotations

from sat.models.evidence import EvidenceItem
from sat.evidence.syndication import (
    extract_domain,
    cluster_by_domain,
    detect_wire_service_items,
    build_syndication_summary,
    WIRE_SERVICES,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_item(item_id: str, source_urls: list[str] | None = None) -> EvidenceItem:
    """Create a minimal EvidenceItem with optional source_urls."""
    return EvidenceItem(
        item_id=item_id,
        claim=f"Claim for {item_id}",
        source="research",
        source_urls=source_urls or [],
    )


# ---------------------------------------------------------------------------
# 1. extract_domain
# ---------------------------------------------------------------------------

class TestExtractDomain:
    def test_simple_url(self):
        assert extract_domain("https://apnews.com/article/123") == "apnews.com"

    def test_strips_www_prefix(self):
        assert extract_domain("https://www.reuters.com/world/story") == "reuters.com"

    def test_subdomain_other_than_www_preserved(self):
        # Subdomains like news.bbc.co.uk are not stripped (only www. is)
        result = extract_domain("https://news.bbc.co.uk/story")
        assert result == "news.bbc.co.uk"

    def test_http_scheme(self):
        assert extract_domain("http://afp.com/en/news") == "afp.com"

    def test_url_with_path_and_query(self):
        assert extract_domain("https://nytimes.com/2024/01/01/article.html?ref=rss") == "nytimes.com"

    def test_empty_string_returns_empty(self):
        assert extract_domain("") == ""

    def test_malformed_url_returns_empty_or_input(self):
        # urlparse on bare strings: hostname is None, so returns ""
        result = extract_domain("not-a-url")
        assert isinstance(result, str)

    def test_url_with_port(self):
        result = extract_domain("https://example.com:8080/path")
        assert result == "example.com"


# ---------------------------------------------------------------------------
# 2. cluster_by_domain
# ---------------------------------------------------------------------------

class TestClusterByDomain:
    def test_single_item_per_domain_excluded(self):
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/story1"]),
            make_item("R-C2", source_urls=["https://reuters.com/story1"]),
        ]
        clusters = cluster_by_domain(items)
        # Each domain appears only once — should not be in result
        assert clusters == {}

    def test_two_items_same_domain_clustered(self):
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/story1"]),
            make_item("R-C2", source_urls=["https://apnews.com/story2"]),
        ]
        clusters = cluster_by_domain(items)
        assert "apnews.com" in clusters
        assert set(clusters["apnews.com"]) == {"R-C1", "R-C2"}

    def test_three_items_same_domain(self):
        items = [
            make_item("R-C1", source_urls=["https://nytimes.com/a"]),
            make_item("R-C2", source_urls=["https://nytimes.com/b"]),
            make_item("R-C3", source_urls=["https://nytimes.com/c"]),
        ]
        clusters = cluster_by_domain(items)
        assert "nytimes.com" in clusters
        assert len(clusters["nytimes.com"]) == 3

    def test_items_with_no_source_urls_ignored(self):
        items = [
            make_item("R-C1"),  # no source_urls
            make_item("R-C2"),
        ]
        clusters = cluster_by_domain(items)
        assert clusters == {}

    def test_item_with_multiple_urls_same_domain(self):
        """Item with two URLs from same domain: item_id appears in cluster."""
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/a", "https://apnews.com/b"]),
            make_item("R-C2", source_urls=["https://apnews.com/c"]),
        ]
        clusters = cluster_by_domain(items)
        assert "apnews.com" in clusters
        assert "R-C2" in clusters["apnews.com"]

    def test_www_and_non_www_same_domain(self):
        """www.apnews.com and apnews.com should cluster together."""
        items = [
            make_item("R-C1", source_urls=["https://www.apnews.com/story1"]),
            make_item("R-C2", source_urls=["https://apnews.com/story2"]),
        ]
        clusters = cluster_by_domain(items)
        assert "apnews.com" in clusters
        assert set(clusters["apnews.com"]) == {"R-C1", "R-C2"}

    def test_mixed_domains(self):
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/story1"]),
            make_item("R-C2", source_urls=["https://apnews.com/story2"]),
            make_item("R-C3", source_urls=["https://reuters.com/story1"]),
        ]
        clusters = cluster_by_domain(items)
        assert "apnews.com" in clusters
        assert "reuters.com" not in clusters  # Only 1 item

    def test_empty_items_list(self):
        assert cluster_by_domain([]) == {}


# ---------------------------------------------------------------------------
# 3. detect_wire_service_items
# ---------------------------------------------------------------------------

class TestDetectWireServiceItems:
    def test_ap_news_detected(self):
        items = [make_item("R-C1", source_urls=["https://apnews.com/article/123"])]
        result = detect_wire_service_items(items)
        assert "R-C1" in result

    def test_ap_org_detected(self):
        items = [make_item("R-C1", source_urls=["https://ap.org/story"])]
        result = detect_wire_service_items(items)
        assert "R-C1" in result

    def test_reuters_detected(self):
        items = [make_item("R-C1", source_urls=["https://reuters.com/world/story"])]
        result = detect_wire_service_items(items)
        assert "R-C1" in result

    def test_afp_detected(self):
        items = [make_item("R-C1", source_urls=["https://afp.com/en/news"])]
        result = detect_wire_service_items(items)
        assert "R-C1" in result

    def test_non_wire_service_not_detected(self):
        items = [make_item("R-C1", source_urls=["https://nytimes.com/story"])]
        result = detect_wire_service_items(items)
        assert result == []

    def test_no_source_urls_not_detected(self):
        items = [make_item("R-C1")]
        result = detect_wire_service_items(items)
        assert result == []

    def test_item_not_duplicated_with_multiple_wire_urls(self):
        """An item with two wire service URLs should appear only once."""
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/a", "https://reuters.com/b"])
        ]
        result = detect_wire_service_items(items)
        assert result.count("R-C1") == 1

    def test_mixed_items(self):
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/story"]),
            make_item("R-C2", source_urls=["https://nytimes.com/story"]),
            make_item("R-C3", source_urls=["https://reuters.com/story"]),
        ]
        result = detect_wire_service_items(items)
        assert set(result) == {"R-C1", "R-C3"}

    def test_empty_items(self):
        assert detect_wire_service_items([]) == []

    def test_wire_services_set_contains_expected_domains(self):
        """Sanity check that the constant covers the four major wire services."""
        assert "apnews.com" in WIRE_SERVICES
        assert "reuters.com" in WIRE_SERVICES
        assert "afp.com" in WIRE_SERVICES
        assert "ap.org" in WIRE_SERVICES


# ---------------------------------------------------------------------------
# 4. build_syndication_summary
# ---------------------------------------------------------------------------

class TestBuildSyndicationSummary:
    def test_empty_items_returns_empty_string(self):
        assert build_syndication_summary([]) == ""

    def test_no_syndication_returns_empty_string(self):
        items = [
            make_item("R-C1", source_urls=["https://nytimes.com/a"]),
            make_item("R-C2", source_urls=["https://bbc.co.uk/b"]),
        ]
        result = build_syndication_summary(items)
        assert result == ""

    def test_wire_service_triggers_warning(self):
        items = [make_item("R-C1", source_urls=["https://apnews.com/story"])]
        result = build_syndication_summary(items)
        assert "SYNDICATION WARNING" in result
        assert "wire" in result.lower()

    def test_wire_service_count_in_warning(self):
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/a"]),
            make_item("R-C2", source_urls=["https://reuters.com/b"]),
        ]
        result = build_syndication_summary(items)
        assert "2" in result

    def test_domain_cluster_3plus_items_shown(self):
        """Clusters of 3+ items from same domain should be listed."""
        items = [
            make_item("R-C1", source_urls=["https://localgazette.com/a"]),
            make_item("R-C2", source_urls=["https://localgazette.com/b"]),
            make_item("R-C3", source_urls=["https://localgazette.com/c"]),
        ]
        result = build_syndication_summary(items)
        assert "localgazette.com" in result

    def test_domain_cluster_2_items_not_shown_in_domain_list(self):
        """Two-item clusters with no wire service produce empty string."""
        items = [
            make_item("R-C1", source_urls=["https://smallpaper.com/a"]),
            make_item("R-C2", source_urls=["https://smallpaper.com/b"]),
        ]
        result = build_syndication_summary(items)
        # 2 items: cluster exists but multi_domain threshold is 3+
        # No wire service -> empty string
        assert result == ""

    def test_returns_string_type(self):
        result = build_syndication_summary([make_item("R-C1")])
        assert isinstance(result, str)

    def test_combined_wire_and_domain_cluster(self):
        items = [
            make_item("R-C1", source_urls=["https://apnews.com/a"]),
            make_item("R-C2", source_urls=["https://nytimes.com/a"]),
            make_item("R-C3", source_urls=["https://nytimes.com/b"]),
            make_item("R-C4", source_urls=["https://nytimes.com/c"]),
        ]
        result = build_syndication_summary(items)
        assert "SYNDICATION WARNING" in result
        assert "nytimes.com" in result


# ---------------------------------------------------------------------------
# 5. EvidenceItem.source_urls backward compatibility
# ---------------------------------------------------------------------------

class TestEvidenceItemSourceUrls:
    def test_source_urls_defaults_to_empty_list(self):
        """EvidenceItem should default source_urls to [] — backward compatible."""
        item = EvidenceItem(
            item_id="R-C1",
            claim="Test claim",
            source="research",
        )
        assert item.source_urls == []

    def test_source_urls_can_be_populated(self):
        item = EvidenceItem(
            item_id="R-C1",
            claim="Test claim",
            source="research",
            source_urls=["https://example.com/a", "https://example.com/b"],
        )
        assert len(item.source_urls) == 2
        assert "https://example.com/a" in item.source_urls

    def test_existing_evidence_item_construction_unaffected(self):
        """The full set of existing EvidenceItem fields still works with source_urls."""
        item = EvidenceItem(
            item_id="D-F1",
            claim="GDP grew 2.3% in Q3",
            source="decomposition",
            source_ids=["S1", "S2"],
            category="fact",
            confidence="High",
            entities=["GDP", "Q3"],
            verified=True,
            selected=True,
            provider_name=None,
            source_urls=["https://treasury.gov/report"],
        )
        assert item.item_id == "D-F1"
        assert item.source_urls == ["https://treasury.gov/report"]

    def test_model_serialization_includes_source_urls(self):
        item = EvidenceItem(
            item_id="R-C1",
            claim="Test",
            source="research",
            source_urls=["https://apnews.com/story"],
        )
        dumped = item.model_dump()
        assert "source_urls" in dumped
        assert dumped["source_urls"] == ["https://apnews.com/story"]

    def test_model_copy_preserves_source_urls(self):
        item = EvidenceItem(
            item_id="R-C1",
            claim="Test",
            source="research",
            source_urls=["https://apnews.com/story"],
        )
        copied = item.model_copy(update={"claim": "Updated claim"})
        assert copied.source_urls == ["https://apnews.com/story"]


# ---------------------------------------------------------------------------
# 6. URL propagation: _build_items_from_research_result creates items with source_urls
# ---------------------------------------------------------------------------

class TestUrlPropagationInGatherer:
    """Test that _build_items_from_research_result populates source_urls on EvidenceItems.

    Production sequence:
      ResearchResult (with claims + sources) -> EvidenceItems (with source_urls)
    """

    def _make_research_result(self):
        from sat.models.research import ResearchResult, ResearchSource, ResearchClaim

        sources = [
            ResearchSource(
                id="S1",
                title="AP Report",
                url="https://apnews.com/story/abc",
                source_type="news",
                reliability_assessment="High",
            ),
            ResearchSource(
                id="S2",
                title="Reuters Report",
                url="https://reuters.com/story/xyz",
                source_type="news",
                reliability_assessment="High",
            ),
            ResearchSource(
                id="S3",
                title="Internal Report",
                url=None,  # URL-less source
                source_type="government",
                reliability_assessment="High",
            ),
        ]
        claims = [
            ResearchClaim(
                claim="Claim one from AP and Reuters",
                source_ids=["S1", "S2"],
                confidence="High",
                category="fact",
            ),
            ResearchClaim(
                claim="Claim two from internal source only",
                source_ids=["S3"],
                confidence="Medium",
                category="analysis",
            ),
            ResearchClaim(
                claim="Claim three from AP only",
                source_ids=["S1"],
                confidence="High",
                category="fact",
            ),
        ]
        return ResearchResult(
            technique_id="research",
            technique_name="Deep Research",
            summary="Test research result",
            query="test query",
            sources=sources,
            claims=claims,
            formatted_evidence="Evidence text",
            research_provider="perplexity",
            gaps_identified=[],
        )

    def test_items_get_source_urls_from_research_result(self):
        """EvidenceItems from research claims must have source_urls from ResearchSource.url."""
        from sat.evidence.gatherer import _build_items_from_research_result

        research_result = self._make_research_result()
        items = _build_items_from_research_result(research_result)

        # First claim: S1 and S2 both have URLs
        item1 = items[0]
        assert "https://apnews.com/story/abc" in item1.source_urls
        assert "https://reuters.com/story/xyz" in item1.source_urls

    def test_url_less_sources_do_not_add_empty_strings(self):
        """Sources without URLs should not contribute empty strings to source_urls."""
        from sat.evidence.gatherer import _build_items_from_research_result

        research_result = self._make_research_result()
        items = _build_items_from_research_result(research_result)

        # Second claim: only S3 which has url=None
        item2 = items[1]
        assert item2.source_urls == []

    def test_third_claim_has_ap_url_only(self):
        """Third claim references only S1 (AP) — should have only AP URL."""
        from sat.evidence.gatherer import _build_items_from_research_result

        research_result = self._make_research_result()
        items = _build_items_from_research_result(research_result)

        item3 = items[2]
        assert item3.source_urls == ["https://apnews.com/story/abc"]

    def test_missing_source_ids_handled_gracefully(self):
        """Claims referencing unknown source IDs produce items with empty source_urls."""
        from sat.evidence.gatherer import _build_items_from_research_result
        from sat.models.research import ResearchResult, ResearchClaim

        result = ResearchResult(
            technique_id="research",
            technique_name="Research",
            summary="Test",
            query="test",
            sources=[],  # No sources
            claims=[
                ResearchClaim(
                    claim="Orphan claim",
                    source_ids=["S99"],  # Unknown source
                    confidence="Low",
                    category="fact",
                )
            ],
            formatted_evidence="",
            research_provider="perplexity",
            gaps_identified=[],
        )
        items = _build_items_from_research_result(result)
        assert items[0].source_urls == []
