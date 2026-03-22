"""Tests for adversarial configuration models.

@decision DEC-TEST-ADV-002: Config model validation and defaults.
@title Verify ProviderRef, RoleAssignment, AdversarialConfig
@status accepted
@rationale Config models drive the entire adversarial system. Testing defaults,
validation, and TOML-style dict construction ensures the CLI → config → pool
pipeline works correctly.
"""

from __future__ import annotations


from sat.adversarial.config import AdversarialConfig, ProviderRef, RoleAssignment


def test_adversarial_config_full():
    config = AdversarialConfig(
        enabled=True,
        rounds=2,
        providers={
            "claude": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
            "gpt4": ProviderRef(provider="openai", model="o3"),
        },
        roles=RoleAssignment(primary="claude", challenger="gpt4"),
    )
    assert config.enabled
    assert config.rounds == 2
    assert len(config.providers) == 2
    assert config.roles.primary == "claude"


def test_adversarial_config_from_dict():
    """Verify config can be constructed from TOML-style dict data."""
    data = {
        "enabled": True,
        "rounds": 3,
        "providers": {
            "primary": {"provider": "anthropic", "model": "claude-opus-4-6"},
            "challenger": {"provider": "openai", "model": "o3"},
        },
        "roles": {"primary": "primary", "challenger": "challenger"},
    }
    config = AdversarialConfig(**data)
    assert config.enabled
    assert config.rounds == 3
    assert isinstance(config.providers["primary"], ProviderRef)
    assert isinstance(config.roles, RoleAssignment)
