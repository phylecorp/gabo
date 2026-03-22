"""Tests for multi-provider research runner.

@decision DEC-TEST-RESEARCH-011: Multi-runner tests with in-memory test doubles.
@title Multi-provider research orchestration tests
@status accepted
@rationale Tests discovery, parallel execution, merge logic, and graceful degradation
using in-memory test doubles. Env vars are mocked at the boundary to control provider
availability. The core logic (merge, parallel gather, fallback) is tested directly.
"""
# @mock-exempt: Must mock os.environ to control which providers are "available".
# Provider test doubles implement the real protocol, not unittest.mock.

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sat.errors import is_transient_error
from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.providers.base import LLMMessage, LLMResult, LLMUsage
from sat.research.base import ResearchResponse, SearchResult
from sat.research.multi_runner import (
    _RESEARCH_EXTRA_TRANSIENT,
    discover_providers,
    merge_responses,
    run_multi_research,
)


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
                SearchResult(
                    title=f"{self.name} Source 2",
                    url=f"https://example.com/{self.name}/2",
                    snippet=f"{self.name} snippet 2",
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


def _no_config_file(tmp_path: Path) -> Path:
    """Return a path to a non-existent config file for test isolation."""
    return tmp_path / "no_config.json"


class TestDiscoverProviders:
    """Test provider discovery logic.

    Each test patches both os.environ (clear=True) AND the config file path
    to a non-existent file so that neither source leaks keys from the real
    developer environment.
    """

    def test_discover_providers_finds_available(self, tmp_path):
        """Should discover all providers when all API keys are set."""
        no_cfg = _no_config_file(tmp_path)
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "test-openai",
                "PERPLEXITY_API_KEY": "test-perplexity",
                "GEMINI_API_KEY": "test-gemini",
            },
            clear=True,
        ):
            with patch("sat.config._get_sat_config_path", return_value=no_cfg):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "openai_deep" in names
        assert "perplexity" in names
        assert "gemini_deep" in names
        assert len(providers) == 3

    def test_discover_providers_skips_missing_keys(self, tmp_path):
        """Should only discover providers with valid API keys."""
        no_cfg = _no_config_file(tmp_path)
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "test-openai"},
            clear=True,
        ):
            with patch("sat.config._get_sat_config_path", return_value=no_cfg):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "openai_deep" in names
        assert "perplexity" not in names
        assert "gemini_deep" not in names
        assert len(providers) == 1

    def test_discover_providers_includes_brave_alone(self, tmp_path):
        """Should include Brave when only Brave API key is set (no deep providers)."""
        no_cfg = _no_config_file(tmp_path)
        with patch.dict(
            "os.environ",
            {"BRAVE_API_KEY": "test-brave"},
            clear=True,
        ):
            with patch("sat.config._get_sat_config_path", return_value=no_cfg):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "brave" in names
        assert len(providers) == 1

    def test_discover_providers_includes_brave_alongside_deep(self, tmp_path):
        """Should include Brave alongside deep research providers when all keys are set."""
        no_cfg = _no_config_file(tmp_path)
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "test-openai",
                "BRAVE_API_KEY": "test-brave",
            },
            clear=True,
        ):
            with patch("sat.config._get_sat_config_path", return_value=no_cfg):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "openai_deep" in names
        assert "brave" in names
        assert len(providers) == 2

    def test_discover_providers_falls_back_to_llm(self, tmp_path):
        """Should fall back to LLM if no other providers available."""
        no_cfg = _no_config_file(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=no_cfg):
                mock_llm = MockLLMProvider()
                providers = discover_providers(llm_provider=mock_llm)
        names = [name for name, _ in providers]
        assert "llm" in names
        assert len(providers) == 1

    def test_discover_providers_returns_empty_when_nothing(self, tmp_path):
        """Should return empty list when no providers available."""
        no_cfg = _no_config_file(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=no_cfg):
                providers = discover_providers(llm_provider=None)
        assert providers == []


