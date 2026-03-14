"""Tests for research data models.

@decision DEC-TEST-RESEARCH-001: Validate research model serialization and schema generation.
@title Research model unit tests
@status accepted
@rationale Ensures ResearchResult, ResearchSource, and ResearchClaim serialize correctly
and produce valid JSON schemas for LLM structured output. Round-trip test confirms
Pydantic validation works end-to-end.
"""

from __future__ import annotations

from sat.models.research import ResearchClaim, ResearchResult, ResearchSource


class TestResearchModels:
    """Test research model serialization and validation."""

    def test_research_source_serialization(self):
        source = ResearchSource(
            id="S1",
            title="Test Source",
            url="https://example.com",
            source_type="web",
            reliability_assessment="High",
        )
        data = source.model_dump()
        assert data["id"] == "S1"
        assert data["title"] == "Test Source"
        assert data["url"] == "https://example.com"
        assert data["source_type"] == "web"

    def test_research_claim_serialization(self):
        claim = ResearchClaim(
            claim="Test claim",
            source_ids=["S1", "S2"],
            confidence="High",
            category="fact",
        )
        data = claim.model_dump()
        assert data["claim"] == "Test claim"
        assert data["source_ids"] == ["S1", "S2"]

    def test_research_result_roundtrip(self):
        result = ResearchResult(
            technique_id="research",
            technique_name="Deep Research",
            summary="Found 3 sources",
            query="test query",
            sources=[
                ResearchSource(
                    id="S1",
                    title="Source 1",
                    source_type="web",
                    reliability_assessment="High",
                ),
            ],
            claims=[
                ResearchClaim(
                    claim="A fact",
                    source_ids=["S1"],
                    confidence="High",
                    category="fact",
                ),
            ],
            formatted_evidence="Evidence text here",
            research_provider="perplexity",
            gaps_identified=["Missing data on X"],
        )
        json_str = result.model_dump_json()
        restored = ResearchResult.model_validate_json(json_str)
        assert restored.query == "test query"
        assert len(restored.sources) == 1
        assert len(restored.claims) == 1
        assert restored.formatted_evidence == "Evidence text here"

    def test_research_result_json_schema(self):
        schema = ResearchResult.model_json_schema()
        assert "properties" in schema
        assert "query" in schema["properties"]
        assert "sources" in schema["properties"]
        assert "claims" in schema["properties"]
        assert "formatted_evidence" in schema["properties"]

    def test_research_source_optional_url(self):
        source = ResearchSource(
            id="S1",
            title="No URL",
            source_type="academic",
            reliability_assessment="Medium",
        )
        assert source.url is None
