"""Shared helpers for native local LLM HTTP providers (Ollama, LM Studio)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Default hosts (scheme + host + port, no path suffix).
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_LMSTUDIO_HOST = "http://127.0.0.1:1234"

LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio"})

# Long timeout — local inference of large SAT schemas can take minutes.
LOCAL_HTTP_TIMEOUT = 1200.0
PROBE_TIMEOUT = 1.0

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def normalize_host(url: str) -> str:
    """Strip trailing slashes and accidental /v1 or /api path suffixes."""
    host = url.strip().rstrip("/")
    # Longer suffixes first so /api/v1 is not partially stripped to /api.
    for suffix in ("/api/v1", "/v1", "/api"):
        if host.endswith(suffix):
            host = host[: -len(suffix)].rstrip("/")
            break
    return host


def extract_json_text(text: str) -> str:
    """Best-effort extraction of a JSON object/array from model output."""
    stripped = text.strip()
    if not stripped:
        return stripped

    fence = _JSON_FENCE_RE.search(stripped)
    if fence:
        return fence.group(1).strip()

    # Find first { or [ and last matching closer
    start_obj = stripped.find("{")
    start_arr = stripped.find("[")
    if start_obj < 0 and start_arr < 0:
        return stripped
    if start_obj < 0:
        start = start_arr
        end = stripped.rfind("]")
    elif start_arr < 0:
        start = start_obj
        end = stripped.rfind("}")
    else:
        if start_obj < start_arr:
            start = start_obj
            end = stripped.rfind("}")
        else:
            start = start_arr
            end = stripped.rfind("]")
    if end > start:
        return stripped[start : end + 1]
    return stripped


def schema_for_ollama_format(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-schema dict suitable for Ollama's ``format`` field.

    Strips Pydantic extras that some models reject while keeping structure.
    """
    cleaned = json.loads(json.dumps(schema))

    def _strip(node: Any) -> None:
        if not isinstance(node, dict):
            return
        node.pop("title", None)
        node.pop("default", None)
        if "$defs" in node:
            for defn in node["$defs"].values():
                _strip(defn)
        if "properties" in node and isinstance(node["properties"], dict):
            for prop in node["properties"].values():
                _strip(prop)
        if "items" in node:
            _strip(node["items"])
        for key in ("anyOf", "oneOf"):
            if key in node and isinstance(node[key], list):
                for variant in node[key]:
                    _strip(variant)

    _strip(cleaned)
    return cleaned
