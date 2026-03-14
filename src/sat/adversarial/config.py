"""Adversarial analysis configuration.

@decision DEC-ADV-002: TOML-configurable multi-model setup.
@title Named provider references with role assignments
@status accepted
@rationale Providers are named references (e.g. "claude", "gpt4"), roles map
names to primary/challenger/adjudicator. Supports both TOML config files and
CLI flags for quick inline setup. Only imports from pydantic — no circular deps.

@decision DEC-ADV-006: Trident mode config with optional investigator role.
@title mode field + investigator role in AdversarialConfig/RoleAssignment
@status accepted
@rationale mode="trident" activates the three-provider IPA flow. investigator
is optional in RoleAssignment so dual mode configs remain valid without changes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderRef(BaseModel):
    """Reference to a named provider configuration."""

    provider: str = Field(description="Provider type: 'anthropic', 'openai', 'gemini'")
    model: str = Field(description="Model identifier")
    api_key: str | None = Field(default=None, description="API key (falls back to env var)")


class RoleAssignment(BaseModel):
    """Maps roles to named provider references."""

    primary: str = Field(description="Key into providers dict for primary analyst")
    challenger: str = Field(description="Key into providers dict for challenger/critic")
    adjudicator: str | None = Field(
        default=None,
        description="Key into providers dict for adjudicator",
    )
    investigator: str | None = Field(
        default=None,
        description="Key into providers dict for investigator (trident mode)",
    )


class AdversarialConfig(BaseModel):
    """Configuration for adversarial multi-model analysis."""

    enabled: bool = Field(default=True, description="Enable adversarial analysis")
    rounds: int = Field(default=2, description="Number of critique-rebuttal rounds")
    providers: dict[str, ProviderRef] = Field(
        default_factory=dict, description="Named provider configurations"
    )
    roles: RoleAssignment | None = Field(default=None, description="Role assignments")
    mode: str = Field(
        default="dual",
        description="Adversarial mode: 'dual' or 'trident'",
    )


_AUTO_MODE = object()  # Sentinel: caller did not explicitly pick a mode


def build_adversarial_config(
    provider: str,
    model: str | None = None,
    mode: str | object = _AUTO_MODE,
    rounds: int = 1,
    api_key: str | None = None,
) -> AdversarialConfig:
    """Build a fully-populated AdversarialConfig with provider resolution.

    Encapsulates the CLI's provider-resolution logic so that API routes
    (and any other caller) get correct providers and role assignments
    without duplicating the wiring.

    Args:
        provider: Primary LLM provider name (e.g. "anthropic", "openai", "gemini").
        model: Explicit model override; resolved via ProviderConfig if None.
        mode: Adversarial mode string ("dual" or "trident"), or omitted for
            auto-detection. When omitted (default), the factory upgrades to
            "trident" automatically if a third provider key is available.
            Passing "dual" explicitly suppresses the auto-upgrade.
        rounds: Number of critique-rebuttal rounds.
        api_key: Explicit API key for the primary provider.

    Returns:
        Fully-populated AdversarialConfig with providers and roles set.

    @decision DEC-ADV-007
    @title Shared factory for AdversarialConfig construction
    @status accepted
    @rationale API routes were constructing AdversarialConfig without providers/roles,
    causing 'No role assignments configured' errors. This factory centralizes the
    resolution logic that the CLI already had inline, eliminating the duplication
    between analysis.py, evidence.py, and cli.py.

    A sentinel default (_AUTO_MODE) distinguishes "caller did not specify a mode"
    (allow auto-upgrade to trident) from "caller explicitly passed 'dual'"
    (suppress auto-upgrade), without requiring a separate parameter.
    """
    from sat.config import ProviderConfig, resolve_challenger_provider, resolve_investigator_provider

    resolved_model = model or ProviderConfig(provider=provider).resolve_model()

    challenger_info = resolve_challenger_provider(provider)
    if challenger_info:
        chall_provider, chall_model = challenger_info
    else:
        # No other provider available — self-critique fallback
        chall_provider, chall_model = provider, resolved_model

    providers_dict: dict[str, ProviderRef] = {
        "primary": ProviderRef(provider=provider, model=resolved_model, api_key=api_key),
        "challenger": ProviderRef(provider=chall_provider, model=chall_model),
    }
    role_kwargs: dict[str, str] = {"primary": "primary", "challenger": "challenger"}

    # Resolve the effective mode string (sentinel → "dual" as starting point)
    caller_specified = mode is not _AUTO_MODE
    effective_mode = "dual" if mode is _AUTO_MODE else str(mode)

    if effective_mode == "trident":
        # Explicit trident requested — resolve investigator if available
        inv_info = resolve_investigator_provider(provider, chall_provider)
        if inv_info:
            inv_prov, inv_model = inv_info
            providers_dict["investigator"] = ProviderRef(provider=inv_prov, model=inv_model)
            role_kwargs["investigator"] = "investigator"
    elif not caller_specified:
        # Auto-detect trident only when the caller did not explicitly choose a mode
        inv_info = resolve_investigator_provider(provider, chall_provider)
        if inv_info:
            inv_prov, inv_model = inv_info
            providers_dict["investigator"] = ProviderRef(provider=inv_prov, model=inv_model)
            role_kwargs["investigator"] = "investigator"
            effective_mode = "trident"
    # else: caller explicitly passed "dual" — keep dual, skip investigator resolution

    return AdversarialConfig(
        enabled=True,
        rounds=rounds,
        providers=providers_dict,
        roles=RoleAssignment(**role_kwargs),
        mode=effective_mode,
    )
