# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file for the SAT API sidecar process.
#
# @decision DEC-BUILD-001
# @title PyInstaller spec file over CLI arguments
# @status accepted
# @rationale The SAT API has dynamic imports (provider modules loaded by name from
# config, technique modules registered at import time, research backends selected
# at runtime), data files (Jinja2 templates), and excludes for unused heavy
# dependencies. A spec file captures all of this declaratively and is reproducible
# across environments. CLI arguments cannot express hidden imports + data files +
# excludes in a maintainable way.
#
# @decision DEC-BUILD-002
# @title onedir mode — instant startup vs 5-15s extraction delay
# @status accepted
# @rationale onefile mode extracts the entire bundle to a temp directory on each
# launch, causing a 5-15 second cold-start penalty. The Electron sidecar manager
# starts the API process on demand; a 5-15s delay before the first API call is
# unacceptable UX. onedir mode produces a directory of files that load instantly
# because no extraction step is needed. The directory is distributed inside the
# Electron app's Resources directory and is opaque to the end user.
#
# Build command (from repo root):
#   pyinstaller desktop/sat-api.spec \
#       --distpath desktop/pyinstaller/dist \
#       --workpath desktop/pyinstaller/build
#
# Output: desktop/pyinstaller/dist/sat-api/   (the onedir bundle)
#
# Entry point: src/sat/api/main.py (main() function, also registered as the
# console_scripts entry point "sat-api" in pyproject.toml).

import os
from pathlib import Path

# Resolve repo root relative to this spec file's location (desktop/).
_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))  # noqa: F821 — SPEC is a PyInstaller built-in
_REPO_ROOT = os.path.dirname(_SPEC_DIR)
_SRC_SAT = os.path.join(_REPO_ROOT, "src", "sat")

block_cipher = None

a = Analysis(
    # Entry point: src/sat/api/main.py — defines main() which uvicorn.run()s the app.
    scripts=[os.path.join(_REPO_ROOT, "src", "sat", "api", "main.py")],
    pathex=[os.path.join(_REPO_ROOT, "src")],
    binaries=[],
    datas=[
        # Jinja2 report templates — mapped to sat/report/templates/ inside the bundle.
        # get_resource_path(__file__, "templates") in builder.py resolves to
        # _MEIPASS/sat/report/templates when frozen (see DEC-BUILD-005).
        (
            os.path.join(_SRC_SAT, "report", "templates", "*.j2"),
            os.path.join("sat", "report", "templates"),
        ),
    ],
    hiddenimports=[
        # ---------------------------------------------------------------------------
        # LLM provider modules — loaded dynamically by name from provider registry.
        # PyInstaller cannot detect these because they are imported via string lookup.
        # ---------------------------------------------------------------------------
        "sat.providers",
        "sat.providers.anthropic",
        "sat.providers.openai",
        "sat.providers.gemini",
        "sat.providers.base",
        "sat.providers.rate_limiter",
        "sat.providers.registry",
        # ---------------------------------------------------------------------------
        # Technique modules — imported by sat.techniques.__init__ at registration time.
        # PyInstaller may not follow the "import sat.techniques.diagnostic" pattern.
        # ---------------------------------------------------------------------------
        "sat.techniques",
        "sat.techniques.base",
        "sat.techniques.registry",
        "sat.techniques.selector",
        "sat.techniques.synthesis",
        "sat.techniques.diagnostic",
        "sat.techniques.diagnostic.ach",
        "sat.techniques.diagnostic.assumptions",
        "sat.techniques.diagnostic.indicators",
        "sat.techniques.diagnostic.quality",
        "sat.techniques.contrarian",
        "sat.techniques.contrarian.devils_advocacy",
        "sat.techniques.contrarian.high_impact",
        "sat.techniques.contrarian.team_ab",
        "sat.techniques.contrarian.what_if",
        "sat.techniques.imaginative",
        "sat.techniques.imaginative.alt_futures",
        "sat.techniques.imaginative.brainstorming",
        "sat.techniques.imaginative.outside_in",
        "sat.techniques.imaginative.red_team",
        # ---------------------------------------------------------------------------
        # Research backend modules — selected at runtime from registry.
        # ---------------------------------------------------------------------------
        "sat.research",
        "sat.research.base",
        "sat.research.registry",
        "sat.research.runner",
        "sat.research.structurer",
        "sat.research.gap_resolver",
        "sat.research.llm_search",
        "sat.research.perplexity",
        "sat.research.brave",
        "sat.research.openai_deep",
        "sat.research.gemini_deep",
        "sat.research.multi_runner",
        # ---------------------------------------------------------------------------
        # uvicorn internals — lifespan, logging, and protocol handlers are loaded
        # dynamically by uvicorn's config system and missed by static analysis.
        # ---------------------------------------------------------------------------
        "uvicorn.lifespan.on",
        "uvicorn.logging",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        # ---------------------------------------------------------------------------
        # Optional high-performance uvicorn extras — included defensively; safe to
        # omit if not installed (PyInstaller will warn but not fail).
        # ---------------------------------------------------------------------------
        "uvloop",
        "httptools",
        # ---------------------------------------------------------------------------
        # Runtime dependencies imported conditionally or by string name.
        # ---------------------------------------------------------------------------
        "dotenv",           # python-dotenv: load_dotenv() in main.py
        "markdown",         # markdown: report HTML rendering
        "jinja2",           # Jinja2: report template rendering
        "jinja2.ext",
        "certifi",          # certifi: TLS cert bundle for httpx
        "httpx",            # httpx: HTTP client for provider API calls
        "websockets",       # websockets: WebSocket support
        "pydantic",         # pydantic v2: model validation throughout
        "pydantic.v1",      # pydantic v1 compat shim (used by some libs)
        "fastapi",
        "fastapi.middleware.cors",
        "starlette",
        "starlette.routing",
        "anyio",
        "anyio._backends._asyncio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy scientific / GUI packages not used by the SAT API.
        # Excluding them reduces bundle size significantly.
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "PIL",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "setuptools",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: binaries go in COLLECT, not embedded in exe
    name="sat-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # console=True: stdout required for SAT_AUTH_TOKEN= line (DEC-AUTH-004)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="sat-api",
)
