"""Tests for GET /api/config/models/{provider} endpoint.

Covers:
- All 5 providers return well-formed responses
- OpenAI and Gemini use API-fetched lists (mocked at HTTP boundary)
- Anthropic and Perplexity return curated lists
- Brave returns empty lists
- Cache hit returns cached=True
- Cache miss returns cached=False
- Failed API call returns curated fallback with error field
- Model categorization (deep-research → research, others → analysis)
- Default model marking

@decision DEC-MODELS-TEST-001
@title Tests mock external provider APIs at the HTTP layer only
@status accepted
@rationale External LLM and REST APIs (openai.OpenAI, httpx.get for Gemini REST)
are mocked because they require real API keys and make network calls. Internal
cache, model lists, and categorization logic are tested directly without mocking.
Gemini tests mock httpx.get (the REST boundary) rather than google.generativeai
(which is not installed); see DEC-MODELS-003.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app

# @mock-exempt: openai.OpenAI and httpx.get (Gemini REST API) are external
# third-party service boundaries requiring real API keys and network access.
# They cannot be tested without mocking at these external boundaries.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8742)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_model_cache():
    """Clear the in-memory model cache before each test."""
    import sat.api.routes.models as models_mod
    models_mod._model_cache.clear()
    yield
    models_mod._model_cache.clear()


# ---------------------------------------------------------------------------
# Response schema validation
# ---------------------------------------------------------------------------


def test_response_schema_anthropic(client):
    """Anthropic returns correct schema with analysis/research keys."""
    resp = client.get("/api/config/models/anthropic")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "anthropic"
    assert "models" in body
    assert "analysis" in body["models"]
    assert "research" in body["models"]
    assert "cached" in body


def test_response_schema_perplexity(client):
    """Perplexity returns correct schema."""
    resp = client.get("/api/config/models/perplexity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "perplexity"
    assert "models" in body
    assert "analysis" in body["models"]
    assert "research" in body["models"]
    assert "cached" in body


def test_response_schema_brave(client):
    """Brave returns empty lists — no model concept."""
    resp = client.get("/api/config/models/brave")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "brave"
    assert body["models"]["analysis"] == []
    assert body["models"]["research"] == []


def test_model_entry_schema(client):
    """Each model entry has id, name, and optional default field."""
    resp = client.get("/api/config/models/anthropic")
    body = resp.json()
    for category in ("analysis", "research"):
        for model in body["models"][category]:
            assert "id" in model
            assert "name" in model
            # 'default' is optional but if present must be bool
            if "default" in model:
                assert isinstance(model["default"], bool)


# ---------------------------------------------------------------------------
# Anthropic curated list
# ---------------------------------------------------------------------------


def test_anthropic_analysis_models_present(client):
    """Anthropic analysis models include expected curated entries."""
    resp = client.get("/api/config/models/anthropic")
    body = resp.json()
    analysis_ids = [m["id"] for m in body["models"]["analysis"]]
    assert "claude-opus-4-6" in analysis_ids
    assert "claude-sonnet-4-6" in analysis_ids


def test_anthropic_has_default_analysis_model(client):
    """Anthropic default analysis model is marked."""
    resp = client.get("/api/config/models/anthropic")
    body = resp.json()
    defaults = [m for m in body["models"]["analysis"] if m.get("default")]
    assert len(defaults) == 1
    assert defaults[0]["id"] == "claude-opus-4-6"


def test_anthropic_research_is_empty(client):
    """Anthropic has no research models."""
    resp = client.get("/api/config/models/anthropic")
    body = resp.json()
    assert body["models"]["research"] == []


# ---------------------------------------------------------------------------
# Perplexity curated list
# ---------------------------------------------------------------------------


def test_perplexity_all_models_are_research(client):
    """All Perplexity models are in the research category."""
    resp = client.get("/api/config/models/perplexity")
    body = resp.json()
    assert body["models"]["analysis"] == []
    research_ids = [m["id"] for m in body["models"]["research"]]
    assert "sonar-deep-research" in research_ids
    assert "sonar" in research_ids


def test_perplexity_has_default_research_model(client):
    """Perplexity default research model is marked."""
    resp = client.get("/api/config/models/perplexity")
    body = resp.json()
    defaults = [m for m in body["models"]["research"] if m.get("default")]
    assert len(defaults) >= 1


# ---------------------------------------------------------------------------
# OpenAI — API-fetched with mocked external SDK
# ---------------------------------------------------------------------------


def _make_openai_model(model_id: str):
    """Create a mock openai model object mimicking openai SDK's Model type."""
    m = MagicMock()
    m.id = model_id
    return m


