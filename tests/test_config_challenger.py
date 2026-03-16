"""Tests for cross-provider challenger resolution.

@mock-exempt: Environment variables are external OS state.
Testing environment variable resolution requires controlling os.environ,
which is an external boundary, not internal code.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from sat.config import resolve_challenger_provider


def test_resolve_challenger_finds_openai_for_anthropic():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
        result = resolve_challenger_provider("anthropic")
        assert result is not None
        provider, model = result
        assert provider == "openai"


def test_resolve_challenger_finds_anthropic_for_openai():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
        result = resolve_challenger_provider("openai")
        assert result is not None
        provider, model = result
        assert provider == "anthropic"


def test_resolve_challenger_skips_unavailable():
    """If preferred provider has no key, falls to next."""
    with patch("sat.config._load_config_file_key", return_value=None):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = resolve_challenger_provider("anthropic")
            assert result is not None
            provider, _ = result
            assert provider == "gemini"


def test_resolve_challenger_returns_none_when_no_keys():
    with patch("sat.config._load_config_file_key", return_value=None):
        with patch.dict(os.environ, {}, clear=True):
            result = resolve_challenger_provider("anthropic")
            assert result is None
