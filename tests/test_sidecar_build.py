"""Tests that verify the PyInstaller spec file covers all dynamic imports and data files.

The SAT API sidecar is packaged as a PyInstaller onedir bundle. Because Python
modules loaded by string name (providers, techniques, research backends) and data
files (Jinja2 templates) are invisible to PyInstaller's static analysis, they must
be declared explicitly in desktop/sat-api.spec. These tests catch regressions where
a new module is added to the source tree but forgotten in the spec.

@decision DEC-BUILD-003
@title Spec coverage tests — fail-fast guard against missing hiddenimports/datas
@status accepted
@rationale When a new provider, technique, or research module is added, a developer
may forget to update desktop/sat-api.spec. Without these tests the omission is only
discovered after a full PyInstaller build succeeds but the packaged binary fails at
runtime with a ModuleNotFoundError. These tests run in seconds and catch the omission
at CI time, before a binary is ever built.

The tests parse sat-api.spec as Python source using ast.parse rather than executing
it, so they work without PyInstaller installed and without building anything.

Module name generation note: all paths are resolved before computing relative paths
to avoid mismatches when tests are run from a different working directory (e.g. repo
root vs. worktree).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Always resolve to absolute paths so relative-path CWD differences don't matter.
_REPO_ROOT = Path(__file__).parent.parent.resolve()
_SPEC_FILE = _REPO_ROOT / "desktop" / "sat-api.spec"
_SRC_SAT = _REPO_ROOT / "src" / "sat"
_SRC_ROOT = _REPO_ROOT / "src"  # the root relative to which dotted names are formed


def _module_name_from_path(py_path: Path) -> str:
    """Convert an absolute .py file path to a dotted module name relative to src/.

    e.g. /repo/src/sat/providers/anthropic.py -> "sat.providers.anthropic"
         /repo/src/sat/providers/__init__.py   -> "sat.providers"

    Both py_path and _SRC_ROOT are resolved before the relative_to call so the
    function works regardless of the CWD from which tests are invoked.
    """
    abs_path = py_path.resolve()
    rel = abs_path.relative_to(_SRC_ROOT)  # e.g. sat/providers/anthropic.py
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def _parse_hiddenimports() -> frozenset[str]:
    """Extract hiddenimports string literals from the Analysis() call in the spec.

    We use ast.parse (not exec) so this works without PyInstaller installed.
    """
    source = _SPEC_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(_SPEC_FILE))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "Analysis":
            continue
        for kw in node.keywords:
            if kw.arg != "hiddenimports":
                continue
            strings: list[str] = []
            for child in ast.walk(kw.value):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    strings.append(child.value)
            return frozenset(strings)

    return frozenset()


def _parse_datas_source_strings() -> list[str]:
    """Extract all string literals from the datas list in the Analysis() call.

    The spec uses os.path.join() calls within the datas tuples, so individual
    path components appear as separate string constants rather than complete
    paths.  We collect them all and let the tests check for key substrings.
    """
    source = _SPEC_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(_SPEC_FILE))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "Analysis":
            continue
        for kw in node.keywords:
            if kw.arg != "datas":
                continue
            strings: list[str] = []
            for child in ast.walk(kw.value):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    strings.append(child.value)
            return strings

    return []


# ---------------------------------------------------------------------------
# Tests: hiddenimports coverage
# ---------------------------------------------------------------------------


class TestHiddenImportsCoverage:
    """Every provider/technique/research .py module must appear in hiddenimports."""

    @pytest.fixture(scope="class")
    def hidden_imports(self) -> frozenset[str]:
        return _parse_hiddenimports()

    def _collect_modules(self, package_dir: Path, *, recursive: bool = False) -> list[str]:
        """Return sorted dotted module names for all .py files under package_dir."""
        glob_pattern = "**/*.py" if recursive else "*.py"
        paths = sorted(package_dir.resolve().glob(glob_pattern))
        return [_module_name_from_path(p) for p in paths]

    def test_spec_file_exists(self):
        assert _SPEC_FILE.exists(), f"Spec file not found: {_SPEC_FILE}"

    def test_hidden_imports_non_empty(self, hidden_imports):
        assert len(hidden_imports) > 0, "hiddenimports list in spec is empty"

    def test_all_provider_modules_listed(self, hidden_imports):
        """Every sat/providers/*.py must be in hiddenimports (providers are dynamically loaded)."""
        providers_dir = _SRC_SAT / "providers"
        modules = self._collect_modules(providers_dir)
        missing = [m for m in modules if m not in hidden_imports]
        assert not missing, (
            f"Provider modules missing from hiddenimports in {_SPEC_FILE.relative_to(_REPO_ROOT)}:\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    def test_all_technique_modules_listed(self, hidden_imports):
        """Every sat/techniques/**/*.py must be in hiddenimports (techniques registered at import time)."""
        techniques_dir = _SRC_SAT / "techniques"
        modules = self._collect_modules(techniques_dir, recursive=True)
        missing = [m for m in modules if m not in hidden_imports]
        assert not missing, (
            f"Technique modules missing from hiddenimports in {_SPEC_FILE.relative_to(_REPO_ROOT)}:\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    def test_all_research_modules_listed(self, hidden_imports):
        """Every sat/research/*.py must be in hiddenimports (research backends selected at runtime)."""
        research_dir = _SRC_SAT / "research"
        modules = self._collect_modules(research_dir)
        missing = [m for m in modules if m not in hidden_imports]
        assert not missing, (
            f"Research modules missing from hiddenimports in {_SPEC_FILE.relative_to(_REPO_ROOT)}:\n"
            + "\n".join(f"  {m}" for m in missing)
        )


# ---------------------------------------------------------------------------
# Tests: datas coverage (Jinja2 templates)
# ---------------------------------------------------------------------------


class TestDataFilesCoverage:
    """All .j2 template files must be covered by the datas entry in the spec.

    The spec uses os.path.join() to build the source and destination paths of
    the datas tuple, so we cannot reconstruct full paths from string literals
    alone.  Instead we verify that the required path *components* are present
    in the datas string constants.  This is robust and avoids coupling to OS
    path separators.
    """

    @pytest.fixture(scope="class")
    def datas_strings(self) -> list[str]:
        return _parse_datas_source_strings()

    def test_spec_datas_non_empty(self, datas_strings):
        assert len(datas_strings) > 0, "datas list in spec is empty — templates are missing"

    def test_templates_directory_has_j2_files(self):
        """Sanity: the source template directory actually contains .j2 files."""
        templates_dir = _SRC_SAT / "report" / "templates"
        j2_files = list(templates_dir.glob("*.j2"))
        assert j2_files, f"No .j2 files found in {templates_dir}"

    def test_datas_entry_has_j2_glob(self, datas_strings):
        """The datas source entry must contain a '*.j2' glob component."""
        has_j2_glob = any("*.j2" in s for s in datas_strings)
        assert has_j2_glob, (
            "No '*.j2' glob found in datas entries. "
            "Template files will be missing from the packaged binary.\n"
            f"datas string components found: {datas_strings}"
        )

    def test_datas_source_has_report_and_templates_components(self, datas_strings):
        """The datas source path components must include 'report' and 'templates'."""
        # os.path.join(_SRC_SAT, "report", "templates", "*.j2") contributes
        # "report", "templates", and "*.j2" as separate string constants.
        required_components = {"report", "templates", "*.j2"}
        found = set(datas_strings)
        missing = required_components - found
        assert not missing, (
            f"Expected datas source path components {required_components!r} "
            f"but these were not found as string constants: {missing!r}\n"
            f"All datas string components: {datas_strings}"
        )

    def test_datas_destination_has_sat_report_templates_components(self, datas_strings):
        """The datas destination path components must include 'sat', 'report', 'templates'.

        The destination is os.path.join("sat", "report", "templates"), so each
        component appears as a separate string constant.  get_sat_resource_path
        in builder.py resolves to _MEIPASS/sat/report/templates when frozen.
        """
        required_components = {"sat", "report", "templates"}
        found = set(datas_strings)
        missing = required_components - found
        assert not missing, (
            f"Expected datas destination path components {required_components!r} "
            f"but these were not found as string constants: {missing!r}\n"
            "get_resource_path will fail to locate templates in the frozen binary.\n"
            f"All datas string components: {datas_strings}"
        )


# ---------------------------------------------------------------------------
# Tests: resource path helper integration
# ---------------------------------------------------------------------------


class TestResourcePathIntegration:
    """Integration check: get_sat_resource_path resolves to a dir with real .j2 files."""

    def test_template_dir_contains_j2_files(self):
        """get_sat_resource_path('report/templates') must point to a directory with .j2 files."""
        from sat.utils.resources import get_sat_resource_path

        template_dir = get_sat_resource_path("report/templates")
        assert template_dir.is_dir(), f"Template directory not found: {template_dir}"
        j2_files = list(template_dir.glob("*.j2"))
        assert j2_files, (
            f"Template directory {template_dir} exists but contains no .j2 files. "
            "The report builder will fail at runtime."
        )

    def test_specific_templates_exist(self):
        """The two canonical templates (html and md) must both be present."""
        from sat.utils.resources import get_sat_resource_path

        template_dir = get_sat_resource_path("report/templates")
        expected = ["report.html.j2", "report.md.j2"]
        for name in expected:
            path = template_dir / name
            assert path.exists(), f"Expected template file not found: {path}"
