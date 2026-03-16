"""Model listing endpoint with caching.

GET /api/config/models/{provider} returns available models for a provider,
categorized as "analysis" or "research".

@decision DEC-MODELS-001
@title Hybrid model listing — API-fetched for OpenAI/Gemini, curated for Anthropic/Perplexity
@status accepted
@rationale Anthropic has no public model listing API. Perplexity's API is
OpenAI-compatible but does not expose a models endpoint. OpenAI and Gemini
both provide model listing APIs, so we use them for accuracy while falling
back to curated lists on failure. Results are cached in-memory with a 1-hour
TTL to avoid hammering the APIs on every page load. The cache is invalidated
when the API key hash changes, ensuring users who rotate keys see fresh lists.

@decision DEC-MODELS-002
@title Cache keyed by provider name, invalidated by key hash comparison
@status accepted
@rationale A 1-hour TTL is appropriate because model lists rarely change
(providers add models infrequently). Key-hash invalidation handles the edge
case where a user switches from one account (with access to some models) to
another account (with different model access). The hash uses only the first
8 chars — sufficient to detect a change without storing the full key.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from copy import deepcopy
from typing import Any

from fastapi import APIRouter

# Optional provider SDK imports — available at module level for test patching.
# Imported defensively so the route module loads even if a provider SDK is not
# installed in the current environment.
try:
    import openai  # type: ignore[import]
except ImportError:
    openai = None  # type: ignore[assignment]

try:
    import google.generativeai as genai  # type: ignore[import]
except ImportError:
    genai = None  # type: ignore[assignment]

from sat.config import (
    ANTHROPIC_ANALYSIS_MODELS,
    ANTHROPIC_RESEARCH_MODELS,
    DEFAULT_MODELS,
    GEMINI_ANALYSIS_MODELS_FALLBACK,
    GEMINI_RESEARCH_MODELS_FALLBACK,
    OPENAI_ANALYSIS_MODELS_FALLBACK,
    OPENAI_RESEARCH_MODELS_FALLBACK,
    PERPLEXITY_ANALYSIS_MODELS,
    PERPLEXITY_RESEARCH_MODELS,
    PROVIDER_API_KEY_ENVS,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

# In-memory cache: {provider: {models: ..., timestamp: float, key_hash: str}}
_model_cache: dict[str, dict[str, Any]] = {}

# Cache TTL — 1 hour. Mutatable by tests via module-level assignment.
CACHE_TTL_SECONDS: int = 3600

# Model ID substrings that indicate a non-generative (non-chat) model.
# These are used to filter out embedding, audio, image, and legacy models.
# Note: "search" is intentionally excluded because "deep-research" contains
# the substring "research" which contains "search" — we filter search-preview
# specifically instead to avoid false matches.
_OPENAI_FILTER_KEYWORDS = (
    "embedding",
    "embed",
    "whisper",
    "dall-e",
    "tts",
    "transcribe",
    "search-preview",  # e.g. gpt-4o-search-preview — NOT "deep-research"
    "similarity",
    "instruct",
    "moderation",
    "realtime",
    "audio",
    "image-",        # e.g. dall-e but not "image" in model names like "imagine"
    "clip",
    "davinci",
    "curie",
    "babbage",
    "-ada-",         # e.g. text-embedding-ada-002 but not future "ada-*" models
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _key_hash(provider: str) -> str:
    """Return an 8-char hash of the current API key for *provider*.

    Used to detect key changes that should invalidate the cache.
    Returns empty string if no key is configured.
    """
    env_var = PROVIDER_API_KEY_ENVS.get(provider, f"{provider.upper()}_API_KEY")
    key = os.environ.get(env_var, "")
    # Also check GOOGLE_API_KEY for gemini
    if provider == "gemini" and not key:
        key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        # Try ~/.sat/config.json
        try:
            from sat.config import _load_config_file_key
            key = _load_config_file_key(provider) or ""
        except Exception:
            key = ""
    if not key:
        return ""
    return hashlib.md5(key.encode()).hexdigest()[:8]


def _is_cache_valid(provider: str) -> bool:
    """Return True if the cache entry for *provider* is still valid."""
    entry = _model_cache.get(provider)
    if not entry:
        return False
    # Check TTL
    age = time.monotonic() - entry["timestamp"]
    if age > CACHE_TTL_SECONDS:
        return False
    # Check key hash — invalidate if key changed
    current_hash = _key_hash(provider)
    if current_hash != entry.get("key_hash", ""):
        return False
    return True


def _get_api_key(provider: str) -> str | None:
    """Return the API key for *provider* from env or config file, or None."""
    env_var = PROVIDER_API_KEY_ENVS.get(provider, f"{provider.upper()}_API_KEY")
    key = os.environ.get(env_var, "")
    if provider == "gemini" and not key:
        key = os.environ.get("GOOGLE_API_KEY", "")
    if key:
        return key
    try:
        from sat.config import _load_config_file_key
        return _load_config_file_key(provider)
    except Exception:
        return None


def _mark_default(models: list[dict], provider: str, category: str) -> list[dict]:
    """Mark the default model for *provider*/*category* with default=True.

    Uses DEFAULT_MODELS from config. Deep-copies entries to avoid mutating
    the source constants.
    """
    default_id = DEFAULT_MODELS.get(provider, "")
    result = []
    for m in models:
        entry = dict(m)  # shallow copy sufficient — values are primitives
        if entry.get("id") == default_id and category == "analysis":
            entry["default"] = True
        elif "default" not in entry:
            entry.setdefault("default", False)
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Provider-specific listing functions
# ---------------------------------------------------------------------------


def _list_anthropic() -> dict[str, list[dict]]:
    """Return curated Anthropic model lists."""
    return {
        "analysis": deepcopy(ANTHROPIC_ANALYSIS_MODELS),
        "research": deepcopy(ANTHROPIC_RESEARCH_MODELS),
    }


def _list_perplexity() -> dict[str, list[dict]]:
    """Return curated Perplexity model lists."""
    return {
        "analysis": deepcopy(PERPLEXITY_ANALYSIS_MODELS),
        "research": deepcopy(PERPLEXITY_RESEARCH_MODELS),
    }


def _list_brave() -> dict[str, list[dict]]:
    """Brave is a search API with no model concept — return empty lists."""
    return {"analysis": [], "research": []}


def _list_openai(api_key: str | None) -> tuple[dict[str, list[dict]], str | None]:
    """Fetch OpenAI models via SDK, categorize, and filter.

    Returns (models_dict, error_string_or_None).
    Falls back to curated list on any failure.
    """
    if openai is None:
        return (
            {
                "analysis": deepcopy(OPENAI_ANALYSIS_MODELS_FALLBACK),
                "research": deepcopy(OPENAI_RESEARCH_MODELS_FALLBACK),
            },
            "openai package not installed",
        )

    try:
        client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        raw_models = list(client.models.list())
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI model listing failed: %s", exc)
        return (
            {
                "analysis": deepcopy(OPENAI_ANALYSIS_MODELS_FALLBACK),
                "research": deepcopy(OPENAI_RESEARCH_MODELS_FALLBACK),
            },
            str(exc),
        )

    analysis: list[dict] = []
    research: list[dict] = []
    default_analysis = DEFAULT_MODELS.get("openai", "")

    for m in raw_models:
        model_id: str = m.id
        model_id_lower = model_id.lower()

        # Filter out non-generative models
        if any(kw in model_id_lower for kw in _OPENAI_FILTER_KEYWORDS):
            continue

        display_name = _openai_display_name(model_id)
        entry: dict = {"id": model_id, "name": display_name}

        if "deep-research" in model_id_lower:
            if model_id == DEFAULT_MODELS.get("openai_research", "o3-deep-research-2025-06-26"):
                entry["default"] = True
            research.append(entry)
        else:
            if model_id == default_analysis:
                entry["default"] = True
            analysis.append(entry)

    # Sort: defaults first, then alphabetical
    analysis.sort(key=lambda x: (not x.get("default", False), x["id"]))
    research.sort(key=lambda x: (not x.get("default", False), x["id"]))

    return {"analysis": analysis, "research": research}, None


def _openai_display_name(model_id: str) -> str:
    """Convert an OpenAI model ID to a human-friendly display name."""
    # Simple title-case mapping for common models
    _known: dict[str, str] = {
        "o3": "O3",
        "o3-mini": "O3 Mini",
        "o4-mini": "O4 Mini",
        "gpt-4o": "GPT-4o",
        "gpt-4o-mini": "GPT-4o Mini",
        "gpt-4-turbo": "GPT-4 Turbo",
        "gpt-4": "GPT-4",
        "gpt-4.1": "GPT-4.1",
        "gpt-4.1-mini": "GPT-4.1 Mini",
        "gpt-3.5-turbo": "GPT-3.5 Turbo",
        "o3-deep-research-2025-06-26": "O3 Deep Research",
        "o4-mini-deep-research-2025-06-26": "O4 Mini Deep Research",
    }
    if model_id in _known:
        return _known[model_id]
    # Generic: replace hyphens with spaces and title-case
    return model_id.replace("-", " ").title()


def _list_gemini(api_key: str | None) -> tuple[dict[str, list[dict]], str | None]:
    """Fetch Gemini models via google.generativeai, categorize, and filter.

    Returns (models_dict, error_string_or_None).
    Falls back to curated list on any failure.
    """
    if genai is None:
        return (
            {
                "analysis": deepcopy(GEMINI_ANALYSIS_MODELS_FALLBACK),
                "research": deepcopy(GEMINI_RESEARCH_MODELS_FALLBACK),
            },
            "google-generativeai package not installed",
        )

    try:
        if api_key:
            genai.configure(api_key=api_key)
        raw_models = list(genai.list_models())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini model listing failed: %s", exc)
        return (
            {
                "analysis": deepcopy(GEMINI_ANALYSIS_MODELS_FALLBACK),
                "research": deepcopy(GEMINI_RESEARCH_MODELS_FALLBACK),
            },
            str(exc),
        )

    analysis: list[dict] = []
    research: list[dict] = []
    default_analysis = DEFAULT_MODELS.get("gemini", "gemini-2.5-pro")

    for m in raw_models:
        # Filter: only include models that support generateContent
        methods = getattr(m, "supported_generation_methods", [])
        if "generateContent" not in methods:
            continue

        # model.name is like "models/gemini-2.5-pro" — strip the prefix
        full_name: str = m.name
        model_id = full_name.removeprefix("models/")
        model_id_lower = model_id.lower()

        display_name = _gemini_display_name(model_id)
        entry: dict = {"id": model_id, "name": display_name}

        if "deep-research" in model_id_lower:
            research.append(entry)
        else:
            if model_id == default_analysis or full_name == default_analysis:
                entry["default"] = True
            analysis.append(entry)

    # Sort: defaults first, then alphabetical
    analysis.sort(key=lambda x: (not x.get("default", False), x["id"]))
    research.sort(key=lambda x: (not x.get("default", False), x["id"]))

    return {"analysis": analysis, "research": research}, None


def _gemini_display_name(model_id: str) -> str:
    """Convert a Gemini model ID to a human-friendly display name."""
    _known: dict[str, str] = {
        "gemini-2.5-pro": "Gemini 2.5 Pro",
        "gemini-2.5-flash": "Gemini 2.5 Flash",
        "gemini-2.0-pro": "Gemini 2.0 Pro",
        "gemini-2.0-flash": "Gemini 2.0 Flash",
        "gemini-1.5-pro": "Gemini 1.5 Pro",
        "gemini-1.5-flash": "Gemini 1.5 Flash",
    }
    if model_id in _known:
        return _known[model_id]
    return model_id.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/api/config/models/{provider}")
async def list_models(provider: str) -> dict:
    """Return available models for a provider, categorized as analysis or research.

    Results are cached in-memory for CACHE_TTL_SECONDS (1 hour by default).
    Cache is invalidated when the provider's API key changes.

    Providers:
    - anthropic: curated list (no listing API available)
    - perplexity: curated list (all models are research category)
    - brave: empty lists (search API, no model concept)
    - openai: fetched via openai.models.list(), fallback to curated on failure
    - gemini: fetched via genai.list_models(), fallback to curated on failure

    Returns:
        {
            "provider": str,
            "models": {"analysis": [...], "research": [...]},
            "cached": bool,
            "error": str | None  # present only when API call failed
        }
    """
    provider = provider.lower()

    known_providers = {"anthropic", "openai", "gemini", "perplexity", "brave"}
    if provider not in known_providers:
        return {
            "provider": provider,
            "models": {"analysis": [], "research": []},
            "cached": False,
            "error": f"Unknown provider: {provider!r}",
        }

    # Cache hit
    if _is_cache_valid(provider):
        cached_entry = _model_cache[provider]
        return {
            "provider": provider,
            "models": deepcopy(cached_entry["models"]),
            "cached": True,
        }

    # Cache miss — fetch fresh data
    api_key = _get_api_key(provider)
    error: str | None = None

    if provider == "anthropic":
        models = _list_anthropic()
    elif provider == "perplexity":
        models = _list_perplexity()
    elif provider == "brave":
        models = _list_brave()
    elif provider == "openai":
        models, error = _list_openai(api_key)
    elif provider == "gemini":
        models, error = _list_gemini(api_key)
    else:
        models = {"analysis": [], "research": []}

    # Store in cache
    _model_cache[provider] = {
        "models": deepcopy(models),
        "timestamp": time.monotonic(),
        "key_hash": _key_hash(provider),
    }

    response: dict = {
        "provider": provider,
        "models": models,
        "cached": False,
    }
    if error:
        response["error"] = error

    return response
