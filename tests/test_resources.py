"""Tests for the resource path helpers (src/sat/utils/resources.py).

Verifies correct path resolution in both normal (unfrozen) and PyInstaller
frozen (_MEIPASS) execution modes for both helpers:

- get_resource_path(package_path, relative) — caller-directory-relative
- get_sat_resource_path(relative) — sat-package-root-relative

@decision DEC-BUILD-005
@title sys._MEIPASS-aware resource path helper — standard PyInstaller pattern
@status accepted
@rationale PyInstaller extracts bundled files to sys._MEIPASS in onedir mode.
Without this helper, Path(__file__).parent references become invalid in the
frozen binary because source files don't exist at their original locations.
The helper centralizes the freeze-detection logic so callers don't duplicate it.
Two helpers cover the two common patterns: caller-relative (get_resource_path)
and sat-root-relative (get_sat_resource_path), covering shallow vs. deep callers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Tests: get_resource_path — normal (unfrozen) mode
# ---------------------------------------------------------------------------


class TestUnfrozenMode:
    """get_resource_path returns Path(__file__).parent / relative in normal mode."""

    def test_returns_path_object(self):
        from sat.utils.resources import get_resource_path

        result = get_resource_path(__file__, "fixtures/data.json")
        assert isinstance(result, Path)

    def test_returns_caller_parent_relative(self):
        from sat.utils.resources import get_resource_path

        result = get_resource_path(__file__, "fixtures/data.json")
        expected = Path(__file__).parent / "fixtures/data.json"
        assert result == expected

    def test_simple_filename(self):
        from sat.utils.resources import get_resource_path

        result = get_resource_path(__file__, "report.html.j2")
        expected = Path(__file__).parent / "report.html.j2"
        assert result == expected

    def test_nested_relative_path(self):
        from sat.utils.resources import get_resource_path

        result = get_resource_path(__file__, "a/b/c.txt")
        expected = Path(__file__).parent / "a/b/c.txt"
        assert result == expected

    def test_no_meipass_in_sys(self):
        """Confirm _MEIPASS is absent so test is not running under frozen mode."""
        assert not hasattr(sys, "_MEIPASS"), (
            "Test environment appears to be a PyInstaller bundle; "
            "unfrozen-mode tests are meaningless here."
        )


# ---------------------------------------------------------------------------
# Tests: get_resource_path — frozen (PyInstaller) mode
# ---------------------------------------------------------------------------


class TestFrozenMode:
    """get_resource_path returns MEIPASS / relative when sys._MEIPASS is set."""

    @pytest.fixture(autouse=True)
    def _set_meipass(self, monkeypatch, tmp_path):
        """Inject a fake _MEIPASS into sys and reload the module."""
        self.meipass = tmp_path / "meipass"
        self.meipass.mkdir()
        monkeypatch.setattr(sys, "_MEIPASS", str(self.meipass), raising=False)
        import importlib

        import sat.utils.resources as mod

        importlib.reload(mod)
        yield
        importlib.reload(mod)

    def test_returns_meipass_based_path(self):
        import sat.utils.resources as mod

        result = mod.get_resource_path(__file__, "sat/report/templates/report.html.j2")
        expected = self.meipass / "sat/report/templates/report.html.j2"
        assert result == expected

    def test_ignores_package_path_in_frozen_mode(self):
        """package_path is irrelevant when MEIPASS is set."""
        import sat.utils.resources as mod

        result1 = mod.get_resource_path("/some/module.py", "sat/report/templates/report.html.j2")
        result2 = mod.get_resource_path("/different/module.py", "sat/report/templates/report.html.j2")
        assert result1 == result2

    def test_simple_relative_path(self):
        import sat.utils.resources as mod

        result = mod.get_resource_path(__file__, "data.json")
        expected = self.meipass / "data.json"
        assert result == expected

    def test_meipass_is_a_path_object(self):
        import sat.utils.resources as mod

        result = mod.get_resource_path(__file__, "some/resource.txt")
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# Tests: get_sat_resource_path — normal (unfrozen) mode
# ---------------------------------------------------------------------------


class TestSatResourceUnfrozenMode:
    """get_sat_resource_path resolves from the sat package root in unfrozen mode."""

    def test_returns_path_object(self):
        from sat.utils.resources import get_sat_resource_path

        result = get_sat_resource_path("report/templates")
        assert isinstance(result, Path)

    def test_resolves_from_sat_package_root(self):
        from sat.utils.resources import _SAT_ROOT, get_sat_resource_path

        result = get_sat_resource_path("report/templates")
        expected = _SAT_ROOT / "report/templates"
        assert result == expected

    def test_templates_path_points_to_real_dir(self):
        """report/templates actually exists — smoke-test the resolved path."""
        from sat.utils.resources import get_sat_resource_path

        result = get_sat_resource_path("report/templates")
        assert result.is_dir(), f"Expected directory at {result}"

    def test_nested_resource(self):
        from sat.utils.resources import _SAT_ROOT, get_sat_resource_path

        result = get_sat_resource_path("report/templates/report.html.j2")
        expected = _SAT_ROOT / "report/templates/report.html.j2"
        assert result == expected


# ---------------------------------------------------------------------------
# Tests: get_sat_resource_path — frozen (PyInstaller) mode
# ---------------------------------------------------------------------------


class TestSatResourceFrozenMode:
    """get_sat_resource_path returns MEIPASS/sat/<relative> in frozen mode."""

    @pytest.fixture(autouse=True)
    def _set_meipass(self, monkeypatch, tmp_path):
        self.meipass = tmp_path / "meipass"
        self.meipass.mkdir()
        monkeypatch.setattr(sys, "_MEIPASS", str(self.meipass), raising=False)
        import importlib

        import sat.utils.resources as mod

        importlib.reload(mod)
        yield
        importlib.reload(mod)

    def test_returns_meipass_sat_prefixed_path(self):
        import sat.utils.resources as mod

        result = mod.get_sat_resource_path("report/templates")
        expected = self.meipass / "sat" / "report/templates"
        assert result == expected

    def test_nested_resource(self):
        import sat.utils.resources as mod

        result = mod.get_sat_resource_path("report/templates/report.html.j2")
        expected = self.meipass / "sat" / "report/templates/report.html.j2"
        assert result == expected

    def test_returns_path_object(self):
        import sat.utils.resources as mod

        result = mod.get_sat_resource_path("report/templates")
        assert isinstance(result, Path)
