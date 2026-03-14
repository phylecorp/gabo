"""Tests for adversarial provider pool.

# @mock-exempt: Test doubles implement the LLMProvider protocol pattern —
# ProviderPool delegates to create_provider which is the external boundary.

@decision DEC-TEST-ADV-003: Pool tests with provider creation mocking.
@title Verify ProviderPool role resolution and caching
@status accepted
@rationale ProviderPool resolves named roles to concrete LLM providers. We mock
create_provider (the external boundary) to test pool logic: role resolution,
caching, and error handling for missing providers/roles.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sat.adversarial.config import AdversarialConfig, ProviderRef, RoleAssignment
from sat.adversarial.pool import ProviderPool


def _make_config(**overrides) -> AdversarialConfig:
    defaults = {
        "enabled": True,
        "rounds": 1,
        "providers": {
            "claude": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
            "gpt4": ProviderRef(provider="openai", model="o3"),
            "gemini": ProviderRef(provider="gemini", model="gemini-2.5-pro"),
        },
        "roles": RoleAssignment(primary="claude", challenger="gpt4", adjudicator="gemini"),
    }
    defaults.update(overrides)
    return AdversarialConfig(**defaults)


class FakeProvider:
    """Minimal test double implementing LLMProvider protocol."""

    def __init__(self, name: str = "fake"):
        self.name = name

    async def generate(self, system_prompt, messages, max_tokens=4096, temperature=0.3):
        pass

    async def generate_structured(
        self, system_prompt, messages, output_schema, max_tokens=4096, temperature=0.3
    ):
        pass


@patch("sat.adversarial.pool.create_provider")
def test_get_primary(mock_create):
    mock_create.return_value = FakeProvider("primary")
    pool = ProviderPool(_make_config())
    provider = pool.get_primary()
    assert isinstance(provider, FakeProvider)
    mock_create.assert_called_once()


@patch("sat.adversarial.pool.create_provider")
def test_get_challenger(mock_create):
    mock_create.return_value = FakeProvider("challenger")
    pool = ProviderPool(_make_config())
    provider = pool.get_challenger()
    assert isinstance(provider, FakeProvider)


@patch("sat.adversarial.pool.create_provider")
def test_get_adjudicator(mock_create):
    mock_create.return_value = FakeProvider("adjudicator")
    pool = ProviderPool(_make_config())
    provider = pool.get_adjudicator()
    assert provider is not None


@patch("sat.adversarial.pool.create_provider")
def test_adjudicator_none_when_not_configured(mock_create):
    config = _make_config(
        roles=RoleAssignment(primary="claude", challenger="gpt4"),
    )
    pool = ProviderPool(config)
    assert pool.get_adjudicator() is None
    mock_create.assert_not_called()


@patch("sat.adversarial.pool.create_provider")
def test_provider_caching(mock_create):
    mock_create.return_value = FakeProvider("cached")
    config = _make_config(
        roles=RoleAssignment(primary="claude", challenger="claude"),
    )
    pool = ProviderPool(config)
    p1 = pool.get_primary()
    p2 = pool.get_challenger()
    assert p1 is p2
    assert mock_create.call_count == 1


def test_unknown_provider_name_raises():
    config = _make_config(
        roles=RoleAssignment(primary="nonexistent", challenger="gpt4"),
    )
    pool = ProviderPool(config)
    with pytest.raises(ValueError, match="Unknown provider name"):
        pool.get_primary()


def test_no_roles_raises():
    config = _make_config(roles=None)
    pool = ProviderPool(config)
    with pytest.raises(ValueError, match="No role assignments"):
        pool.get_primary()
