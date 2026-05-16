"""GET /api/techniques — list all registered SAT techniques.

@decision DEC-TECH-API-001
@title default_temperature sourced from Technique.temperature property, not TechniqueMetadata
@status accepted
@rationale TechniqueMetadata (the dataclass) does not carry temperature — that lives on the
Technique instance as a property. The endpoint must therefore query get_all_techniques()
(which returns Technique instances) rather than get_metadata() (which returns metadata only).
We iterate the instances and read both .metadata and .temperature in one pass. This keeps the
API layer honest about the actual class-level default without duplicating the value elsewhere.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from sat.api.auth import verify_token
from sat.api.models import TechniqueInfo

# Import all technique modules so they register themselves before we query the registry.
# This mirrors how the CLI triggers registration — importing sat.techniques ensures the
# @register decorators run.
import sat.techniques  # noqa: F401

from sat.techniques.registry import get_all_techniques

router = APIRouter()


@router.get("/api/techniques", response_model=list[TechniqueInfo], dependencies=[Depends(verify_token)])
async def list_techniques() -> list[TechniqueInfo]:
    """Return all registered techniques sorted by category and order.

    default_temperature reflects the technique's class-level temperature property.
    The frontend uses this as the placeholder in temperature override inputs so
    users know what the technique uses by default.
    """
    techniques = get_all_techniques()
    return [
        TechniqueInfo(
            id=t.metadata.id,
            name=t.metadata.name,
            category=t.metadata.category,
            description=t.metadata.description,
            order=t.metadata.order,
            default_temperature=t.temperature,
        )
        for t in techniques
    ]
