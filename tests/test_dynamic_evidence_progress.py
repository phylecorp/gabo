"""Tests for the dynamic evidence gathering progress events.

@decision DEC-TEST-EVIDENCE-PROGRESS-001
@title Tests for ProviderStarted and decomposition stage events
@status accepted
@rationale These tests verify that:
- multi_runner.py emits ProviderStarted for each provider before parallel dispatch
- gatherer.py emits StageStarted/StageCompleted around the decomposition step
These are the two backend gaps that caused provider dots to stay gray and
decomposition to have no progress feedback.
"""
# @mock-exempt: discover_providers patches env-dependent API key loading (external boundary).
# decompose_evidence patches an external LLM API call — same boundary pattern as
# test_multi_runner.py. Test doubles implement the ResearchProvider protocol, not
# unittest.mock.MagicMock.

from __future__ import annotations

from unittest.mock import patch

import pytest

from sat.events import (
    EventBus,
    PipelineEvent,
    ProviderCompleted,
    ProviderFailed,
    ProviderStarted,
    ResearchStarted,
    StageCompleted,
    StageStarted,
)
from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.providers.base import LLMMessage, LLMResult, LLMUsage
from sat.research.base import ResearchResponse, SearchResult
from sat.research.multi_runner import run_multi_research


# ---------------------------------------------------------------------------
# In-memory test doubles (implement real protocols, no unittest.mock)
# ---------------------------------------------------------------------------


class MockResearchProvider:
    """In-memory test double implementing ResearchProvider protocol."""

    def __init__(self, name: str, fail: bool = False):
        self.name = name
        self.fail = fail

    async def research(
        self, query: str, context: str | None = None, max_sources: int = 10
    ) -> ResearchResponse:
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return ResearchResponse(
            content=f"{self.name} research content",
            citations=[
                SearchResult(
                    title=f"{self.name} Source 1",
                    url=f"https://example.com/{self.name}/1",
                    snippet=f"{self.name} snippet 1",
                ),
            ],
        )


class MockLLMProvider:
    """In-memory test double implementing LLMProvider protocol."""

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResult:
        return LLMResult(
            text="optimized search query",
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
            summary="Multi-provider research summary",
            query="optimized search query",
            sources=[
                ResearchSource(
                    id="S1",
                    title="Test Source",
                    url="https://example.com/1",
                    source_type="web",
                    reliability_assessment="High",
                ),
            ],
            claims=[
                ResearchClaim(
                    claim="Test claim",
                    source_ids=["S1"],
                    confidence="High",
                    category="fact",
                ),
            ],
            formatted_evidence="Formatted evidence from multiple providers",
            research_provider="multi(test)",
            gaps_identified=[],
        )


# ---------------------------------------------------------------------------
# Tests: ProviderStarted events in multi_runner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_started_emitted_before_research():
    """ProviderStarted must be emitted for each provider before parallel research."""
    providers = [
        ("provider_a", MockResearchProvider("provider_a")),
        ("provider_b", MockResearchProvider("provider_b")),
    ]
    mock_llm = MockLLMProvider()
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    with patch("sat.research.multi_runner.discover_providers", return_value=providers):
        await run_multi_research(
            question="Test question",
            llm_provider=mock_llm,
            max_sources=10,
            events=bus,
        )

    provider_started_names = [e.name for e in captured if isinstance(e, ProviderStarted)]
    assert "provider_a" in provider_started_names, (
        "ProviderStarted(name='provider_a') was not emitted"
    )
    assert "provider_b" in provider_started_names, (
        "ProviderStarted(name='provider_b') was not emitted"
    )


@pytest.mark.asyncio
async def test_provider_started_emitted_before_provider_completed():
    """ProviderStarted must appear before ProviderCompleted for the same provider."""
    providers = [("alpha", MockResearchProvider("alpha"))]
    mock_llm = MockLLMProvider()
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    with patch("sat.research.multi_runner.discover_providers", return_value=providers):
        await run_multi_research(
            question="Test question",
            llm_provider=mock_llm,
            max_sources=10,
            events=bus,
        )

    started_idx = next(
        (i for i, e in enumerate(captured) if isinstance(e, ProviderStarted) and e.name == "alpha"),
        None,
    )
    completed_idx = next(
        (
            i
            for i, e in enumerate(captured)
            if isinstance(e, ProviderCompleted) and e.name == "alpha"
        ),
        None,
    )
    assert started_idx is not None, "ProviderStarted(alpha) not found"
    assert completed_idx is not None, "ProviderCompleted(alpha) not found"
    assert started_idx < completed_idx, (
        f"ProviderStarted(idx={started_idx}) should precede "
        f"ProviderCompleted(idx={completed_idx})"
    )


@pytest.mark.asyncio
async def test_provider_started_emitted_even_when_provider_fails():
    """ProviderStarted must be emitted even for providers that subsequently fail."""
    providers = [
        ("bad_provider", MockResearchProvider("bad_provider", fail=True)),
        ("good_provider", MockResearchProvider("good_provider")),
    ]
    mock_llm = MockLLMProvider()
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    with patch("sat.research.multi_runner.discover_providers", return_value=providers):
        await run_multi_research(
            question="Test question",
            llm_provider=mock_llm,
            max_sources=10,
            events=bus,
        )

    provider_started_names = [e.name for e in captured if isinstance(e, ProviderStarted)]
    assert "bad_provider" in provider_started_names, (
        "ProviderStarted should be emitted even for providers that fail"
    )
    failed_names = [e.name for e in captured if isinstance(e, ProviderFailed)]
    assert "bad_provider" in failed_names


