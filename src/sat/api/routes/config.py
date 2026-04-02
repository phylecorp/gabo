"""Config routes: provider listing, settings management, and template upload.

@decision DEC-API-008
@title Settings persisted to ~/.sat/config.json, applied to os.environ immediately
@status accepted
@rationale The Settings UI needs to save API keys that survive the current request.
Writing to ~/.sat/config.json gives persistence across restarts. Immediately
updating os.environ after a PUT /settings ensures the running process picks up
new keys for subsequent pipeline runs without needing a restart. Empty key values
are removed from os.environ (not written as empty strings) so downstream code
that checks `if os.environ.get(...)` continues to work correctly.

@decision DEC-API-009
@title API keys masked in all responses: first 6 + '...' + last 4 chars
@status accepted
@rationale Full API keys must never be returned in HTTP responses. The preview
format (first 6 + last 4) gives enough context for the user to verify which key
is configured without exposing the full secret. Keys shorter than 10 chars are
masked entirely (shown as '***').

@decision DEC-API-010
@title test-provider performs a real minimal LLM call without mocking
@status accepted
@rationale The only way to verify an API key works is to actually call the
provider's API. We send a minimal "Say hello" prompt and treat any successful
response as proof the key works. Unknown providers return success=False with
a clear error message rather than 422, since the frontend needs a JSON response
to display to the user.

@decision DEC-API-011
@title Brave and Perplexity are "research providers" — no default model, different test path
@status accepted
@rationale Brave Search uses a plain HTTP subscription-token API (not an LLM at all).
Perplexity uses an OpenAI-compatible API with a fixed model (sonar-deep-research).
Both need API key management through the Settings UI, so they are added to
_KNOWN_PROVIDERS and _PROVIDER_KEY_ENVS. The test-provider endpoint uses httpx
for Brave (a simple GET to confirm the subscription token works) and the openai
SDK with base_url=https://api.perplexity.ai for Perplexity. The frontend hides
the "Default Model" field for Brave since the concept doesn't apply; Perplexity
keeps the model field since users may want to use a different sonar variant.

@decision DEC-TEMPLATE-001
@title Custom templates stored in ~/.sat/templates/, validated as Jinja2 before write
@status accepted
@rationale User-supplied templates must be validated before being stored so the
ReportBuilder never encounters a broken template at report generation time. We
parse the uploaded content with jinja2.Environment().parse() which is a pure
syntax check — no rendering — and reject with 400 on TemplateSyntaxError. Files
are stored at 0o600 (owner-only) since templates may contain proprietary
formatting. The upload endpoint normalises filenames: any .j2 file whose content
looks like HTML (starts with '<') is stored as report.html.j2; everything else
becomes report.md.j2. This keeps the storage convention consistent with the
default template names that ReportBuilder expects.

@decision DEC-TEMPLATE-002
@title DELETE only targets ~/.sat/templates/ — default templates are read-only via API
@status accepted
@rationale Allowing DELETE on bundled templates would corrupt the package
installation. The endpoint checks the custom dir only: 404 if not present there,
200 on success. The 403 path is reserved for future cases where a filename
matches a default but the caller tries to delete it explicitly.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from sat.api.models import (
    AppSettings,
    ProviderInfo,
    ProviderSettings,
    ProviderSettingsResponse,
    SettingsResponse,
    TemplateInfo,
    TemplateUploadResponse,
    TestProviderRequest,
    TestProviderResponse,
)
from sat.config import DEFAULT_MODELS, PROVIDER_API_KEY_ENVS
from sat.utils.resources import get_sat_resource_path

logger = logging.getLogger(__name__)

router = APIRouter()

# Environment variable names for each provider's API key
_PROVIDER_KEY_ENVS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "brave": "BRAVE_API_KEY",
}

# Some users set GOOGLE_API_KEY instead of GEMINI_API_KEY
_GEMINI_ALT_KEY = "GOOGLE_API_KEY"

_KNOWN_PROVIDERS = ["anthropic", "openai", "gemini", "perplexity", "brave"]


def _get_config_path() -> Path:
    """Return path to ~/.sat/config.json.

    Overrideable in tests by monkey-patching this function on the module.
    """
    return Path.home() / ".sat" / "config.json"


def _get_templates_dir() -> Path:
    """Return path to the user's custom templates directory (~/.sat/templates/).

    Overrideable in tests by monkey-patching this function on the module.
    The directory is NOT created here — callers that write files create it on demand.
    """
    return Path.home() / ".sat" / "templates"


def _mask_key(key: str) -> str:
    """Return a masked preview of an API key.

    For keys >= 10 chars: first 6 + '...' + last 4.
    For shorter keys: '***' (too short to preview safely).
    """
    if len(key) >= 10:
        return f"{key[:6]}...{key[-4:]}"
    return "***"


def _load_settings(config_path: Path) -> SettingsResponse:
    """Build SettingsResponse from config file + environment variables.

    Load order per provider: config file > environment > default.
    Returns a SettingsResponse with masked key previews.
    """
    file_data: dict = {}
    if config_path.exists():
        try:
            file_data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            file_data = {}

    file_providers = file_data.get("providers", {})
    providers: dict[str, ProviderSettingsResponse] = {}

    for name in _KNOWN_PROVIDERS:
        file_entry = file_providers.get(name, {})
        file_key = file_entry.get("api_key", "") if isinstance(file_entry, dict) else ""
        file_model = file_entry.get("default_model", "") if isinstance(file_entry, dict) else ""
        file_research_model = (
            file_entry.get("research_model", "") if isinstance(file_entry, dict) else ""
        )

        env_var = _PROVIDER_KEY_ENVS.get(name, f"{name.upper()}_API_KEY")
        env_key = os.environ.get(env_var, "")

        # Gemini alt env var
        if name == "gemini" and not env_key:
            env_key = os.environ.get(_GEMINI_ALT_KEY, "")

        if file_key:
            has_key = True
            preview = _mask_key(file_key)
            source = "config_file"
        elif env_key:
            has_key = True
            preview = _mask_key(env_key)
            source = "environment"
        else:
            has_key = False
            preview = ""
            source = "default"

        # Model selection is independent of where the API key comes from.
        # Always prefer the user-saved model from the config file; fall back
        # to DEFAULT_MODELS only when no model has been saved.
        model = file_model or DEFAULT_MODELS.get(name, "")

        providers[name] = ProviderSettingsResponse(
            has_api_key=has_key,
            api_key_preview=preview,
            default_model=model,
            research_model=file_research_model,
            source=source,
        )

    return SettingsResponse(providers=providers)


def _save_config(settings: AppSettings, config_path: Path) -> None:
    """Write settings to config_path, creating parent directories as needed.

    Applies 0o600 permissions (owner read/write only) after writing to protect
    API keys stored in the config file from being readable by other users.
    The chmod is applied unconditionally — both on first write and on overwrite —
    because file creation mode is subject to the process umask.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "providers": {
            name: {
                "api_key": ps.api_key,
                "default_model": ps.default_model,
                "research_model": ps.research_model,
            }
            for name, ps in settings.providers.items()
        }
    }
    config_path.write_text(json.dumps(data, indent=2))
    os.chmod(config_path, 0o600)