def test_openai_uses_api_listing(client):
    """OpenAI uses openai.models.list() to fetch models."""
    fake_models = [
        _make_openai_model("gpt-4o"),
        _make_openai_model("o3"),
        _make_openai_model("o3-deep-research-2025-06-26"),
        _make_openai_model("text-embedding-ada-002"),  # should be filtered
        _make_openai_model("whisper-1"),  # should be filtered
    ]
    mock_client = MagicMock()
    mock_client.models.list.return_value = fake_models

    with patch("sat.api.routes.models.openai") as mock_openai:
        mock_openai.OpenAI.return_value = mock_client
        resp = client.get("/api/config/models/openai")

    assert resp.status_code == 200
    body = resp.json()
    analysis_ids = [m["id"] for m in body["models"]["analysis"]]
    research_ids = [m["id"] for m in body["models"]["research"]]

    # Completions models should appear in analysis
    assert "gpt-4o" in analysis_ids
    assert "o3" in analysis_ids
    # deep-research model goes to research category
    assert "o3-deep-research-2025-06-26" in research_ids
    # embedding / whisper should be filtered out
    assert "text-embedding-ada-002" not in analysis_ids
    assert "whisper-1" not in analysis_ids


def test_openai_default_model_marked(client):
    """OpenAI default model (o3) is marked default=True."""
    fake_models = [
        _make_openai_model("o3"),
        _make_openai_model("gpt-4o"),
        _make_openai_model("o3-deep-research-2025-06-26"),
    ]
    mock_client = MagicMock()
    mock_client.models.list.return_value = fake_models

    with patch("sat.api.routes.models.openai") as mock_openai:
        mock_openai.OpenAI.return_value = mock_client
        resp = client.get("/api/config/models/openai")

    body = resp.json()
    analysis_defaults = [m for m in body["models"]["analysis"] if m.get("default")]
    assert len(analysis_defaults) == 1
    assert analysis_defaults[0]["id"] == "o3"


def test_openai_api_failure_returns_fallback(client):
    """If OpenAI API call fails, returns curated fallback with error field."""
    import sat.api.routes.models as models_mod
    models_mod._model_cache.clear()

    with patch("sat.api.routes.models.openai") as mock_openai:
        mock_openai.OpenAI.side_effect = Exception("API error")
        resp = client.get("/api/config/models/openai")

    assert resp.status_code == 200
    body = resp.json()
    # Must return something useful — analysis list not empty (curated fallback)
    assert len(body["models"]["analysis"]) > 0
    assert "error" in body
    assert body["error"] is not None


# ---------------------------------------------------------------------------
# Gemini — API-fetched via REST (httpx.get), mocked at the HTTP boundary
# ---------------------------------------------------------------------------


def _make_gemini_rest_response(models: list[dict]) -> MagicMock:
    """Create a mock httpx.Response for the Gemini REST /v1beta/models endpoint.

    Each model dict should have at minimum "name" and "supportedGenerationMethods".
    """
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"models": models}
    return mock_resp


def test_gemini_uses_api_listing(client):
    """Gemini fetches models via the REST API (httpx.get) and categorizes them."""
    fake_models = [
        {
            "name": "models/gemini-2.5-pro",
            "displayName": "Gemini 2.5 Pro",
            "supportedGenerationMethods": ["generateContent"],
        },
        {
            "name": "models/gemini-1.5-flash",
            "displayName": "Gemini 1.5 Flash",
            "supportedGenerationMethods": ["generateContent"],
        },
        {
            "name": "models/gemini-deep-research-pro",
            "displayName": "Gemini Deep Research Pro",
            "supportedGenerationMethods": ["generateContent"],
        },
        {
            "name": "models/text-embedding-004",
            "displayName": "Text Embedding 004",
            "supportedGenerationMethods": ["embedContent"],  # should be filtered
        },
    ]

    with patch("sat.api.routes.models.httpx") as mock_httpx:
        mock_httpx.get.return_value = _make_gemini_rest_response(fake_models)
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            resp = client.get("/api/config/models/gemini")

    assert resp.status_code == 200
    body = resp.json()
    analysis_ids = [m["id"] for m in body["models"]["analysis"]]
    research_ids = [m["id"] for m in body["models"]["research"]]

    # Generative models should appear in analysis
    assert "gemini-2.5-pro" in analysis_ids
    # deep-research model goes to research category
    assert any("deep-research" in rid for rid in research_ids)
    # embedding model filtered out
    assert not any("embedding" in aid for aid in analysis_ids)