@pytest.mark.asyncio
async def test_research_started_emitted_before_provider_started():
    """ResearchStarted should appear before any ProviderStarted."""
    providers = [("p1", MockResearchProvider("p1"))]
    mock_llm = MockLLMProvider()
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    with patch("sat.research.multi_runner.discover_providers", return_value=providers):
        await run_multi_research(
            question="Test question",
            llm_provider=mock_llm,
            max_sources=10,
            events=bus,
        )

    research_started_idx = next(
        (i for i, e in enumerate(captured) if isinstance(e, ResearchStarted)), None
    )
    first_provider_started_idx = next(
        (i for i, e in enumerate(captured) if isinstance(e, ProviderStarted)), None
    )
    assert research_started_idx is not None, "ResearchStarted not emitted"
    assert first_provider_started_idx is not None, "ProviderStarted not emitted"
    assert research_started_idx < first_provider_started_idx, (
        "ResearchStarted must precede ProviderStarted"
    )


# ---------------------------------------------------------------------------
# Tests: StageStarted / StageCompleted in gatherer decomposition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decomposition_stage_events_emitted():
    """gather_evidence emits StageStarted/StageCompleted for decomposition."""
    from tests.helpers import MockProvider
    from sat.config import DecompositionConfig, ResearchConfig
    from sat.evidence.gatherer import gather_evidence
    from sat.models.decomposition import AtomicFact, DecompositionResult

    provider = MockProvider(text_response="{}")
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    decomp_result = DecompositionResult(
        facts=[
            AtomicFact(
                fact_id="F1",
                claim="Test fact.",
                source_ids=["1"],
                confidence="High",
                category="fact",
                entities=[],
            )
        ],
        original_text="Test evidence.",
        technique_id="decomposition",
        technique_name="Decomposition",
        summary="Test summary",
    )

    # @mock-exempt: decompose_evidence calls an external LLM API.
    # Patched at the source module because gatherer imports it lazily inside the function.
    with patch("sat.decomposition.decompose_evidence", return_value=decomp_result):
        await gather_evidence(
            question="What happened?",
            evidence="Test evidence.",
            research_config=ResearchConfig(enabled=False),
            decomposition_config=DecompositionConfig(enabled=True),
            provider=provider,
            events=bus,
        )

    stage_started = [
        e for e in captured if isinstance(e, StageStarted) and e.stage == "decomposition"
    ]
    stage_completed = [
        e for e in captured if isinstance(e, StageCompleted) and e.stage == "decomposition"
    ]

    assert len(stage_started) == 1, (
        f"Expected 1 StageStarted(decomposition), got {len(stage_started)}"
    )
    assert len(stage_completed) == 1, (
        f"Expected 1 StageCompleted(decomposition), got {len(stage_completed)}"
    )


@pytest.mark.asyncio
async def test_decomposition_stage_events_not_emitted_when_disabled():
    """No StageStarted/StageCompleted for decomposition when decomposition is off."""
    from tests.helpers import MockProvider
    from sat.config import DecompositionConfig, ResearchConfig
    from sat.evidence.gatherer import gather_evidence

    provider = MockProvider(text_response="{}")
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    await gather_evidence(
        question="What happened?",
        evidence="Some evidence text.",
        research_config=ResearchConfig(enabled=False),
        decomposition_config=DecompositionConfig(enabled=False),
        provider=provider,
        events=bus,
    )

    decomp_stage_events = [
        e
        for e in captured
        if isinstance(e, (StageStarted, StageCompleted))
        and getattr(e, "stage", "") == "decomposition"
    ]
    assert len(decomp_stage_events) == 0, (
        "Decomposition stage events should not be emitted when decomposition is disabled"
    )


@pytest.mark.asyncio
async def test_decomposition_stage_started_before_completed():
    """StageStarted(decomposition) must precede StageCompleted(decomposition)."""
    from tests.helpers import MockProvider
    from sat.config import DecompositionConfig, ResearchConfig
    from sat.evidence.gatherer import gather_evidence
    from sat.models.decomposition import DecompositionResult

    provider = MockProvider(text_response="{}")
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    decomp_result = DecompositionResult(
        facts=[],
        original_text="Evidence.",
        technique_id="decomposition",
        technique_name="Decomposition",
        summary="Empty decomposition.",
    )

    # @mock-exempt: decompose_evidence calls an external LLM API.
    # Patched at the source module because gatherer imports it lazily inside the function.
    with patch("sat.decomposition.decompose_evidence", return_value=decomp_result):
        await gather_evidence(
            question="Test?",
            evidence="Evidence.",
            research_config=ResearchConfig(enabled=False),
            decomposition_config=DecompositionConfig(enabled=True),
            provider=provider,
            events=bus,
        )

    started_idx = next(
        (
            i
            for i, e in enumerate(captured)
            if isinstance(e, StageStarted) and e.stage == "decomposition"
        ),
        None,
    )
    completed_idx = next(
        (
            i
            for i, e in enumerate(captured)
            if isinstance(e, StageCompleted) and e.stage == "decomposition"
        ),
        None,
    )
    assert started_idx is not None, "StageStarted(decomposition) not emitted"
    assert completed_idx is not None, "StageCompleted(decomposition) not emitted"
    assert started_idx < completed_idx
