"""Tests for electron-builder config, package.json scripts, and build helpers.

Validates that W2-1 (issue #23) deliverables are correct:
- electron-builder.yml is valid YAML with required Mac + Windows sections
- package.json scripts include dist:mac and dist:win targets
- scripts/build-sidecar.py is syntactically valid Python
- .gitignore covers the pyinstaller output directories

@decision DEC-BUILD-004
@title Separate dist:mac and dist:win scripts, no cross-compilation
@status accepted
@rationale PyInstaller cannot cross-compile; each platform must build natively.
Separate npm scripts make the intent explicit and allow CI matrix to call
the correct script per runner OS. The underlying pyinstaller command is
identical (auto-detects OS), but the scripts are named for clarity.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
DESKTOP_DIR = REPO_ROOT / "desktop"
ELECTRON_BUILDER_YML = DESKTOP_DIR / "electron-builder.yml"
PACKAGE_JSON = DESKTOP_DIR / "package.json"
DESKTOP_GITIGNORE = DESKTOP_DIR / ".gitignore"
BUILD_SIDECAR_SCRIPT = REPO_ROOT / "scripts" / "build-sidecar.py"


# ---------------------------------------------------------------------------
# electron-builder.yml tests
# ---------------------------------------------------------------------------


def test_electron_builder_yml_is_valid_yaml():
    """electron-builder.yml must parse without errors."""
    content = ELECTRON_BUILDER_YML.read_text()
    config = yaml.safe_load(content)
    assert isinstance(config, dict), "electron-builder.yml should parse to a dict"


def test_electron_builder_has_app_id():
    """appId is required for electron-builder to generate installer metadata."""
    config = yaml.safe_load(ELECTRON_BUILDER_YML.read_text())
    assert "appId" in config, "electron-builder.yml must define appId"
    assert config["appId"], "appId must be non-empty"


def test_electron_builder_has_mac_section():
    """mac section is required for DMG generation."""
    config = yaml.safe_load(ELECTRON_BUILDER_YML.read_text())
    assert "mac" in config, "electron-builder.yml must have a mac section"
    mac = config["mac"]
    assert "target" in mac, "mac section must define target"
    # Verify DMG target is present
    targets = mac["target"]
    target_names = [
        t["target"] if isinstance(t, dict) else t for t in (targets if isinstance(targets, list) else [targets])
    ]
    assert "dmg" in target_names, f"mac must target dmg, got: {target_names}"


def test_electron_builder_has_win_section():
    """win section with NSIS target is required for Windows installer generation."""
    config = yaml.safe_load(ELECTRON_BUILDER_YML.read_text())
    assert "win" in config, "electron-builder.yml must have a win section"
    win = config["win"]
    assert "target" in win, "win section must define target"
    targets = win["target"]
    target_names = [
        t["target"] if isinstance(t, dict) else t for t in (targets if isinstance(targets, list) else [targets])
    ]
    assert "nsis" in target_names, f"win must target nsis, got: {target_names}"


def test_electron_builder_nsis_section():
    """nsis section must be configured with installer customizations."""
    config = yaml.safe_load(ELECTRON_BUILDER_YML.read_text())
    assert "nsis" in config, "electron-builder.yml must have an nsis section"
    nsis = config["nsis"]
    # oneClick: false means the user can choose installation directory
    assert nsis.get("oneClick") is False, "nsis.oneClick must be false for interactive install"
    assert nsis.get("allowToChangeInstallationDirectory") is True, (
        "nsis.allowToChangeInstallationDirectory must be true"
    )


def test_electron_builder_extra_resources_uses_directory_filter():
    """extraResources must use directory glob to include the full onedir bundle.

    DEC-BUILD-002: onedir mode produces a directory, not a single file.
    The extraResources config must use a filter glob to capture all files
    in the sat-api directory, not just the top-level entry.
    """
    config = yaml.safe_load(ELECTRON_BUILDER_YML.read_text())
    assert "extraResources" in config, "electron-builder.yml must define extraResources"
    resources = config["extraResources"]
    assert isinstance(resources, list), "extraResources must be a list"
    assert len(resources) >= 1, "extraResources must have at least one entry"

    sidecar_entry = resources[0]
    assert isinstance(sidecar_entry, dict), "sidecar extraResources entry must be a dict"
    assert "from" in sidecar_entry, "sidecar entry must have a from path"
    assert "to" in sidecar_entry, "sidecar entry must have a to path"

    # The 'from' path must point to the onedir dist directory
    assert "sat-api" in sidecar_entry["from"], (
        f"extraResources.from must reference sat-api directory, got: {sidecar_entry['from']}"
    )
    # The 'to' path must place it under sidecar/
    assert sidecar_entry["to"].startswith("sidecar"), (
        f"extraResources.to must be under sidecar/, got: {sidecar_entry['to']}"
    )
    # Must have a filter to include all files (onedir has many files)
    assert "filter" in sidecar_entry, (
        "extraResources entry must have a filter to capture all files in the onedir bundle"
    )
    filter_val = sidecar_entry["filter"]
    assert isinstance(filter_val, list), "filter must be a list"
    assert "**/*" in filter_val, f"filter must include **/* glob, got: {filter_val}"


def test_electron_builder_mac_has_icon():
    """Mac section must reference the icns icon file."""
    config = yaml.safe_load(ELECTRON_BUILDER_YML.read_text())
    mac = config.get("mac", {})
    assert mac.get("icon") == "build/icon.icns", (
        f"mac.icon must be build/icon.icns, got: {mac.get('icon')}"
    )


def test_electron_builder_win_has_icon():
    """Win section must reference the ico icon file."""
    config = yaml.safe_load(ELECTRON_BUILDER_YML.read_text())
    win = config.get("win", {})
    assert win.get("icon") == "build/icon.ico", (
        f"win.icon must be build/icon.ico, got: {win.get('icon')}"
    )


# ---------------------------------------------------------------------------
# package.json script tests
# ---------------------------------------------------------------------------


def test_package_json_is_valid_json():
    """package.json must parse without errors."""
    content = PACKAGE_JSON.read_text()
    pkg = json.loads(content)
    assert isinstance(pkg, dict), "package.json should parse to a dict"


def test_package_json_has_dist_mac_script():
    """dist:mac script must build the sidecar and run electron-builder for Mac."""
    pkg = json.loads(PACKAGE_JSON.read_text())
    scripts = pkg.get("scripts", {})
    assert "dist:mac" in scripts, "package.json must have a dist:mac script"
    cmd = scripts["dist:mac"]
    assert "electron-builder" in cmd, f"dist:mac must invoke electron-builder, got: {cmd}"
    assert "--mac" in cmd, f"dist:mac must pass --mac flag, got: {cmd}"


def test_package_json_has_dist_win_script():
    """dist:win script must build the sidecar and run electron-builder for Windows."""
    pkg = json.loads(PACKAGE_JSON.read_text())
    scripts = pkg.get("scripts", {})
    assert "dist:win" in scripts, "package.json must have a dist:win script"
    cmd = scripts["dist:win"]
    assert "electron-builder" in cmd, f"dist:win must invoke electron-builder, got: {cmd}"
    assert "--win" in cmd, f"dist:win must pass --win flag, got: {cmd}"


def test_package_json_has_build_sidecar_mac_script():
    """build:sidecar:mac script must invoke pyinstaller with the spec file."""
    pkg = json.loads(PACKAGE_JSON.read_text())
    scripts = pkg.get("scripts", {})
    assert "build:sidecar:mac" in scripts, "package.json must have a build:sidecar:mac script"
    cmd = scripts["build:sidecar:mac"]
    assert "pyinstaller" in cmd, f"build:sidecar:mac must invoke pyinstaller, got: {cmd}"
    assert "sat-api.spec" in cmd, f"build:sidecar:mac must reference sat-api.spec, got: {cmd}"


def test_package_json_has_build_sidecar_win_script():
    """build:sidecar:win script must invoke pyinstaller with the spec file."""
    pkg = json.loads(PACKAGE_JSON.read_text())
    scripts = pkg.get("scripts", {})
    assert "build:sidecar:win" in scripts, "package.json must have a build:sidecar:win script"
    cmd = scripts["build:sidecar:win"]
    assert "pyinstaller" in cmd, f"build:sidecar:win must invoke pyinstaller, got: {cmd}"
    assert "sat-api.spec" in cmd, f"build:sidecar:win must reference sat-api.spec, got: {cmd}"


def test_package_json_dist_scripts_include_build_step():
    """dist:mac and dist:win must invoke the build step before electron-builder.

    This ensures the JS bundle is current before packaging.
    """
    pkg = json.loads(PACKAGE_JSON.read_text())
    scripts = pkg.get("scripts", {})
    for script_name in ("dist:mac", "dist:win"):
        cmd = scripts.get(script_name, "")
        assert "build" in cmd, (
            f"{script_name} must call npm run build (or equivalent) before electron-builder, got: {cmd}"
        )


# ---------------------------------------------------------------------------
# scripts/build-sidecar.py tests
# ---------------------------------------------------------------------------


def test_build_sidecar_script_exists():
    """scripts/build-sidecar.py must exist as a cross-platform build helper."""
    assert BUILD_SIDECAR_SCRIPT.exists(), (
        f"scripts/build-sidecar.py not found at {BUILD_SIDECAR_SCRIPT}"
    )


def test_build_sidecar_script_is_valid_python():
    """scripts/build-sidecar.py must be syntactically valid Python."""
    source = BUILD_SIDECAR_SCRIPT.read_text()
    try:
        ast.parse(source)
    except SyntaxError as exc:
        pytest.fail(f"scripts/build-sidecar.py has a syntax error: {exc}")


def test_build_sidecar_script_detects_platform():
    """build-sidecar.py must reference platform detection (sys.platform or platform module)."""
    source = BUILD_SIDECAR_SCRIPT.read_text()
    assert "platform" in source, (
        "build-sidecar.py must detect the current platform (sys.platform or platform module)"
    )


def test_build_sidecar_script_references_spec_file():
    """build-sidecar.py must reference the PyInstaller spec file."""
    source = BUILD_SIDECAR_SCRIPT.read_text()
    assert "sat-api.spec" in source, (
        "build-sidecar.py must reference the sat-api.spec file"
    )


def test_build_sidecar_script_references_distpath():
    """build-sidecar.py must specify the distpath for PyInstaller output."""
    source = BUILD_SIDECAR_SCRIPT.read_text()
    assert "distpath" in source or "--distpath" in source, (
        "build-sidecar.py must specify the --distpath argument to control output location"
    )


# ---------------------------------------------------------------------------
# .gitignore tests
# ---------------------------------------------------------------------------


def test_gitignore_covers_pyinstaller_output():
    """desktop/.gitignore must exclude pyinstaller build artifacts."""
    assert DESKTOP_GITIGNORE.exists(), "desktop/.gitignore must exist"
    content = DESKTOP_GITIGNORE.read_text()
    assert "pyinstaller" in content.lower() or "pyinstaller/" in content, (
        "desktop/.gitignore must exclude pyinstaller/ directory"
    )


def test_gitignore_covers_dist_output():
    """desktop/.gitignore must exclude the electron-builder dist output."""
    assert DESKTOP_GITIGNORE.exists(), "desktop/.gitignore must exist"
    content = DESKTOP_GITIGNORE.read_text()
    assert "dist" in content, "desktop/.gitignore must exclude dist/ (electron-builder output)"


def test_gitignore_covers_out_directory():
    """desktop/.gitignore must exclude the vite/electron-vite build output."""
    assert DESKTOP_GITIGNORE.exists(), "desktop/.gitignore must exist"
    content = DESKTOP_GITIGNORE.read_text()
    assert "out" in content, "desktop/.gitignore must exclude out/ (electron-vite output)"


# ---------------------------------------------------------------------------
# electron-builder availability check
# ---------------------------------------------------------------------------


def test_electron_builder_available():
    """electron-builder must be installed in the desktop node_modules.

    Checks both the worktree desktop directory and the canonical project desktop
    directory, since worktrees don't get a copy of node_modules (they share from
    the main checkout or rely on 'npm install' being run separately).
    """
    # Check worktree desktop first, then fall back to main project desktop
    candidate_dirs = [
        DESKTOP_DIR,
        # Main project desktop (when running from worktree that doesn't have node_modules).
        # Path: tests/test_build_config.py -> tests/ -> worktree-root/ -> .worktrees/ -> repo root
        Path(__file__).parent.parent.parent.parent / "desktop",
    ]
    for desktop in candidate_dirs:
        electron_builder_bin = desktop / "node_modules" / ".bin" / "electron-builder"
        if electron_builder_bin.exists():
            return  # Found it — test passes

    # Neither location has it installed — skip in CI where Node deps aren't installed
    pytest.skip(
        "desktop/node_modules not installed — skipping electron-builder check. "
        "Run: cd desktop && npm install"
    )
