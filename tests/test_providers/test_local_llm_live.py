"""Live integration tests against local Ollama and LM Studio native APIs.

Skipped individually when the corresponding server is not reachable.
Run with::

    pytest -m integration tests/test_providers/test_local_llm_live.py -v
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage
from sat.providers.lmstudio import LMStudioProvider
from sat.providers.local_http import (
    DEFAULT_LMSTUDIO_HOST,
    DEFAULT_OLLAMA_HOST,
    PROBE_TIMEOUT,
    normalize_host,
)
from sat.providers.ollama import OllamaProvider


class _HelloSchema(BaseModel):
    greeting: str


def _ollama_reachable() -> bool:
    try:
        r = httpx.get(f"{DEFAULT_OLLAMA_HOST}/api/tags", timeout=PROBE_TIMEOUT)
        return r.status_code < 500
    except Exception:
        return False


def _lmstudio_reachable() -> bool:
    try:
        r = httpx.get(f"{DEFAULT_LMSTUDIO_HOST}/api/v1/models", timeout=PROBE_TIMEOUT)
        return r.status_code < 500
    except Exception:
        return False


def _first_ollama_model() -> str | None:
    r = httpx.get(f"{DEFAULT_OLLAMA_HOST}/api/tags", timeout=5.0)
    r.raise_for_status()
    models = r.json().get("models") or []
    if not models:
        return None
    return models[0].get("name") or models[0].get("model")


def _first_lmstudio_model() -> str | None:
    r = httpx.get(f"{DEFAULT_LMSTUDIO_HOST}/api/v1/models", timeout=5.0)
    r.raise_for_status()
    for m in r.json().get("models") or []:
        if m.get("type") == "llm" and m.get("key"):
            return m["key"]
    return None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_live_generate():
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable at 127.0.0.1:11434")
    model = _first_ollama_model()
    if not model:
        pytest.skip("No Ollama models pulled")

    provider = OllamaProvider(
        ProviderConfig(provider="ollama", model=model, base_url=DEFAULT_OLLAMA_HOST)
    )
    try:
        result = await provider.generate(
            "Reply briefly.",
            [LLMMessage(role="user", content="Say hello in one short word.")],
            max_tokens=32,
            temperature=0.1,
        )
    finally:
        await provider.aclose()

    assert result.text.strip()
    assert normalize_host(DEFAULT_OLLAMA_HOST) == "http://127.0.0.1:11434"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_live_structured():
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable at 127.0.0.1:11434")
    model = _first_ollama_model()
    if not model:
        pytest.skip("No Ollama models pulled")

    provider = OllamaProvider(
        ProviderConfig(provider="ollama", model=model, base_url=DEFAULT_OLLAMA_HOST)
    )
    try:
        result = await provider.generate_structured(
            "Return JSON only.",
            [LLMMessage(role="user", content='Produce greeting="hi"')],
            _HelloSchema,
            max_tokens=64,
            temperature=0.1,
        )
    finally:
        await provider.aclose()

    assert isinstance(result.greeting, str)
    assert result.greeting.strip()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lmstudio_live_generate():
    if not _lmstudio_reachable():
        pytest.skip("LM Studio not reachable at 127.0.0.1:1234")
    model = _first_lmstudio_model()
    if not model:
        pytest.skip("No LM Studio LLM models available")

    provider = LMStudioProvider(
        ProviderConfig(provider="lmstudio", model=model, base_url=DEFAULT_LMSTUDIO_HOST)
    )
    try:
        result = await provider.generate(
            "Reply briefly.",
            [LLMMessage(role="user", content="Say hello in one short word.")],
            max_tokens=32,
            temperature=0.1,
        )
    finally:
        await provider.aclose()

    assert result.text.strip()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lmstudio_live_structured():
    if not _lmstudio_reachable():
        pytest.skip("LM Studio not reachable at 127.0.0.1:1234")
    model = _first_lmstudio_model()
    if not model:
        pytest.skip("No LM Studio LLM models available")

    provider = LMStudioProvider(
        ProviderConfig(provider="lmstudio", model=model, base_url=DEFAULT_LMSTUDIO_HOST)
    )
    try:
        result = await provider.generate_structured(
            "Return JSON only.",
            [LLMMessage(role="user", content='Produce greeting="hi"')],
            _HelloSchema,
            max_tokens=64,
            temperature=0.1,
        )
    finally:
        await provider.aclose()

    assert isinstance(result.greeting, str)
    assert result.greeting.strip()
