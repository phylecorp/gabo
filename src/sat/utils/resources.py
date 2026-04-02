"""Resource path resolution for frozen (PyInstaller) and normal execution.

In a PyInstaller onedir bundle, source files are compiled into the executable and
data files are extracted to sys._MEIPASS at runtime. Path(__file__).parent references
embedded in source modules point to non-existent paths inside the bundle, so any code
that resolves file paths relative to __file__ will break under PyInstaller unless it
checks for _MEIPASS explicitly.

This module provides two helpers:

- ``get_resource_path(package_path, relative)`` — resolves ``relative`` from the
  calling module's directory (unfrozen) or from ``_MEIPASS`` (frozen).  Best for
  resources that live in the same package directory as the calling module.

- ``get_sat_resource_path(relative)`` — resolves ``relative`` from the ``sat``
  package root (unfrozen) or from ``_MEIPASS`` (frozen).  Use this when the caller
  is deeply nested and the resource is expressed as a sat-root-relative path such as
  ``"report/templates"``.  Both modes use the same ``relative`` string, so the
  caller never needs to branch on the frozen flag.

@decision DEC-BUILD-005
@title sys._MEIPASS-aware resource path helper — standard PyInstaller pattern
@status accepted
@rationale PyInstaller extracts bundled files to sys._MEIPASS in onedir mode
(DEC-BUILD-002). The standard pattern is: if sys._MEIPASS exists, resolve resources
relative to that directory; otherwise resolve relative to the calling module's parent.
Centralising this logic here means callers never duplicate freeze-detection code, and
Future Implementers only need to update one place if the extraction strategy changes.
Two helpers cover the two common call-site shapes:
  1. get_resource_path(__file__, "templates") — caller-relative (e.g. builder.py)
  2. get_sat_resource_path("report/templates") — sat-root-relative (e.g. config.py
     which is nested 3 directories deep but references sat/report/templates)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Resolved once at import time: the directory that contains the ``sat`` package.
# In normal execution this is src/sat/utils/../.. = src/sat/.
# In a frozen bundle _SAT_ROOT is unused because _MEIPASS takes precedence.
_SAT_ROOT: Path = Path(__file__).parent.parent


def get_resource_path(package_path: str, relative: str) -> Path:
    """Resolve a resource path for both frozen (PyInstaller) and normal execution.

    In normal execution, the resource is resolved relative to the directory that
    contains ``package_path`` (which callers typically pass as ``__file__``).

    In a PyInstaller onedir bundle, ``sys._MEIPASS`` is set to the temporary
    directory where the bundle's data files are extracted. In that mode, the
    ``package_path`` argument is ignored and the resource is resolved relative to
    ``sys._MEIPASS`` instead. The ``relative`` path must therefore be the same
    path that is mapped into the bundle via the ``datas`` list in the spec file.

    Example (in src/sat/report/builder.py)::

        from sat.utils.resources import get_resource_path

        # Normal: returns <src/sat/report>/templates
        # Frozen: returns <MEIPASS>/sat/report/templates
        template_dir = get_resource_path(__file__, "templates")

        # For a file one level deeper:
        # Normal: returns <src/sat/report>/templates/report.html.j2
        # Frozen: returns <MEIPASS>/sat/report/templates/report.html.j2
        tmpl = get_resource_path(__file__, "templates/report.html.j2")

    Note: in frozen mode ``relative`` must match the path used in the ``datas``
    entry of the PyInstaller spec file.  For ``builder.py``, the spec maps
    ``src/sat/report/templates/*.j2`` to ``sat/report/templates/``, so
    ``relative="templates"`` (unfrozen) must correspond to ``_MEIPASS/sat/report/templates``
    (frozen) — the spec ``dest`` must include the full package path.

    Args:
        package_path: ``__file__`` of the calling module.  Used as the base for
            relative resolution when *not* running under PyInstaller.
        relative: Path to the resource relative to ``package_path``'s directory
            (unfrozen) or relative to ``sys._MEIPASS`` (frozen).  Use forward
            slashes; ``Path`` handles platform normalisation.

    Returns:
        Absolute ``Path`` to the resource.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass) / relative
    return Path(package_path).parent / relative


def get_sat_resource_path(relative: str) -> Path:
    """Resolve a sat-package-root-relative resource path.

    Use this when the caller is deeply nested inside the ``sat`` package and the
    resource is most naturally expressed as a path from the ``sat`` package root
    (e.g. ``"report/templates"``).  The same ``relative`` string works in both
    frozen and unfrozen modes because PyInstaller bundles data files at paths
    relative to ``_MEIPASS`` that mirror the ``sat`` package structure.

    Example (in src/sat/api/routes/config.py)::

        from sat.utils.resources import get_sat_resource_path

        # Normal: returns <repo>/src/sat/report/templates
        # Frozen: returns <MEIPASS>/sat/report/templates
        default_templates = get_sat_resource_path("report/templates")

    Args:
        relative: Path to the resource relative to the ``sat`` package root, using
            forward slashes.  Do NOT include a leading ``sat/`` prefix — this
            function adds it automatically in frozen mode.

    Returns:
        Absolute ``Path`` to the resource.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        # In the bundle, data files are at _MEIPASS/sat/<relative>
        return Path(meipass) / "sat" / relative
    return _SAT_ROOT / relative