def test_gemini_api_failure_returns_fallback(client):
    """If Gemini REST API call fails, returns curated fallback with error field."""
    import sat.api.routes.models as models_mod
    models_mod._model_cache.clear()

    with patch("sat.api.routes.models.httpx") as mock_httpx:
        mock_httpx.get.side_effect = Exception("API error")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            resp = client.get("/api/config/models/gemini")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["models"]["analysis"]) > 0
    assert "error" in body
    assert body["error"] is not None


def test_gemini_no_api_key_returns_fallback(client):
    """If no Gemini API key is configured, returns curated fallback with error."""
    import sat.api.routes.models as models_mod
    models_mod._model_cache.clear()

    with patch("sat.api.routes.models._get_api_key", return_value=None):
        resp = client.get("/api/config/models/gemini")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["models"]["analysis"]) > 0
    assert "error" in body
    assert body["error"] is not None


def test_gemini_research_fallback_includes_deep_research(client):
    """The Gemini research fallback list includes the known deep-research model."""
    import sat.api.routes.models as models_mod
    models_mod._model_cache.clear()

    with patch("sat.api.routes.models.httpx") as mock_httpx:
        mock_httpx.get.side_effect = Exception("network error")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            resp = client.get("/api/config/models/gemini")

    assert resp.status_code == 200
    body = resp.json()
    research_ids = [m["id"] for m in body["models"]["research"]]
    assert "deep-research-pro-preview-12-2025" in research_ids


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def test_first_call_not_cached(client):
    """First call returns cached=False."""
    resp = client.get("/api/config/models/anthropic")
    body = resp.json()
    assert body["cached"] is False


def test_second_call_is_cached(client):
    """Second call within TTL returns cached=True."""
    client.get("/api/config/models/anthropic")
    resp = client.get("/api/config/models/anthropic")
    body = resp.json()
    assert body["cached"] is True


def test_different_providers_cached_independently(client):
    """Each provider has its own cache slot."""
    resp_a = client.get("/api/config/models/anthropic")
    resp_p = client.get("/api/config/models/perplexity")

    assert resp_a.json()["cached"] is False
    assert resp_p.json()["cached"] is False

    # Second calls should be cached
    resp_a2 = client.get("/api/config/models/anthropic")
    resp_p2 = client.get("/api/config/models/perplexity")
    assert resp_a2.json()["cached"] is True
    assert resp_p2.json()["cached"] is True


def test_cache_expiry(client):
    """Cache entry expires after TTL."""
    import sat.api.routes.models as models_mod

    # Force a very short TTL
    orig_ttl = models_mod.CACHE_TTL_SECONDS
    models_mod.CACHE_TTL_SECONDS = 0  # Expire immediately

    try:
        client.get("/api/config/models/anthropic")
        # With TTL=0, all entries are expired
        resp = client.get("/api/config/models/anthropic")
        body = resp.json()
        assert body["cached"] is False
    finally:
        models_mod.CACHE_TTL_SECONDS = orig_ttl


def test_cache_busted_on_api_key_change(client):
    """Cache is invalidated when the API key for a provider changes."""
    import sat.api.routes.models as models_mod

    # Seed cache
    client.get("/api/config/models/anthropic")
    assert "anthropic" in models_mod._model_cache

    # Simulate key change by mutating stored hash
    models_mod._model_cache["anthropic"]["key_hash"] = "different-hash"

    resp = client.get("/api/config/models/anthropic")
    body = resp.json()
    assert body["cached"] is False


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


def test_unknown_provider_returns_404_or_empty(client):
    """Unknown provider returns 404 or empty models."""
    resp = client.get("/api/config/models/unknownprovider")
    assert resp.status_code in (404, 200)
    if resp.status_code == 200:
        body = resp.json()
        assert body["models"]["analysis"] == []
        assert body["models"]["research"] == []