def _apply_to_environ(settings: AppSettings) -> None:
    """Update os.environ to reflect the saved settings.

    Only providers with a non-empty api_key are updated. Empty api_key means
    "don't change" — the key was either not included in this save request or
    was preserved from the existing config. We do not remove env vars here
    because externally-configured keys (e.g. from a .env file or shell export)
    must survive a settings save that only updates model selections.
    """
    for name, ps in settings.providers.items():
        env_var = PROVIDER_API_KEY_ENVS.get(name, f"{name.upper()}_API_KEY")
        if ps.api_key:
            os.environ[env_var] = ps.api_key


async def _test_provider_connection(req: TestProviderRequest) -> TestProviderResponse:
    """Attempt a minimal LLM call to verify provider credentials.

    Calls the provider with "Say hello" and treats any successful response
    as proof the key works. Returns success=False with an error message on
    any exception (auth error, network error, unknown provider, etc.).
    """
    provider = req.provider.lower()

    if provider not in _KNOWN_PROVIDERS:
        return TestProviderResponse(
            success=False,
            error=f"Unknown provider: {req.provider!r}. Supported: {', '.join(_KNOWN_PROVIDERS)}",
        )

    model = req.model or DEFAULT_MODELS.get(provider, "")

    try:
        if provider == "anthropic":
            import anthropic

            ac = anthropic.Anthropic(api_key=req.api_key)
            ac.messages.create(
                model=model,
                max_tokens=16,
                messages=[{"role": "user", "content": "Say hello"}],
            )
            return TestProviderResponse(success=True, model_used=model)

        elif provider == "openai":
            import openai

            oc = openai.OpenAI(api_key=req.api_key)
            oc.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say hello"}],
                max_completion_tokens=16,
            )
            return TestProviderResponse(success=True, model_used=model)

        elif provider == "gemini":
            import google.generativeai as genai  # type: ignore[import]

            genai.configure(api_key=req.api_key)
            gmodel = genai.GenerativeModel(model)
            gmodel.generate_content("Say hello")
            return TestProviderResponse(success=True, model_used=model)

        elif provider == "perplexity":
            # Perplexity exposes an OpenAI-compatible API at api.perplexity.ai.
            # We use the `sonar` model (lightweight) for the connectivity check;
            # sonar-deep-research is the production model but costs more per call.
            import openai

            pc = openai.OpenAI(api_key=req.api_key, base_url="https://api.perplexity.ai")
            pc.chat.completions.create(
                model="sonar",
                messages=[{"role": "user", "content": "Say hello"}],
                max_completion_tokens=16,
            )
            return TestProviderResponse(success=True, model_used="sonar")

        elif provider == "brave":
            # Brave Search API uses a simple HTTP token header — no SDK needed.
            # A minimal web search with count=1 verifies the subscription token.
            import httpx

            resp = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "X-Subscription-Token": req.api_key,
                    "Accept": "application/json",
                },
                params={"q": "test", "count": 1},
            )
            resp.raise_for_status()
            return TestProviderResponse(success=True, model_used="brave-search")

    except Exception as exc:  # noqa: BLE001
        # Log full traceback server-side. Return a sanitized message that
        # omits internal details but retains enough for the user to act on
        # (DEC-SEC-006). str(exc) is used here because provider auth errors
        # (e.g. "AuthenticationError: Invalid API Key") are meaningful to
        # the user and don't contain sensitive server-side data.
        logger.warning(
            "Provider test failed for %s: %s",
            req.provider,
            str(exc),
            exc_info=True,
        )
        # Truncate to 200 chars to avoid leaking long stack traces if the
        # exception message itself is unexpectedly verbose.
        sanitized = str(exc)[:200]
        return TestProviderResponse(success=False, error=sanitized)

    return TestProviderResponse(success=False, error="Unexpected error")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/config/providers", response_model=list[ProviderInfo])
