"""Configuration loading with CLI > env > file precedence.

@decision DEC-CFG-001: Pydantic models for config with env var fallback.
Uses ProviderConfig for LLM settings and AnalysisConfig for the full run.
API key resolution order: explicit CLI flag > ~/.sat/config.json > env var.

@decision DEC-CFG-002: resolve_investigator_provider finds the third provider.
@title Auto-select investigator as the remaining provider not used by primary/challenger
@status accepted
@rationale Trident mode needs a third provider. Given primary and challenger are
already chosen, the investigator is the remaining provider with an API key set.
Follows the same env-var-based availability check as resolve_challenger_provider.

@decision DEC-CFG-003
@title Config file (~/.sat/config.json) loaded in resolve_api_key
@status accepted
@rationale When users save API keys via the Settings UI they are persisted to
~/.sat/config.json. ProviderConfig.resolve_api_key() now checks the config
file before falling back to environment variables so pipeline runs pick up
UI-saved keys without requiring a process restart or env var export.
The config file is loaded on each resolve_api_key call (not cached) to pick
up changes made during a running session.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from sat.adversarial.config import AdversarialConfig


DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-6",
    "openai": "o3",
    "gemini": "gemini-2.5-pro",
    "copilot": "copilot-gpt-4",
}

CHALLENGER_PREFERENCE = {
    "anthropic": ["openai", "gemini"],
    "openai": ["anthropic", "gemini"],
    "gemini": ["anthropic", "openai"],
}

PROVIDER_API_KEY_ENVS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "copilot": None,
}


def _get_sat_config_path() -> Path:
    """Return the path to ~/.sat/config.json.

    Overrideable in tests by monkey-patching this function on the module.
    """
    return Path.home() / ".sat" / "config.json"


def _load_config_file_key(provider: str) -> str | None:
    """Read the API key for *provider* from ~/.sat/config.json, if present."""
    config_path = _get_sat_config_path()
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
        key = data.get("providers", {}).get(provider, {}).get("api_key", "")
        return key if key else None
    except (json.JSONDecodeError, OSError):
        return None


def _load_config_file_model(provider: str) -> str | None:
    """Read the default model for *provider* from ~/.sat/config.json, if present."""
    config_path = _get_sat_config_path()
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
        model = data.get("providers", {}).get(provider, {}).get("default_model", "")
        return model if model else None
    except (json.JSONDecodeError, OSError):
        return None


def resolve_challenger_provider(primary_provider: str) -> tuple[str, str] | None:
    """Find the best available challenger provider different from primary.

    Checks env vars and config file to find a provider with an API key configured.
    Returns (provider_name, resolved_model) or None if no other provider available.
    """
    preferences = CHALLENGER_PREFERENCE.get(primary_provider, ["anthropic", "openai", "gemini"])
    for candidate in preferences:
        if candidate == primary_provider:
            continue
        env_var = PROVIDER_API_KEY_ENVS.get(candidate, f"{candidate.upper()}_API_KEY")
        has_key = bool(os.environ.get(env_var)) or bool(_load_config_file_key(candidate))
        if has_key:
            resolved = ProviderConfig(provider=candidate).resolve_model()
            return (candidate, resolved)
    return None


def resolve_investigator_provider(
    primary_provider: str, challenger_provider: str
) -> tuple[str, str] | None:
    """Find an investigator provider different from both primary and challenger.

    Iterates all known providers and returns the first one that:
    - Is not primary_provider
    - Is not challenger_provider
    - Has an API key configured in the environment or config file

    Returns (provider_name, resolved_model) or None if no third provider available.
    """
    all_providers = ["anthropic", "openai", "gemini"]
    for candidate in all_providers:
        if candidate == primary_provider or candidate == challenger_provider:
            continue
        env_var = PROVIDER_API_KEY_ENVS.get(candidate, f"{candidate.upper()}_API_KEY")
        has_key = bool(os.environ.get(env_var)) or bool(_load_config_file_key(candidate))
        if has_key:
            resolved = ProviderConfig(provider=candidate).resolve_model()
            return (candidate, resolved)
    return None


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    provider: str = Field(default="anthropic", description="LLM provider name")
    model: str | None = Field(
        default=None, description="Model identifier (defaults to env var or built-in per provider)"
    )
    api_key: str | None = Field(default=None, description="API key (falls back to config file then env var)")
    max_tokens: int = Field(default=16384, description="Max tokens per LLM call")
    temperature: float = Field(default=0.3, description="LLM temperature")
    base_url: str | None = Field(default=None, description="Custom API base URL")

    def resolve_api_key(self) -> str:
        """Resolve API key: explicit field > config file > env var, or raise."""
        if self.api_key:
            return self.api_key

        # Check ~/.sat/config.json
        file_key = _load_config_file_key(self.provider)
        if file_key:
            return file_key

        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        env_var = env_map.get(self.provider, f"{self.provider.upper()}_API_KEY")
        key = os.environ.get(env_var)
        if not key:
            raise ValueError(
                f"No API key found. Set --api-key, save via Settings UI, "
                f"or set the {env_var} environment variable."
            )
        return key

    def try_resolve_api_key(self) -> str | None:
        """Resolve API key from explicit field, config file, or env var; return None if not found."""
        if self.api_key:
            return self.api_key

        # Check ~/.sat/config.json
        file_key = _load_config_file_key(self.provider)
        if file_key:
            return file_key

        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        env_var = env_map.get(self.provider, f"{self.provider.upper()}_API_KEY")
        return os.environ.get(env_var)

    def resolve_model(self) -> str:
        """Resolve model: explicit value > config file > env var > built-in default."""
        if self.model:
            return self.model

        # Check ~/.sat/config.json
        file_model = _load_config_file_model(self.provider)
        if file_model:
            return file_model

        env_map = {
            "anthropic": "ANTHROPIC_MODEL",
            "openai": "OPENAI_MODEL",
            "gemini": "GEMINI_MODEL",
        }
        env_var = env_map.get(self.provider, f"{self.provider.upper()}_MODEL")
        return os.environ.get(env_var, DEFAULT_MODELS.get(self.provider, "claude-opus-4-6"))


class VerificationConfig(BaseModel):
    """Configuration for source verification."""

    enabled: bool = Field(default=True, description="Enable source verification")
    model: str | None = Field(default=None, description="Override verification model")
    max_sources: int = Field(default=20, description="Max sources to verify")
    timeout: float = Field(default=15.0, description="Per-source fetch timeout in seconds")
    concurrency: int = Field(default=10, description="Max concurrent fetches")


class ResearchConfig(BaseModel):
    """Configuration for deep research phase."""

    enabled: bool = Field(default=False, description="Enable deep research")
    mode: str = Field(default="multi", description="Research mode: 'single' or 'multi'")
    provider: str = Field(
        default="auto",
        description="Research provider: 'perplexity', 'brave', 'llm', 'auto'",
    )
    api_key: str | None = Field(default=None, description="API key for research provider")
    max_sources: int = Field(default=10, description="Maximum sources to retrieve")
    verification: "VerificationConfig" = Field(
        default_factory=lambda: VerificationConfig(),
        description="Source verification configuration",
    )


class PreprocessingConfig(BaseModel):
    """Configuration for evidence preprocessing."""

    enabled: bool = Field(default=True, description="Enable evidence preprocessing")
    budget_fraction: float = Field(
        default=0.4, description="Fraction of context window reserved for evidence"
    )
    max_chunk_tokens: int = Field(
        default=50_000, description="Max estimated tokens per chunk in map-reduce"
    )
    force_format: str | None = Field(
        default=None, description="Override auto-detection with a specific format"
    )


class ReportConfig(BaseModel):
    """Configuration for executive report generation."""

    enabled: bool = Field(default=True, description="Generate executive report after analysis")
    fmt: str = Field(default="both", description="Report format: 'markdown', 'html', or 'both'")


class IngestionConfig(BaseModel):
    """Configuration for multimodal evidence ingestion."""

    enabled: bool = Field(
        default=True, description="Enable Docling-based ingestion for file/URL inputs"
    )
    fetch_timeout: float = Field(default=30.0, description="URL fetch timeout in seconds")
    max_file_size_mb: int = Field(default=50, description="Max file size in MB")
    ocr_enabled: bool = Field(default=True, description="Enable OCR for scanned documents")


class DecompositionConfig(BaseModel):
    """Configuration for atomic fact decomposition."""

    enabled: bool = Field(default=False, description="Enable fact decomposition")
    max_facts: int = Field(default=200, description="Maximum facts to extract")
    chunk_tokens: int = Field(default=30_000, description="Max tokens per decomposition chunk")
    deduplicate: bool = Field(default=True, description="Deduplicate facts across chunks")


class AnalysisConfig(BaseModel):
    """Full analysis run configuration."""

    question: str
    name: str | None = None
    evidence: str | None = None
    techniques: list[str] | None = Field(
        default=None, description="Technique IDs to use (auto-select if None)"
    )
    output_dir: Path = Field(default=Path("."))
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    verbose: bool = False
    json_only: bool = False
    adversarial: AdversarialConfig | None = Field(
        default=None, description="Adversarial analysis configuration"
    )
    report: ReportConfig = Field(default_factory=ReportConfig)
    evidence_sources: list[str] | None = Field(
        default=None, description="File paths or URLs to ingest as evidence"
    )
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    decomposition: DecompositionConfig = Field(default_factory=DecompositionConfig)


__all__ = [
    "ProviderConfig",
    "AnalysisConfig",
    "AdversarialConfig",
    "PreprocessingConfig",
    "ReportConfig",
    "VerificationConfig",
    "IngestionConfig",
    "DecompositionConfig",
    "_get_sat_config_path",
]
