"""
pipeline.models.output
~~~~~~~~~~~~~~~~~~~~~~~
Data shapes for the artefacts produced by the pipeline's output stages:
summaries, diagrams, generated code, reports, and the assembled bundle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SummaryLevel(str, Enum):
    """Granularity / style of a generated summary."""

    PARAGRAPH = "paragraph"  # Single cohesive paragraph.
    SECTION_BY_SECTION = "section_by_section"  # Mirrors paper structure.
    BULLETS = "bullets"  # Concise bullet points.
    ELI5 = "eli5"  # Explain Like I'm 5.


class DiagramType(str, Enum):
    """Category of auto-generated diagram."""

    ARCHITECTURE = "architecture"  # Static model / system diagram.
    TRAINING_FLOW = "training_flow"  # Training loop / data-flow graph.
    INFERENCE_FLOW = "inference_flow"  # Inference / serving graph.


# ---------------------------------------------------------------------------
# Individual output types
# ---------------------------------------------------------------------------


class SummaryOutput(BaseModel):
    """A generated natural-language summary at a requested level of detail."""

    model_config = ConfigDict(populate_by_name=True)

    paper_id: uuid.UUID = Field(..., description="Foreign key to the source Paper.")
    level: SummaryLevel = Field(..., description="Granularity / style of this summary.")
    content: str = Field(..., min_length=1, description="The summary text.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this summary was generated.",
    )


class DiagramOutput(BaseModel):
    """A generated diagram represented as a DSL string (Mermaid or D2)."""

    model_config = ConfigDict(populate_by_name=True)

    paper_id: uuid.UUID = Field(..., description="Foreign key to the source Paper.")
    diagram_type: DiagramType = Field(..., description="Category of diagram.")
    dsl_code: str = Field(
        ...,
        min_length=1,
        description="Raw diagram DSL source (Mermaid or D2 syntax).",
    )
    svg_path: str | None = Field(
        None,
        description="Relative path to the rendered SVG file, if available.",
    )
    dsl_language: str = Field(
        default="mermaid",
        description="DSL used: 'mermaid' or 'd2'.",
        pattern=r"^(mermaid|d2)$",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this diagram was generated.",
    )


class CodeOutput(BaseModel):
    """Paths to generated Python code and notebook artefacts."""

    model_config = ConfigDict(populate_by_name=True)

    paper_id: uuid.UUID = Field(..., description="Foreign key to the source Paper.")
    python_path: str | None = Field(
        None,
        description="Relative path to the generated .py script.",
    )
    notebook_path: str | None = Field(
        None,
        description="Relative path to the generated .ipynb notebook.",
    )
    synthetic_data_description: str | None = Field(
        None,
        description="Description of any synthetic data generated to demonstrate the method.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when code generation completed.",
    )


class ReportOutput(BaseModel):
    """Path to the full Markdown research report."""

    model_config = ConfigDict(populate_by_name=True)

    paper_id: uuid.UUID = Field(..., description="Foreign key to the source Paper.")
    markdown_path: str = Field(
        ...,
        min_length=1,
        description="Relative path to the generated Markdown report file.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the report was written.",
    )


# ---------------------------------------------------------------------------
# Assembled bundle
# ---------------------------------------------------------------------------


class OutputBundle(BaseModel):
    """The complete set of pipeline outputs for a single paper.

    All fields except ``paper_id`` are optional — the bundle may be partially
    populated if only some stages have completed.
    """

    model_config = ConfigDict(populate_by_name=True)

    paper_id: uuid.UUID = Field(..., description="Foreign key to the source Paper.")
    summaries: list[SummaryOutput] = Field(
        default_factory=list,
        description="All generated summaries, one per SummaryLevel requested.",
    )
    diagrams: list[DiagramOutput] = Field(
        default_factory=list,
        description="All generated diagrams, one per DiagramType requested.",
    )
    code: CodeOutput | None = Field(
        None, description="Generated code artefacts, if code generation was run."
    )
    report: ReportOutput | None = Field(
        None, description="Generated Markdown report, if reporting was run."
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_summary(self, level: SummaryLevel) -> SummaryOutput | None:
        """Return the summary for the requested level, or ``None``."""
        return next((s for s in self.summaries if s.level == level), None)

    def get_diagram(self, diagram_type: DiagramType) -> DiagramOutput | None:
        """Return the diagram for the requested type, or ``None``."""
        return next((d for d in self.diagrams if d.diagram_type == diagram_type), None)

    @property
    def is_complete(self) -> bool:
        """True when all standard output types are present."""
        return (
            len(self.summaries) > 0
            and len(self.diagrams) > 0
            and self.code is not None
            and self.report is not None
        )
