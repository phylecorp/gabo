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

@decision DEC-CFG-004
@title DEFAULT_RESEARCH_MODELS and resolve_research_model for research-specific model selection
@status accepted
@rationale Research providers (perplexity, openai, gemini) use distinct models optimised
for deep-research tasks (e.g. o3-deep-research-2025-06-26, sonar-deep-research). Keeping
these separate from DEFAULT_MODELS avoids conflating analysis-model defaults with
research-model defaults. resolve_research_model() follows the same three-tier chain as
resolve_model(): config.json research_model field > env var > built-in default.
The env var convention is <PROVIDER_UPPER>_RESEARCH_MODEL (e.g. OPENAI_RESEARCH_MODEL).
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
    # Local defaults are empty — model is chosen from whatever is installed/loaded.
    "ollama": "",
    "lmstudio": "",
}

DEFAULT_BASE_URLS = {
    "ollama": "http://127.0.0.1:11434",
    "lmstudio": "http://127.0.0.1:1234",
}

LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio"})

# Curated model lists for providers without a model listing API.
# These are used both as the primary list (Anthropic, Perplexity) and as
# fallback when the API listing fails (OpenAI, Gemini).
#
# @decision DEC-MODELS-001 (see MASTER_PLAN.md)
# Hybrid model listing: API-fetched for OpenAI/Gemini, curated for Anthropic/Perplexity.
# Curated lists also serve as fallback when API calls fail.
ANTHROPIC_ANALYSIS_MODELS = [
    {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "default": True},
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
    {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
]
ANTHROPIC_RESEARCH_MODELS: list[dict] = []

PERPLEXITY_RESEARCH_MODELS = [
    {"id": "sonar-deep-research", "name": "Sonar Deep Research", "default": True},
    {"id": "sonar-pro", "name": "Sonar Pro"},
    {"id": "sonar", "name": "Sonar"},
    {"id": "sonar-reasoning-pro", "name": "Sonar Reasoning Pro"},
    {"id": "sonar-reasoning", "name": "Sonar Reasoning"},
]
PERPLEXITY_ANALYSIS_MODELS: list[dict] = []

# Fallback lists for OpenAI and Gemini when API listing fails
OPENAI_ANALYSIS_MODELS_FALLBACK = [
    {"id": "o3", "name": "O3", "default": True},
    {"id": "gpt-4o", "name": "GPT-4o"},
    {"id": "gpt-4.1", "name": "GPT-4.1"},
    {"id": "o4-mini", "name": "O4 Mini"},
]
OPENAI_RESEARCH_MODELS_FALLBACK = [
    {"id": "o3-deep-research-2025-06-26", "name": "O3 Deep Research", "default": True},
    {"id": "o4-mini-deep-research-2025-06-26", "name": "O4 Mini Deep Research"},
]

GEMINI_ANALYSIS_MODELS_FALLBACK = [
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "default": True},
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
]
GEMINI_RESEARCH_MODELS_FALLBACK = [
    {"id": "deep-research-pro-preview-12-2025", "name": "Deep Research Pro", "default": True},
]

# Simple string defaults for research model resolution (used by resolve_research_model()).
# Note: PERPLEXITY_RESEARCH_MODELS above provides the curated list for the UI;
# DEFAULT_RESEARCH_MODELS is the string fallback for the three-tier resolve chain.
DEFAULT_RESEARCH_MODELS = {
    "perplexity": "sonar-deep-research",
    "openai": "o3-deep-research-2025-06-26",
    "gemini": "deep-research-pro-preview-12-2025",
}

CHALLENGER_PREFERENCE = {
    "anthropic": ["openai", "gemini", "ollama", "lmstudio"],
    "openai": ["anthropic", "gemini", "ollama", "lmstudio"],
    "gemini": ["anthropic", "openai", "ollama", "lmstudio"],
    "ollama": ["anthropic", "openai", "gemini", "lmstudio"],
    "lmstudio": ["anthropic", "openai", "gemini", "ollama"],
}

PROVIDER_API_KEY_ENVS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "brave": "BRAVE_API_KEY",
    # Optional — Ollama ignores keys; LM Studio uses a Bearer token when auth is enabled.
    "ollama": "OLLAMA_API_KEY",
    "lmstudio": "LMSTUDIO_API_KEY",
}

PROVIDER_BASE_URL_ENVS = {
    "ollama": "OLLAMA_BASE_URL",
    "lmstudio": "LMSTUDIO_BASE_URL",
}


def _get_style_guide_path() -> Path:
    """Return path to ~/.sat/style_guide.md.

    Overrideable in tests by monkey-patching this function on the module.
    """
    return Path.home() / ".sat" / "style_guide.md"


