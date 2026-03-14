"""Base artifact models and manifest schema.

@decision DEC-SCHEMA-001: Pydantic v2 BaseModel for all artifacts.
Single source of truth: JSON Schema for LLM structured output, validation,
serialization, and Markdown rendering all derive from the same model.
Field descriptions serve double duty: guide the LLM and document the schema.

@decision DEC-SCHEMA-002: ArtifactResult carries a model_validator(mode='before') safety net.
If the provider-level _deep_deserialize pass is ever bypassed or incomplete, Pydantic itself
will JSON-parse top-level string fields that look like arrays or objects before validation
runs on this class.  Nested BaseModel subclasses trigger their own validators automatically,
so only the top level needs to be handled here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ArtifactResult(BaseModel):
    """Base class for all technique result models.

    Every technique's output model should inherit from this.
    Provides common metadata fields and a pre-validation safety net that
    JSON-parses any string field values that look like JSON arrays or objects.
    """

    @model_validator(mode="before")
    @classmethod
    def _parse_json_strings(cls, data: Any) -> Any:
        """Parse top-level string fields that are JSON-encoded arrays or objects.

        Acts as a safety net for cases where the provider-level deserialization
        pass did not fully unwrap a double-encoded value.  Pydantic recurses
        into nested BaseModel fields automatically, so each submodel triggers
        its own validator — only the top level needs handling here.
        """
        if not isinstance(data, dict):
            return data
        for key, value in data.items():
            if isinstance(value, str) and value.strip() and value.strip()[0] in ("[", "{"):
                try:
                    data[key] = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    pass
        return data

    technique_id: str = Field(description="Identifier of the technique that produced this result")
    technique_name: str = Field(description="Human-readable name of the technique")
    summary: str = Field(description="Brief summary of the key findings from this technique")


class Artifact(BaseModel):
    """Record of a produced artifact file."""

    technique_id: str
    technique_name: str
    category: str
    markdown_path: str
    json_path: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ArtifactManifest(BaseModel):
    """Manifest of all artifacts produced in an analysis run."""

    question: str
    name: str | None = None
    run_id: str
    started_at: datetime
    completed_at: datetime | None = None
    techniques_selected: list[str] = Field(
        description="Technique IDs that were selected for this run"
    )
    techniques_completed: list[str] = Field(
        default_factory=list,
        description="Technique IDs that completed successfully",
    )
    artifacts: list[Artifact] = Field(default_factory=list)
    synthesis_path: str | None = None
    evidence_provided: bool = False
    adversarial_enabled: bool = False
    providers_used: list[str] = Field(default_factory=list)
