"""GET /api/techniques — list all registered SAT techniques."""

from __future__ import annotations

from fastapi import APIRouter

from sat.api.models import TechniqueInfo

# Import all technique modules so they register themselves before we query the registry.
# This mirrors how the CLI triggers registration — importing sat.techniques ensures the
# @register decorators run.
import sat.techniques  # noqa: F401

from sat.techniques.registry import get_metadata

router = APIRouter()


@router.get("/api/techniques", response_model=list[TechniqueInfo])
async def list_techniques() -> list[TechniqueInfo]:
    """Return all registered techniques sorted by category and order."""
    metadata = get_metadata()
    return [
        TechniqueInfo(
            id=m.id,
            name=m.name,
            category=m.category,
            description=m.description,
            order=m.order,
        )
        for m in metadata
    ]