def _get_exemplar_path() -> Path:
    """Return path to ~/.sat/exemplar.md.

    Overrideable in tests by monkey-patching this function on the module.
    """
    return Path.home() / ".sat" / "exemplar.md"


def load_style_guide() -> str | None:
    """Read ~/.sat/style_guide.md if present, return contents or None.

    Returns None if the file does not exist, cannot be read, or is blank.
    The path is resolved via _get_style_guide_path() so tests can redirect it.
    """
    path = _get_style_guide_path()
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text if text else None
    except OSError:
        return None


def load_exemplar() -> str | None:
    """Read ~/.sat/exemplar.md if present, return contents or None.

    Returns None if the file does not exist, cannot be read, or is blank.
    The path is resolved via _get_exemplar_path() so tests can redirect it.
    """
    path = _get_exemplar_path()
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text if text else None
    except OSError:
        return None


def get_default_runs_dir() -> Path:
    """Return the stable directory for analysis run output.

    @decision DEC-RUNS-001
    @title Use ~/.sat/runs/ as the stable write location for analysis runs
    @status accepted
    @rationale In packaged Electron apps on macOS, the CWD is typically '/'
    (inherited from the OS launcher via Finder or launchd). Writing run output
    relative to CWD causes 'Permission denied' errors and produces runs that
    disappear after an app restart because the CWD may change. ~/.sat/runs/ is
    always writable by the running user, stable across restarts, and consistent
    between dev and packaged modes.

    The function creates the directory on first call (mode 0o700) so no manual
    setup is required by users or CI. For tests and CI environments, the
    SAT_RUNS_DIR environment variable overrides the default location without
    requiring any internal patching.

    CLI callers that explicitly pass output_dir are unaffected — the default
    only applies when output_dir is None (i.e. omitted by the API client).
    """
    env_override = os.environ.get("SAT_RUNS_DIR")
    if env_override:
        runs_dir = Path(env_override)
    else:
        runs_dir = Path.home() / ".sat" / "runs"
    runs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return runs_dir


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


def _load_config_file_base_url(provider: str) -> str | None:
    """Read the base_url for *provider* from ~/.sat/config.json, if present."""
    config_path = _get_sat_config_path()
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
        base_url = data.get("providers", {}).get(provider, {}).get("base_url", "")
        return base_url if base_url else None
    except (json.JSONDecodeError, OSError):
        return None


class TechniqueOverride(BaseModel):
    """Per-technique configuration override (model and/or temperature).

    @decision DEC-TECH-OVERRIDE-001
    @title Per-technique model and temperature overrides from ~/.sat/config.json
    @status accepted
    @rationale Analysts may want different models or temperatures for specific techniques
      without changing the global provider config. For example, use claude-opus for creative
      techniques but gpt-4o for analytical ones. Stored under the technique_overrides key
      in ~/.sat/config.json as a dict keyed by technique ID. Both fields are optional so
      users can override one without specifying the other. Temperature range 0.0-2.0
      mirrors the OpenAI/Anthropic API constraint.
    """

    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


def load_technique_overrides() -> dict[str, TechniqueOverride]:
    """Load per-technique overrides from ~/.sat/config.json technique_overrides key.

    Returns empty dict if no overrides configured or on any error (missing file,
    malformed JSON, OS error). This is intentionally defensive — a bad config
    file must not break the pipeline.

    The config path is resolved via _get_sat_config_path() so tests can redirect
    it via monkeypatch without touching the real ~/.sat directory.
    """
    config_path = _get_sat_config_path()
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text())
        raw = data.get("technique_overrides", {})
        return {
            tid: TechniqueOverride.model_validate(cfg)
            for tid, cfg in raw.items()
            if isinstance(cfg, dict)
        }
    except (json.JSONDecodeError, OSError):
        return {}


class AdversarialDefaults(BaseModel):
    """Persistent adversarial analysis defaults from ~/.sat/config.json 'adversarial' key.

    @decision DEC-ADV-DEFAULTS-001
    @title AdversarialDefaults loaded from config file adversarial key
    @status accepted
    @rationale Persistent adversarial defaults let users configure their preferred
      mode, rounds, and provider overrides once rather than repeating CLI flags or
      API parameters. The defaults are layered under the existing adversarial config
      build logic — explicit call arguments always win. All fields are Optional so
      a partial config or missing config file gracefully produces empty defaults.
    """

    enabled: bool | None = None
    mode: str | None = None
    rounds: int | None = Field(default=None, ge=1, le=5)
    challenger_provider: str | None = None
    challenger_model: str | None = None
    investigator_provider: str | None = None
    investigator_model: str | None = None


