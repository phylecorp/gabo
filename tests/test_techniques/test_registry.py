"""Test technique registry and all technique registrations.

@decision DEC-TEST-REG-001: Registry completeness and ordering verification.
Tests that all 12 techniques register, can be looked up by ID, are properly
categorized, and maintain correct execution ordering (diagnostic before
contrarian before imaginative). Each technique must have a valid output_schema.
"""

from __future__ import annotations

import pytest

import sat.techniques  # noqa: F401 — trigger registration
from sat.models.base import ArtifactResult
from sat.techniques.registry import (
    get_all_techniques,
    get_technique,
    get_techniques_by_category,
    list_technique_ids,
)


class TestRegistry:
    """All 12 techniques should be registered correctly."""

    def test_twelve_techniques_registered(self):
        assert len(list_technique_ids()) == 12

    def test_all_technique_ids(self):
        expected = {
            "assumptions", "quality", "indicators", "ach",
            "devils_advocacy", "team_ab", "high_impact", "what_if",
            "brainstorming", "outside_in", "red_team", "alt_futures",
        }
        assert set(list_technique_ids()) == expected

    def test_get_technique_by_id(self):
        t = get_technique("ach")
        assert t.metadata.id == "ach"
        assert t.metadata.name == "Analysis of Competing Hypotheses"

    def test_get_unknown_technique_raises(self):
        with pytest.raises(ValueError, match="Unknown technique"):
            get_technique("nonexistent")

    def test_diagnostic_techniques(self):
        diag = get_techniques_by_category("diagnostic")
        assert len(diag) == 4
        ids = [t.metadata.id for t in diag]
        assert "quality" in ids
        assert "assumptions" in ids
        assert "ach" in ids
        assert "indicators" in ids

    def test_contrarian_techniques(self):
        cont = get_techniques_by_category("contrarian")
        assert len(cont) == 4

    def test_imaginative_techniques(self):
        imag = get_techniques_by_category("imaginative")
        assert len(imag) == 4

    def test_ordering_within_categories(self):
        """Techniques should be ordered by their order field within categories."""
        all_techniques = get_all_techniques()
        categories = [t.metadata.category for t in all_techniques]
        diag_end = max(i for i, c in enumerate(categories) if c == "diagnostic")
        cont_start = min(i for i, c in enumerate(categories) if c == "contrarian")
        cont_end = max(i for i, c in enumerate(categories) if c == "contrarian")
        imag_start = min(i for i, c in enumerate(categories) if c == "imaginative")
        assert diag_end < cont_start
        assert cont_end < imag_start

    def test_each_technique_has_output_schema(self):
        """Every technique should have an output_schema that's a Pydantic model."""
        for t in get_all_techniques():
            schema = t.output_schema
            assert issubclass(schema, ArtifactResult), (
                f"{t.metadata.id} output_schema is not an ArtifactResult subclass"
            )
    def test_each_technique_has_dependencies_field(self):
        """Every technique should expose a dependencies list on its metadata."""
        for t in get_all_techniques():
            assert hasattr(t.metadata, "dependencies"), (
                f"{t.metadata.id} metadata missing 'dependencies' field"
            )
            assert isinstance(t.metadata.dependencies, list), (
                f"{t.metadata.id} metadata.dependencies is not a list"
            )


class TestBuildDependencyLayers:
    """Test dependency layer computation for parallel execution."""

    def test_independent_techniques_single_layer(self):
        from sat.techniques.registry import build_dependency_layers
        layers = build_dependency_layers(["quality", "brainstorming", "outside_in"])
        assert len(layers) == 1
        assert set(layers[0]) == {"quality", "brainstorming", "outside_in"}

    def test_linear_chain(self):
        from sat.techniques.registry import build_dependency_layers
        layers = build_dependency_layers(["quality", "assumptions"])
        assert layers == [["quality"], ["assumptions"]]

    def test_diamond_dependencies(self):
        from sat.techniques.registry import build_dependency_layers
        layers = build_dependency_layers(["quality", "assumptions", "ach", "devils_advocacy"])
        assert layers[0] == ["quality"]
        assert layers[1] == ["assumptions"]
        assert layers[2] == ["ach"]
        assert layers[3] == ["devils_advocacy"]

    def test_parallel_in_last_layer(self):
        from sat.techniques.registry import build_dependency_layers
        layers = build_dependency_layers(["quality", "assumptions", "ach", "devils_advocacy", "indicators"])
        # devils_advocacy and indicators both depend on assumptions+ach
        assert len(layers) == 4
        assert set(layers[3]) == {"devils_advocacy", "indicators"}

    def test_empty_list(self):
        from sat.techniques.registry import build_dependency_layers
        assert build_dependency_layers([]) == []

    def test_single_technique(self):
        from sat.techniques.registry import build_dependency_layers
        layers = build_dependency_layers(["quality"])
        assert layers == [["quality"]]

    def test_deps_outside_selected_ignored(self):
        """Dependencies not in the selected set are ignored."""
        from sat.techniques.registry import build_dependency_layers
        # assumptions depends on quality, but quality isn't selected
        layers = build_dependency_layers(["assumptions"])
        assert layers == [["assumptions"]]

