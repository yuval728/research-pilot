"""
pipeline.models.run
~~~~~~~~~~~~~~~~~~~~
Data shapes for pipeline execution runs and per-stage status tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    """Top-level status of a full pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some stages completed; others failed or were skipped.


class StageStatus(str, Enum):
    """Status of a single pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CACHED = "cached"  # Result was served from cache; stage did not execute.


# ---------------------------------------------------------------------------
# Stage-level result
# ---------------------------------------------------------------------------


class StageResult(BaseModel):
    """Execution record for a single pipeline stage."""

    model_config = ConfigDict(populate_by_name=True)

    stage_name: str = Field(..., description="Canonical name of this stage.")
    status: StageStatus = Field(
        default=StageStatus.PENDING,
        description="Current status of this stage.",
    )
    started_at: datetime | None = Field(
        default=None, description="UTC timestamp when the stage began executing."
    )
    completed_at: datetime | None = Field(
        default=None, description="UTC timestamp when the stage finished (or failed)."
    )
    error_message: str | None = Field(
        default=None,
        description="Human-readable error detail if status is FAILED.",
    )
    cached: bool = Field(
        default=False,
        description="True when the result was returned from cache.",
    )
    token_count: int | None = Field(
        default=None,
        ge=0,
        description="Total LLM tokens consumed by this stage (prompt + completion).",
    )

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock seconds between start and completion, or ``None``."""
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


# ---------------------------------------------------------------------------
# Run-level entity
# ---------------------------------------------------------------------------


class PipelineRun(BaseModel):
    """A full execution of the pipeline for a single paper."""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for this run.",
    )
    paper_id: uuid.UUID = Field(
        ..., description="Foreign key to the Paper being processed."
    )
    status: RunStatus = Field(
        default=RunStatus.PENDING,
        description="Aggregate run status.",
    )
    stages: dict[str, StageResult] = Field(
        default_factory=dict,
        description="Mapping of stage_name → StageResult for every stage in this run.",
    )
    started_at: datetime | None = Field(
        default=None, description="UTC timestamp when the run was kicked off."
    )
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the run finished (success or failure).",
    )
    total_tokens: int = Field(
        default=0,
        ge=0,
        description="Cumulative LLM tokens across all stages.",
    )
    error: str | None = Field(
        default=None,
        description="Top-level error message if the run failed catastrophically.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this run record was created.",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def add_stage(self, stage_name: str) -> StageResult:
        """Register a new stage in PENDING state and return it."""
        result = StageResult(stage_name=stage_name)
        self.stages[stage_name] = result
        return result

    def update_total_tokens(self) -> None:
        """Re-compute ``total_tokens`` from all stage token counts."""
        self.total_tokens = sum(
            s.token_count for s in self.stages.values() if s.token_count is not None
        )
