#!/usr/bin/env python3
"""Cross-platform build helper for the SAT API sidecar.

Detects the current OS, finds the PyInstaller spec file, runs PyInstaller
with the standard arguments, and verifies the output directory was created.

This script is a convenience wrapper for CI and local builds. The underlying
npm scripts (dist:mac, dist:win) also work directly, but this script provides
a single entry point with validation.

Usage (from repo root):
    python3 scripts/build-sidecar.py

Output:
    desktop/pyinstaller/dist/sat-api/   (the onedir bundle)

@decision DEC-BUILD-004
@title Separate dist:mac and dist:win scripts, no cross-compilation
@status accepted
@rationale PyInstaller cannot cross-compile. This script auto-detects the OS and
builds for the current platform only. CI uses a matrix build (macos-latest +
windows-latest) to produce both artifacts. The script name and platform check
make the constraint explicit so future operators don't attempt cross-compilation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

PLATFORM = sys.platform  # "darwin", "win32", "linux"

_PLATFORM_NAMES = {
    "darwin": "macOS",
    "win32": "Windows",
    "linux": "Linux",
}

PLATFORM_DISPLAY = _PLATFORM_NAMES.get(PLATFORM, PLATFORM)

# ---------------------------------------------------------------------------
# Paths (resolved relative to this script's location = repo root / scripts)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
DESKTOP_DIR = REPO_ROOT / "desktop"

SPEC_FILE = DESKTOP_DIR / "sat-api.spec"
DIST_PATH = DESKTOP_DIR / "pyinstaller" / "dist"
WORK_PATH = DESKTOP_DIR / "pyinstaller" / "build"

# The onedir output directory produced by PyInstaller
OUTPUT_DIR = DIST_PATH / "sat-api"


def _check_pyinstaller() -> None:
    """Verify PyInstaller is available on PATH."""
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Try the pyinstaller executable directly
        result2 = subprocess.run(
            ["pyinstaller", "--version"],
            capture_output=True,
            text=True,
        )
        if result2.returncode != 0:
            print("ERROR: PyInstaller not found. Install it with:", file=sys.stderr)
            print("  pip install pyinstaller", file=sys.stderr)
            sys.exit(1)


def _check_spec_file() -> None:
    """Verify the spec file exists."""
    if not SPEC_FILE.exists():
        print(f"ERROR: Spec file not found: {SPEC_FILE}", file=sys.stderr)
        print("Ensure you are running from the repo root.", file=sys.stderr)
        sys.exit(1)


def build() -> None:
    """Run PyInstaller to build the SAT API sidecar for the current platform."""
    print(f"Building SAT API sidecar for {PLATFORM_DISPLAY}...")
    print(f"  Spec:     {SPEC_FILE}")
    print(f"  Distpath: {DIST_PATH}")
    print(f"  Workpath: {WORK_PATH}")
    print()

    _check_pyinstaller()
    _check_spec_file()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--distpath", str(DIST_PATH),
        "--workpath", str(WORK_PATH),
        "--noconfirm",
    ]

    print(f"Running: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"\nERROR: PyInstaller failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    # Verify output directory was created
    if not OUTPUT_DIR.exists():
        print(f"\nERROR: Expected output directory not found: {OUTPUT_DIR}", file=sys.stderr)
        print("PyInstaller may have changed its output path.", file=sys.stderr)
        sys.exit(1)

    # Report output
    entry_count = sum(1 for _ in OUTPUT_DIR.rglob("*") if _.is_file())
    print(f"\nBuild complete: {OUTPUT_DIR}")
    print(f"  Files in bundle: {entry_count}")
    print()

    if PLATFORM == "win32":
        exe_path = OUTPUT_DIR / "sat-api.exe"
    else:
        exe_path = OUTPUT_DIR / "sat-api"

    if exe_path.exists():
        print(f"  Entry binary: {exe_path}")
    else:
        print(f"  WARNING: Expected entry binary not found at {exe_path}", file=sys.stderr)
        print("  The bundle may still be valid; check the output directory.", file=sys.stderr)


if __name__ == "__main__":
    build()
