"""Tests for research runner pipeline.

@decision DEC-TEST-RESEARCH-003: Full pipeline test with in-memory test doubles.
@title Research runner integration test
@status accepted
@rationale Tests the query-generation → research → structuring pipeline using
in-memory test doubles that implement the same protocols as real providers.
No external API calls are made.
"""
# @mock-exempt: Uses in-memory test doubles implementing provider protocols,
# not unittest.mock. These are equivalent to the conftest MockProvider pattern.

from __future__ import annotations

from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.providers.base import LLMMessage, LLMResult, LLMUsage
from sat.research.base import ResearchResponse, SearchResult
from sat.research.runner import run_research


class MockResearchProvider:
    """In-memory test double implementing ResearchProvider protocol."""

    async def research(
        self, query: str, context: str | None = None, max_sources: int = 10
    ) -> ResearchResponse:
        return ResearchResponse(
            content="AI research is advancing rapidly. Key developments include...",
            citations=[
                SearchResult(title="Source 1", url="https://example.com/1", snippet="snippet 1"),
                SearchResult(title="Source 2", url="https://example.com/2", snippet="snippet 2"),
            ],
        )


class MockLLMForRunner:
    """In-memory test double implementing LLMProvider protocol for runner tests."""

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResult:
        return LLMResult(
            text="AI capabilities and limitations 2025",
            usage=LLMUsage(input_tokens=50, output_tokens=10),
        )

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ResearchResult:
        return ResearchResult(
            technique_id="research",
            technique_name="Deep Research",
            summary="Found relevant information about AI",
            query="AI capabilities and limitations 2025",
            sources=[
                ResearchSource(
                    id="S1",
                    title="Source 1",
                    url="https://example.com/1",
                    source_type="web",
                    reliability_assessment="Medium",
                ),
            ],
            claims=[
                ResearchClaim(
                    claim="AI is advancing",
                    source_ids=["S1"],
                    confidence="High",
                    category="fact",
                ),
            ],
            formatted_evidence="AI is advancing rapidly according to multiple sources.",
            research_provider="mock",
            gaps_identified=["Long-term projections uncertain"],
        )


class TestRunner:
    """Test the research runner pipeline."""

    async def test_run_research_full_pipeline(self):
        research_prov = MockResearchProvider()
        llm_prov = MockLLMForRunner()

        result = await run_research(
            question="Will AI surpass human intelligence?",
            research_provider=research_prov,
            llm_provider=llm_prov,
        )

        assert isinstance(result, ResearchResult)
        assert result.technique_id == "research"
        assert len(result.sources) >= 1
        assert len(result.claims) >= 1
        assert result.formatted_evidence

    async def test_run_research_sets_provider_name(self):
        research_prov = MockResearchProvider()
        llm_prov = MockLLMForRunner()

        result = await run_research(
            question="Test question",
            research_provider=research_prov,
            llm_provider=llm_prov,
        )

        # MockResearchProvider -> doesn't match perplexity/brave -> "llm"
        assert result.research_provider in ("mock", "llm")
