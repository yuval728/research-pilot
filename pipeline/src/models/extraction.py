"""
pipeline.models.extraction
~~~~~~~~~~~~~~~~~~~~~~~~~~
Data shapes for the LLM-powered extraction stage.

All fields are optional at the model level — the LLM may not find every piece
of information in every paper. Confidence scoring lives in ExtractionResult.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Wrapper returned by the extraction stage
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = "1.0"

ConfidenceScore = Annotated[
    float,
    Field(ge=0.0, le=1.0, description="LLM confidence in the extraction (0–1)."),
]


class ExtractionResult(BaseModel):
    """The output of the extraction stage for one paper."""

    model_config = ConfigDict(populate_by_name=True)

    paper_id: uuid.UUID = Field(
        ..., description="Foreign key to the Paper that was extracted."
    )
    domain: str | None = Field(
        default=None,
        description="High-level paper domain determined during extraction.",
    )
    schema_version: str = Field(
        default=_SCHEMA_VERSION,
        description="Version of the extraction schema used.",
    )
    extraction: dict[str, Any] = Field(
        ..., description="The structured extraction payload."
    )
    confidence_score: ConfidenceScore = Field(
        default=0.0,
        description="Aggregate LLM confidence for the extraction.",
    )
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when extraction completed.",
    )