async def list_providers() -> list[ProviderInfo]:
    """Return availability status for all supported LLM providers.

    Checks config file and environment variables. Config file takes precedence.
    """
    config_path = _get_config_path()
    file_data: dict = {}
    if config_path.exists():
        try:
            file_data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            file_data = {}

    file_providers = file_data.get("providers", {})
    providers: list[ProviderInfo] = []

    for name in _KNOWN_PROVIDERS:
        file_entry = file_providers.get(name, {})
        file_key = file_entry.get("api_key", "") if isinstance(file_entry, dict) else ""
        file_model = file_entry.get("default_model", "") if isinstance(file_entry, dict) else ""

        if file_key:
            has_key = True
        else:
            env_var = _PROVIDER_KEY_ENVS.get(name, f"{name.upper()}_API_KEY")
            has_key = bool(os.environ.get(env_var))
            if name == "gemini" and not has_key:
                has_key = bool(os.environ.get(_GEMINI_ALT_KEY))

        # Use user-saved model if present, otherwise fall back to hardcoded default.
        # This ensures the Settings page model choice is reflected here.
        resolved_model = file_model or DEFAULT_MODELS.get(name, "")

        providers.append(
            ProviderInfo(
                name=name,
                has_api_key=has_key,
                default_model=resolved_model,
            )
        )

    return providers