class TestDiscoverProvidersConfigFile:
    """Test that discover_providers reads API keys from ~/.sat/config.json.

    This covers the bug where research providers only checked os.environ,
    not the config file populated by the Settings UI.
    """

    def _make_config(self, tmp_path: Path, entries: dict) -> Path:
        """Write a minimal config.json with the given provider entries."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"providers": entries}))
        return config_file

    def test_openai_key_from_config_file(self, tmp_path):
        """OpenAI deep research provider discovered via config file key."""
        config_file = self._make_config(
            tmp_path, {"openai": {"api_key": "cfg-openai-key", "default_model": ""}}
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "openai_deep" in names

    def test_perplexity_key_from_config_file(self, tmp_path):
        """Perplexity provider discovered via config file key."""
        config_file = self._make_config(
            tmp_path, {"perplexity": {"api_key": "cfg-perplexity-key", "default_model": ""}}
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "perplexity" in names

    def test_gemini_key_from_config_file(self, tmp_path):
        """Gemini deep research provider discovered via config file key."""
        config_file = self._make_config(
            tmp_path, {"gemini": {"api_key": "cfg-gemini-key", "default_model": ""}}
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "gemini_deep" in names

    def test_brave_key_from_config_file(self, tmp_path):
        """Brave provider discovered via config file key."""
        config_file = self._make_config(
            tmp_path, {"brave": {"api_key": "cfg-brave-key", "default_model": ""}}
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "brave" in names

    def test_env_var_takes_precedence_over_config(self, tmp_path):
        """When both env var and config file have a key, env var is used (both work)."""
        config_file = self._make_config(
            tmp_path, {"openai": {"api_key": "cfg-openai-key", "default_model": ""}}
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-openai-key"}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "openai_deep" in names

    def test_all_providers_from_config_file(self, tmp_path):
        """All four providers discovered when all keys are in config file."""
        config_file = self._make_config(
            tmp_path,
            {
                "openai": {"api_key": "cfg-openai", "default_model": ""},
                "perplexity": {"api_key": "cfg-perplexity", "default_model": ""},
                "gemini": {"api_key": "cfg-gemini", "default_model": ""},
                "brave": {"api_key": "cfg-brave", "default_model": ""},
            },
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "openai_deep" in names
        assert "perplexity" in names
        assert "gemini_deep" in names
        assert "brave" in names
        assert len(providers) == 4

    def test_missing_config_file_falls_back_to_no_providers(self, tmp_path):
        """No config file + no env vars = no providers (unchanged behavior)."""
        nonexistent = tmp_path / "does_not_exist.json"
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=nonexistent):
                providers = discover_providers(llm_provider=None)
        assert providers == []


class TestDiscoverProvidersModelWiring:
    """Test that discover_providers() passes research_model from config to constructors.

    Covers DEC-MODELS-003: discover_providers() explicitly passes
    model=_load_config_file_research_model(provider) to each deep research provider.
    This ensures the Settings UI model preference propagates through the multi-runner
    path without relying solely on each provider's internal resolve_research_model().
    """

    def _make_config(self, tmp_path: Path, entries: dict) -> Path:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"providers": entries}))
        return config_file

    def test_openai_model_from_config_passed_to_provider(self, tmp_path):
        """discover_providers() passes research_model from config file to OpenAI provider."""
        config_file = self._make_config(
            tmp_path,
            {"openai": {"api_key": "cfg-openai-key", "research_model": "o3-custom-research"}},
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        openai_providers = [p for name, p in providers if name == "openai_deep"]
        assert len(openai_providers) == 1
        assert openai_providers[0]._primary_model == "o3-custom-research"

    def test_perplexity_model_from_config_passed_to_provider(self, tmp_path):
        """discover_providers() passes research_model from config file to Perplexity provider."""
        config_file = self._make_config(
            tmp_path,
            {
                "perplexity": {
                    "api_key": "cfg-perplexity-key",
                    "research_model": "sonar-pro-custom",
                }
            },
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        pplx_providers = [p for name, p in providers if name == "perplexity"]
        assert len(pplx_providers) == 1
        assert pplx_providers[0]._model == "sonar-pro-custom"

    def test_gemini_model_from_config_passed_to_provider(self, tmp_path):
        """discover_providers() passes research_model from config file to Gemini provider."""
        config_file = self._make_config(
            tmp_path,
            {"gemini": {"api_key": "cfg-gemini-key", "research_model": "gemini-deep-custom"}},
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        gemini_providers = [p for name, p in providers if name == "gemini_deep"]
        assert len(gemini_providers) == 1
        assert gemini_providers[0]._agent == "gemini-deep-custom"

    def test_no_research_model_in_config_falls_back_to_default(self, tmp_path):
        """When config has no research_model, provider resolves via built-in default."""
        from sat.config import DEFAULT_RESEARCH_MODELS

        config_file = self._make_config(
            tmp_path, {"openai": {"api_key": "cfg-openai-key"}}
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        openai_providers = [p for name, p in providers if name == "openai_deep"]
        assert len(openai_providers) == 1
        assert openai_providers[0]._primary_model == DEFAULT_RESEARCH_MODELS["openai"]

    def test_env_var_used_when_no_research_model_in_config(self, tmp_path):
        """OPENAI_RESEARCH_MODEL env var used when config has no research_model field."""
        config_file = self._make_config(
            tmp_path, {"openai": {"api_key": "cfg-openai-key"}}
        )
        with patch.dict(
            "os.environ",
            {"OPENAI_RESEARCH_MODEL": "o4-env-override"},
            clear=True,
        ):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        openai_providers = [p for name, p in providers if name == "openai_deep"]
        assert len(openai_providers) == 1
        assert openai_providers[0]._primary_model == "o4-env-override"

    def test_config_model_overrides_env_var(self, tmp_path):
        """Config file research_model takes priority over env var in discover_providers()."""
        config_file = self._make_config(
            tmp_path,
            {"openai": {"api_key": "cfg-openai-key", "research_model": "o3-from-config"}},
        )
        with patch.dict(
            "os.environ",
            {"OPENAI_RESEARCH_MODEL": "o3-from-env"},
            clear=True,
        ):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        openai_providers = [p for name, p in providers if name == "openai_deep"]
        assert len(openai_providers) == 1
        assert openai_providers[0]._primary_model == "o3-from-config"

    def test_backward_compat_no_research_model_field(self, tmp_path):
        """Existing configs without research_model still produce working providers."""
        from sat.config import DEFAULT_RESEARCH_MODELS

        config_file = self._make_config(
            tmp_path,
            {
                "openai": {"api_key": "cfg-openai-key", "default_model": "o3"},
                "perplexity": {"api_key": "cfg-perplexity-key", "default_model": "sonar-pro"},
            },
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=config_file):
                providers = discover_providers()
        names = [name for name, _ in providers]
        assert "openai_deep" in names
        assert "perplexity" in names
        for name, prov in providers:
            if name == "openai_deep":
                assert prov._primary_model == DEFAULT_RESEARCH_MODELS["openai"]
            elif name == "perplexity":
                assert prov._model == DEFAULT_RESEARCH_MODELS["perplexity"]


class TestMergeResponses:
    """Test response merging logic."""

    def test_merge_responses_combines_content(self):
        """Should combine content with provider-specific headers."""
        results = [
            (
                "provider1",
                ResearchResponse(
                    content="Content from provider 1",
                    citations=[
                        SearchResult(
                            title="Source 1",
                            url="https://example.com/1",
                            snippet="snippet 1",
                        ),
                    ],
                ),
            ),
            (
                "provider2",
                ResearchResponse(
                    content="Content from provider 2",
                    citations=[
                        SearchResult(
                            title="Source 2",
                            url="https://example.com/2",
                            snippet="snippet 2",
                        ),
                    ],
                ),
            ),
        ]

        merged = merge_responses(results)

        assert "## provider1 Research" in merged.content
        assert "Content from provider 1" in merged.content
        assert "## provider2 Research" in merged.content
        assert "Content from provider 2" in merged.content
        assert "---" in merged.content
        assert len(merged.citations) == 2

    def test_merge_responses_deduplicates_citations(self):
        """Should deduplicate citations by URL."""
        results = [
            (
                "provider1",
                ResearchResponse(
                    content="Content 1",
                    citations=[
                        SearchResult(
                            title="Source 1",
                            url="https://example.com/same",
                            snippet="snippet 1",
                        ),
                        SearchResult(
                            title="Source 2",
                            url="https://example.com/unique1",
                            snippet="snippet 2",
                        ),
                    ],
                ),
            ),
            (
                "provider2",
                ResearchResponse(
                    content="Content 2",
                    citations=[
                        SearchResult(
                            title="Source 1 (duplicate)",
                            url="https://example.com/same",
                            snippet="different snippet",
                        ),
                        SearchResult(
                            title="Source 3",
                            url="https://example.com/unique2",
                            snippet="snippet 3",
                        ),
                    ],
                ),
            ),
        ]

        merged = merge_responses(results)

        # Should have 3 unique citations (same URL is deduplicated)
        assert len(merged.citations) == 3
        urls = [c.url for c in merged.citations]
        assert "https://example.com/same" in urls
        assert "https://example.com/unique1" in urls
        assert "https://example.com/unique2" in urls


class TestRunMultiResearch:
    """Test the full multi-provider research pipeline."""

    async def test_run_multi_research_full_pipeline(self):
        """Should execute full pipeline with multiple providers."""
        mock_providers = [
            ("provider1", MockResearchProvider("provider1")),
            ("provider2", MockResearchProvider("provider2")),
        ]
        mock_llm = MockLLMProvider()

        with patch(
            "sat.research.multi_runner.discover_providers",
            return_value=mock_providers,
        ):
            result = await run_multi_research(
                question="Test question",
                llm_provider=mock_llm,
                max_sources=10,
            )

        assert isinstance(result, ResearchResult)
        assert result.technique_id == "research"
        assert len(result.sources) >= 1
        assert len(result.claims) >= 1
        assert result.formatted_evidence
        # Provider label should be multi(provider1,provider2) based on mock provider names
        assert result.research_provider.startswith("multi(")
        assert "provider1" in result.research_provider or "provider2" in result.research_provider

    async def test_run_multi_research_handles_provider_failure(self):
        """Should continue with remaining providers if one fails."""
        mock_providers = [
            ("provider1", MockResearchProvider("provider1", fail=True)),
            ("provider2", MockResearchProvider("provider2", fail=False)),
        ]
        mock_llm = MockLLMProvider()

        with patch(
            "sat.research.multi_runner.discover_providers",
            return_value=mock_providers,
        ):
            result = await run_multi_research(
                question="Test question",
                llm_provider=mock_llm,
                max_sources=10,
            )

        # Should still succeed with one working provider
        assert isinstance(result, ResearchResult)
        assert result.formatted_evidence

    async def test_run_multi_research_raises_when_all_fail(self):
        """Should raise RuntimeError when all providers fail."""
        mock_providers = [
            ("provider1", MockResearchProvider("provider1", fail=True)),
            ("provider2", MockResearchProvider("provider2", fail=True)),
        ]
        mock_llm = MockLLMProvider()

        with patch(
            "sat.research.multi_runner.discover_providers",
            return_value=mock_providers,
        ):
            with pytest.raises(RuntimeError, match="All research providers failed"):
                await run_multi_research(
                    question="Test question",
                    llm_provider=mock_llm,
                    max_sources=10,
                )

    async def test_run_multi_research_raises_when_no_providers(self):
        """Should raise ValueError when no providers available."""
        mock_llm = MockLLMProvider()

        with patch(
            "sat.research.multi_runner.discover_providers",
            return_value=[],
        ):
            with pytest.raises(ValueError, match="No research providers available"):
                await run_multi_research(
                    question="Test question",
                    llm_provider=mock_llm,
                    max_sources=10,
                )


class MockTransientProvider:
    """Test double that fails with transient errors N times, then succeeds."""

    def __init__(self, name: str, fail_count: int = 1):
        self.name = name
        self.fail_count = fail_count
        self.call_count = 0

    async def research(
        self, query: str, context: str | None = None, max_sources: int = 10
    ) -> ResearchResponse:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise TimeoutError(f"{self.name} timed out (attempt {self.call_count})")
        return ResearchResponse(
            content=f"{self.name} research content (after retry)",
            citations=[
                SearchResult(
                    title=f"{self.name} Source 1",
                    url=f"https://example.com/{self.name}/1",
                    snippet=f"{self.name} snippet 1",
                ),
            ],
        )


class TestIsResearchTransient:
    """Test the transient error classifier with research-specific extra names."""

    def test_timeout_error_is_transient(self):
        assert is_transient_error(TimeoutError("timed out"), _RESEARCH_EXTRA_TRANSIENT) is True

    def test_runtime_error_is_not_transient(self):
        assert is_transient_error(RuntimeError("bad"), _RESEARCH_EXTRA_TRANSIENT) is False

    def test_value_error_is_not_transient(self):
        assert is_transient_error(ValueError("invalid"), _RESEARCH_EXTRA_TRANSIENT) is False

    def test_class_name_matching_for_httpx_timeout(self):
        # Simulate httpx.TimeoutException via dynamic class
        FakeTimeout = type("TimeoutException", (Exception,), {})
        assert is_transient_error(FakeTimeout("timeout"), _RESEARCH_EXTRA_TRANSIENT) is True

    def test_class_name_matching_for_connect_error(self):
        FakeConnect = type("ConnectError", (Exception,), {})
        assert is_transient_error(FakeConnect("refused"), _RESEARCH_EXTRA_TRANSIENT) is True

    def test_class_name_matching_for_api_timeout(self):
        FakeAPITimeout = type("APITimeoutError", (Exception,), {})
        assert is_transient_error(FakeAPITimeout("api timeout"), _RESEARCH_EXTRA_TRANSIENT) is True

    def test_class_name_matching_for_rate_limit(self):
        FakeRateLimit = type("RateLimitError", (Exception,), {})
        assert is_transient_error(FakeRateLimit("rate limited"), _RESEARCH_EXTRA_TRANSIENT) is True

    def test_research_request_failed_is_transient(self):
        """ResearchRequestFailed should be classified as transient."""
        FakeRRF = type("ResearchRequestFailed", (RuntimeError,), {})
        assert is_transient_error(FakeRRF("request failed"), _RESEARCH_EXTRA_TRANSIENT) is True


class MockFailedRequestProvider:
    """Test double that raises ResearchRequestFailed-like error, then succeeds."""

    def __init__(self, name: str, fail_count: int = 1):
        self.name = name
        self.fail_count = fail_count
        self.call_count = 0

    async def research(
        self, query: str, context: str | None = None, max_sources: int = 10
    ) -> ResearchResponse:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            # Simulate the ResearchRequestFailed exception using dynamic class
            # (same pattern as the classifier uses — class-name matching)
            ResearchRequestFailed = type("ResearchRequestFailed", (RuntimeError,), {})
            raise ResearchRequestFailed(f"{self.name} request failed (attempt {self.call_count})")
        return ResearchResponse(
            content=f"{self.name} research content (after retry)",
            citations=[
                SearchResult(
                    title=f"{self.name} Source 1",
                    url=f"https://example.com/{self.name}/1",
                    snippet=f"{self.name} snippet 1",
                ),
            ],
        )


class TestRetryOnTransient:
    """Test retry-on-transient behavior in run_multi_research."""

    async def test_retry_on_timeout_succeeds(self):
        """Single provider times out, retries, succeeds."""
        provider = MockTransientProvider("openai_deep", fail_count=1)
        mock_providers = [("openai_deep", provider)]
        mock_llm = MockLLMProvider()

        with patch("sat.research.multi_runner.discover_providers", return_value=mock_providers):
            with patch("sat.research.multi_runner._RETRY_DELAY", 0):
                result = await run_multi_research(
                    question="Test question", llm_provider=mock_llm, max_sources=10
                )

        assert isinstance(result, ResearchResult)
        assert provider.call_count == 2

    async def test_no_retry_when_one_provider_succeeds(self):
        """Two providers, one succeeds, one times out; no retry."""
        transient = MockTransientProvider("openai_deep", fail_count=99)
        good = MockResearchProvider("perplexity")
        mock_providers = [("openai_deep", transient), ("perplexity", good)]
        mock_llm = MockLLMProvider()

        with patch("sat.research.multi_runner.discover_providers", return_value=mock_providers):
            with patch("sat.research.multi_runner._RETRY_DELAY", 0):
                result = await run_multi_research(
                    question="Test question", llm_provider=mock_llm, max_sources=10
                )

        assert isinstance(result, ResearchResult)
        assert transient.call_count == 1  # Not retried because perplexity succeeded

    async def test_retry_fails_again_raises(self):
        """Provider always times out; RuntimeError after retry."""
        provider = MockTransientProvider("openai_deep", fail_count=99)
        mock_providers = [("openai_deep", provider)]
        mock_llm = MockLLMProvider()

        with patch("sat.research.multi_runner.discover_providers", return_value=mock_providers):
            with patch("sat.research.multi_runner._RETRY_DELAY", 0):
                with pytest.raises(RuntimeError, match="All research providers failed"):
                    await run_multi_research(
                        question="Test question", llm_provider=mock_llm, max_sources=10
                    )

        assert provider.call_count == 2  # Tried once + one retry

    async def test_non_transient_error_not_retried(self):
        """Non-transient error; no retry attempted."""
        provider = MockResearchProvider("openai_deep", fail=True)  # Raises RuntimeError
        mock_providers = [("openai_deep", provider)]
        mock_llm = MockLLMProvider()

        with patch("sat.research.multi_runner.discover_providers", return_value=mock_providers):
            with patch("sat.research.multi_runner._RETRY_DELAY", 0):
                with pytest.raises(RuntimeError, match="All research providers failed"):
                    await run_multi_research(
                        question="Test question", llm_provider=mock_llm, max_sources=10
                    )

    async def test_retry_on_research_request_failed_succeeds(self):
        """OpenAI returns status='failed', retries, succeeds."""
        provider = MockFailedRequestProvider("openai_deep", fail_count=1)
        mock_providers = [("openai_deep", provider)]
        mock_llm = MockLLMProvider()

        with patch("sat.research.multi_runner.discover_providers", return_value=mock_providers):
            with patch("sat.research.multi_runner._RETRY_DELAY", 0):
                result = await run_multi_research(
                    question="Test question", llm_provider=mock_llm, max_sources=10
                )

        assert isinstance(result, ResearchResult)
        assert provider.call_count == 2