def load_adversarial_defaults() -> AdversarialDefaults:
    """Load adversarial defaults from ~/.sat/config.json 'adversarial' key.

    Returns empty AdversarialDefaults (all fields None) if:
    - The config file does not exist
    - The file is malformed JSON
    - The 'adversarial' key is missing or not a dict
    - Any OS or parse error occurs

    This is intentionally defensive — a bad config file must not break the
    pipeline. The config path is resolved via _get_sat_config_path() so tests
    can redirect it via monkeypatch without touching the real ~/.sat directory.
    """
    config_path = _get_sat_config_path()
    if not config_path.exists():
        return AdversarialDefaults()
    try:
        data = json.loads(config_path.read_text())
        raw = data.get("adversarial", {})
        if not isinstance(raw, dict):
            return AdversarialDefaults()
        return AdversarialDefaults.model_validate(raw)
    except (json.JSONDecodeError, OSError, Exception):
        return AdversarialDefaults()


def _load_config_file_research_model(provider: str) -> str | None:
    """Read the research_model for *provider* from ~/.sat/config.json, if present.

    Returns None if the config file doesn't exist, the provider is not present,
    or the research_model field is absent or empty.
    """
    config_path = _get_sat_config_path()
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
        model = data.get("providers", {}).get(provider, {}).get("research_model", "")
        return model if model else None
    except (json.JSONDecodeError, OSError):
        return None


def resolve_research_model(provider: str) -> str:
    """Resolve the research model for *provider* using a three-tier fallback chain.

    Priority order:
    1. research_model field in ~/.sat/config.json for the provider
    2. <PROVIDER_UPPER>_RESEARCH_MODEL environment variable
    3. DEFAULT_RESEARCH_MODELS built-in default for the provider

    Returns an empty string for unknown providers not in DEFAULT_RESEARCH_MODELS.
    """
    # Tier 1: config file
    file_model = _load_config_file_research_model(provider)
    if file_model:
        return file_model

    # Tier 2: environment variable
    env_var = f"{provider.upper()}_RESEARCH_MODEL"
    env_model = os.environ.get(env_var, "")
    if env_model:
        return env_model

    # Tier 3: built-in default (empty string for unknown providers)
    return DEFAULT_RESEARCH_MODELS.get(provider, "")


def _provider_has_credentials(provider: str) -> bool:
    """Return True if *provider* looks configured for use.

    Cloud providers need an API key. Local providers (ollama, lmstudio) are
    considered available when a base URL is configured or the built-in default
    host applies — reachability is checked at request / Settings probe time.
    """
    if provider in LOCAL_PROVIDERS:
        return True
    env_var = PROVIDER_API_KEY_ENVS.get(provider, f"{provider.upper()}_API_KEY")
    return bool(os.environ.get(env_var)) or bool(_load_config_file_key(provider))


