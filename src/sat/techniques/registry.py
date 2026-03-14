"""Technique registry for discovering and resolving technique instances.

@decision DEC-TECH-REG-001: Explicit registration instead of auto-discovery.
Techniques register themselves in a module-level dict. This is simpler than
import-scanning and makes the available techniques immediately visible.
"""

from __future__ import annotations

from sat.techniques.base import Technique, TechniqueMetadata

# Global registry: technique_id -> Technique instance
_REGISTRY: dict[str, Technique] = {}


def register(technique: Technique) -> Technique:
    """Register a technique instance in the global registry."""
    tid = technique.metadata.id
    if tid in _REGISTRY:
        raise ValueError(f"Duplicate technique ID: {tid!r}")
    _REGISTRY[tid] = technique
    return technique


def get_technique(technique_id: str) -> Technique:
    """Get a registered technique by ID."""
    if technique_id not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"Unknown technique: {technique_id!r}. Available: {available}"
        )
    return _REGISTRY[technique_id]


def get_all_techniques() -> list[Technique]:
    """Get all registered techniques, sorted by category and order."""
    category_order = {"diagnostic": 0, "contrarian": 1, "imaginative": 2}
    return sorted(
        _REGISTRY.values(),
        key=lambda t: (category_order.get(t.metadata.category, 99), t.metadata.order),
    )


def get_techniques_by_category(category: str) -> list[Technique]:
    """Get all techniques in a category, sorted by order."""
    return sorted(
        [t for t in _REGISTRY.values() if t.metadata.category == category],
        key=lambda t: t.metadata.order,
    )


def list_technique_ids() -> list[str]:
    """List all registered technique IDs."""
    return sorted(_REGISTRY.keys())


def get_metadata() -> list[TechniqueMetadata]:
    """Get metadata for all registered techniques, sorted."""
    return [t.metadata for t in get_all_techniques()]


def build_dependency_layers(technique_ids: list[str]) -> list[list[str]]:
    """Group technique IDs into dependency layers for parallel execution.

    Each layer contains techniques whose dependencies are all satisfied by
    earlier layers. Techniques within a layer can run concurrently.

    Falls back to sequential (one technique per layer) if dependency
    extraction fails or a cycle is detected.

    @decision DEC-PIPE-003: Layer-based parallel technique execution.
    Techniques with satisfied dependencies run concurrently within a layer.
    Falls back to sequential if dependency resolution fails.
    """
    if not technique_ids:
        return []

    # Build dependency graph restricted to selected techniques
    selected = set(technique_ids)
    deps: dict[str, set[str]] = {}
    for tid in technique_ids:
        try:
            technique = _REGISTRY[tid]
            # Only include dependencies that are in the selected set
            deps[tid] = set(technique.metadata.dependencies) & selected
        except (KeyError, AttributeError):
            # Fallback: sequential execution
            return [[tid] for tid in technique_ids]

    layers: list[list[str]] = []
    placed: set[str] = set()
    remaining = set(technique_ids)

    while remaining:
        # Find techniques whose dependencies are all placed
        layer = [tid for tid in technique_ids if tid in remaining and deps[tid] <= placed]
        if not layer:
            # Cycle or unresolvable dependency — fall back to sequential
            return [[tid] for tid in technique_ids]
        layers.append(layer)
        placed.update(layer)
        remaining -= set(layer)

    return layers