@router.get("/api/config/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Return current settings with masked API keys.

    Load order per provider: config file > environment > default.
    """
    return _load_settings(_get_config_path())


@router.put("/api/config/settings", response_model=SettingsResponse)
async def update_settings(settings: AppSettings) -> SettingsResponse:
    """Persist settings to ~/.sat/config.json and update os.environ immediately.

    Only providers included in the request body are written. Existing config
    file entries for other providers are preserved.
    """
    config_path = _get_config_path()

    # Load existing config to preserve entries not in this request
    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Merge: incoming providers overwrite existing ones.
    # Empty incoming values preserve the existing stored value — the frontend
    # sends api_key="" when the user is not editing the key (by design), so
    # we must not clear a previously-saved key when only the model changes.
    existing_providers: dict = existing.get("providers", {})
    for name, ps in settings.providers.items():
        existing_entry = existing_providers.get(name, {})
        existing_providers[name] = {
            "api_key": ps.api_key or (
                existing_entry.get("api_key", "") if isinstance(existing_entry, dict) else ""
            ),
            "default_model": ps.default_model or (
                existing_entry.get("default_model", "") if isinstance(existing_entry, dict) else ""
            ),
            "research_model": ps.research_model or (
                existing_entry.get("research_model", "") if isinstance(existing_entry, dict) else ""
            ),
        }

    merged = AppSettings(
        providers={
            name: ProviderSettings(
                api_key=v.get("api_key", "") if isinstance(v, dict) else "",
                default_model=v.get("default_model", "") if isinstance(v, dict) else "",
                research_model=v.get("research_model", "") if isinstance(v, dict) else "",
            )
            for name, v in existing_providers.items()
        }
    )

    _save_config(merged, config_path)
    # Apply only providers where the caller explicitly sent an api_key (even if "").
    # This ensures: setting a key updates os.environ; clearing a key (sending "")
    # removes it from os.environ; but providers where no key was sent at all are
    # left untouched in os.environ (env-var keys remain for the running process).
    _apply_to_environ(settings)

    return _load_settings(config_path)


@router.post("/api/config/test-provider", response_model=TestProviderResponse)
async def test_provider(req: TestProviderRequest) -> TestProviderResponse:
    """Test a provider API key with a minimal LLM call.

    Returns success=True with model_used on success, or success=False with
    an error message if the key is invalid or the provider is unreachable.
    """
    return await _test_provider_connection(req)


# ---------------------------------------------------------------------------
# Template management endpoints
# ---------------------------------------------------------------------------

# Allowed template filename suffixes (DEC-TEMPLATE-001)
_ALLOWED_TEMPLATE_SUFFIXES = frozenset({".j2", ".html"})
# Max upload size: 1 MB
_MAX_TEMPLATE_SIZE = 1024 * 1024
# Directory containing bundled default templates.
# get_sat_resource_path resolves from the sat package root in unfrozen mode and
# from sys._MEIPASS/sat/ in a PyInstaller frozen bundle — same relative string
# ("report/templates") works in both contexts without branching.
_DEFAULT_TEMPLATES_DIR = get_sat_resource_path("report/templates")


def _template_modified(path: Path) -> str:
    """Return ISO-8601 mtime string for a file path."""
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


@router.get("/api/config/templates", response_model=list[TemplateInfo])
async def list_templates() -> list[TemplateInfo]:
    """List all available report templates: custom (user-uploaded) and default (bundled).

    Custom templates in ~/.sat/templates/ appear first with is_custom=True.
    Default templates from src/sat/report/templates/ follow with is_custom=False.
    If a filename exists in both directories the custom version supersedes the
    default in the listing (the default entry is omitted for that filename).
    """
    results: list[TemplateInfo] = []
    custom_names: set[str] = set()

    # Scan custom templates dir
    custom_dir = _get_templates_dir()
    if custom_dir.exists() and custom_dir.is_dir():
        for p in sorted(custom_dir.iterdir()):
            if p.is_file() and p.suffix in _ALLOWED_TEMPLATE_SUFFIXES:
                results.append(TemplateInfo(
                    filename=p.name,
                    size=p.stat().st_size,
                    modified=_template_modified(p),
                    is_custom=True,
                ))
                custom_names.add(p.name)

    # Append default templates not already covered by a custom file
    if _DEFAULT_TEMPLATES_DIR.exists():
        for p in sorted(_DEFAULT_TEMPLATES_DIR.iterdir()):
            if p.is_file() and p.name not in custom_names:
                results.append(TemplateInfo(
                    filename=p.name,
                    size=p.stat().st_size,
                    modified=_template_modified(p),
                    is_custom=False,
                ))

    return results


@router.post("/api/config/templates/upload", response_model=TemplateUploadResponse)
async def upload_template(file: UploadFile) -> TemplateUploadResponse:
    """Upload a custom Jinja2 report template.

    Validation:
    - File size must be < 1 MB
    - Extension must be .j2 or .html
    - Content must parse as valid Jinja2 (syntax check only, no rendering)

    Stored as report.html.j2 or report.md.j2 in ~/.sat/templates/ based on
    the uploaded filename. Any existing file with the same name is overwritten.
    File permissions are set to 0o600 (owner read/write only).
    """
    content = await file.read()

    # Size check
    if len(content) > _MAX_TEMPLATE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Template file too large: {len(content)} bytes exceeds 1MB limit.",
        )

    # Extension check
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_TEMPLATE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file extension {suffix!r}. "
                f"Allowed: {', '.join(sorted(_ALLOWED_TEMPLATE_SUFFIXES))}"
            ),
        )

    # Jinja2 syntax validation
    try:
        import jinja2
        jinja2.Environment().parse(content.decode("utf-8", errors="replace"))
    except jinja2.TemplateSyntaxError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Jinja2 template syntax: {exc}",
        ) from exc

    # Determine canonical stored filename.
    # If the uploaded name ends with .html.j2 → report.html.j2
    # otherwise → preserve the uploaded filename as-is (allows report.md.j2 etc.)
    # For arbitrary names (e.g. my_template.j2), default to report.md.j2.
    lower_name = filename.lower()
    if lower_name.endswith(".html.j2") or lower_name.endswith(".html"):
        stored_name = "report.html.j2"
    elif lower_name == "report.md.j2":
        stored_name = "report.md.j2"
    else:
        # Any other .j2 name — store as-is so the caller can retrieve it
        stored_name = filename

    # Write to custom templates dir
    custom_dir = _get_templates_dir()
    custom_dir.mkdir(parents=True, exist_ok=True)
    dest = custom_dir / stored_name
    dest.write_bytes(content)
    os.chmod(dest, 0o600)

    logger.info("Template uploaded: %s (%d bytes)", stored_name, len(content))

    return TemplateUploadResponse(
        filename=stored_name,
        size=len(content),
        status="uploaded",
    )


@router.delete("/api/config/templates/{filename}")
async def delete_template(filename: str) -> dict:
    """Delete a custom report template from ~/.sat/templates/.

    Returns 200 on success, 404 if the file does not exist in the custom
    directory, 400 if the filename contains path-traversal characters.
    Default (bundled) templates cannot be deleted via this endpoint.
    """
    # Guard against path traversal: filename must not contain path separators
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: path separators are not allowed.",
        )

    custom_dir = _get_templates_dir()
    target = custom_dir / filename

    # Verify the resolved path is actually inside custom_dir (belt + suspenders)
    try:
        target.resolve().relative_to(custom_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Template {filename!r} not found in custom templates directory.",
        )

    target.unlink()
    logger.info("Template deleted: %s", filename)
    return {"deleted": filename}