def resolve_challenger_provider(primary_provider: str) -> tuple[str, str] | None:
    """Find the best available challenger provider different from primary.

    Checks env vars and config file to find a provider with an API key configured
    (or a local provider, which needs no cloud key).
    Returns (provider_name, resolved_model) or None if no other provider available.
    """
    preferences = CHALLENGER_PREFERENCE.get(
        primary_provider, ["anthropic", "openai", "gemini", "ollama", "lmstudio"]
    )
    for candidate in preferences:
        if candidate == primary_provider:
            continue
        if _provider_has_credentials(candidate):
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
    - Has credentials configured (API key for cloud; local hosts always qualify)

    Returns (provider_name, resolved_model) or None if no third provider available.
    """
    all_providers = ["anthropic", "openai", "gemini", "ollama", "lmstudio"]
    for candidate in all_providers:
        if candidate == primary_provider or candidate == challenger_provider:
            continue
        if _provider_has_credentials(candidate):
            resolved = ProviderConfig(provider=candidate).resolve_model()
            return (candidate, resolved)
    return None


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    provider: str = Field(default="anthropic", description="LLM provider name")
    model: str | None = Field(
        default=None, description="Model identifier (defaults to env var or built-in per provider)"
    )
    api_key: str | None = Field(
        default=None, description="API key (falls back to config file then env var)"
    )
    max_tokens: int = Field(default=16384, description="Max tokens per LLM call")
    temperature: float = Field(default=0.3, description="LLM temperature")
    base_url: str | None = Field(default=None, description="Custom API base URL")

    def resolve_api_key(self) -> str:
        """Resolve API key: explicit field > config file > env var, or raise.

        Local providers (ollama, lmstudio) do not require a key — returns "" when
        none is configured so callers can still construct a client.
        """
        key = self.try_resolve_api_key()
        if key:
            return key
        if self.provider in LOCAL_PROVIDERS:
            return ""
        env_var = PROVIDER_API_KEY_ENVS.get(
            self.provider, f"{self.provider.upper()}_API_KEY"
        )
        raise ValueError(
            f"No API key found. Set --api-key, save via Settings UI, "
            f"or set the {env_var} environment variable."
        )

    def try_resolve_api_key(self) -> str | None:
        """Resolve API key from explicit field, config file, or env var; return None if not found."""
        if self.api_key:
            return self.api_key

        # Check ~/.sat/config.json
        file_key = _load_config_file_key(self.provider)
        if file_key:
            return file_key

        env_var = PROVIDER_API_KEY_ENVS.get(
            self.provider, f"{self.provider.upper()}_API_KEY"
        )
        return os.environ.get(env_var)

    def resolve_base_url(self) -> str | None:
        """Resolve base URL: explicit field > config file > env var > built-in default.

        Returns None for cloud providers with no custom URL. Local providers always
        resolve to at least the built-in default host.
        """
        if self.base_url:
            return self.base_url

        file_url = _load_config_file_base_url(self.provider)
        if file_url:
            return file_url

        env_var = PROVIDER_BASE_URL_ENVS.get(self.provider)
        if env_var:
            env_url = os.environ.get(env_var, "")
            if env_url:
                return env_url

        return DEFAULT_BASE_URLS.get(self.provider)

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
            "ollama": "OLLAMA_MODEL",
            "lmstudio": "LMSTUDIO_MODEL",
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


class GapResolutionConfig(BaseModel):
    """Configuration for iterative gap-driven research."""

    enabled: bool = Field(default=True, description="Enable gap resolution after initial research")
    max_iterations: int = Field(default=3, description="Maximum gap resolution iterations")
    max_sources_per_iteration: int = Field(
        default=10, description="Max sources per follow-up query"
    )
    query_timeout: float = Field(
        default=300.0,
        description=(
            "Per-query timeout in seconds for gap resolution follow-up queries (default 5 min). "
            "Gap queries are lightweight supplements, not deep research — 300s is generous."
        ),
    )


class ResearchConfig(BaseModel):
    """Configuration for deep research phase."""

    enabled: bool = Field(default=False, description="Enable deep research")
    mode: str = Field(default="multi", description="Research mode: 'single' or 'multi'")
    provider: str = Field(
        default="auto",
        description="Research provider: 'perplexity', 'brave', 'llm', 'auto'",
    )
    api_key: str | None = Field(default=None, description="API key for research provider")
    max_sources: int = Field(default=20, description="Maximum sources to retrieve")
    verification: "VerificationConfig" = Field(
        default_factory=lambda: VerificationConfig(),
        description="Source verification configuration",
    )
    gap_resolution: "GapResolutionConfig" = Field(
        default_factory=lambda: GapResolutionConfig(),
        description="Gap-driven iterative research configuration",
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
    output_dir: Path | None = Field(default=None, description="Output directory (None = ~/.sat/runs/)")
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
    "get_default_runs_dir",
    "ProviderConfig",
    "AnalysisConfig",
    "AdversarialConfig",
    "PreprocessingConfig",
    "ReportConfig",
    "VerificationConfig",
    "IngestionConfig",
    "DecompositionConfig",
    # Per-technique model/temperature overrides (DEC-TECH-OVERRIDE-001)
    "TechniqueOverride",
    "load_technique_overrides",
    # Adversarial persistent defaults (DEC-ADV-DEFAULTS-001)
    "AdversarialDefaults",
    "load_adversarial_defaults",
    # Style guide and exemplar loaders
    "load_style_guide",
    "load_exemplar",
    "_get_style_guide_path",
    "_get_exemplar_path",
    # Research model resolution (DEC-CFG-004)
    "DEFAULT_RESEARCH_MODELS",
    "resolve_research_model",
    "_get_sat_config_path",
    "_load_config_file_research_model",
    # Curated model lists (DEC-MODELS-001)
    "ANTHROPIC_ANALYSIS_MODELS",
    "ANTHROPIC_RESEARCH_MODELS",
    "PERPLEXITY_ANALYSIS_MODELS",
    "PERPLEXITY_RESEARCH_MODELS",
    "OPENAI_ANALYSIS_MODELS_FALLBACK",
    "OPENAI_RESEARCH_MODELS_FALLBACK",
    "GEMINI_ANALYSIS_MODELS_FALLBACK",
    "GEMINI_RESEARCH_MODELS_FALLBACK",
]
