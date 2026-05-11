"""
pipeline.models.paper
~~~~~~~~~~~~~~~~~~~~~
Data shapes for research papers entering the pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from src.models.run import PipelineRun


class PaperSource(str, Enum):
    """Where the paper originated from."""

    PDF_UPLOAD = "pdf_upload"
    ARXIV_URL = "arxiv_url"
    DOI = "doi"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class PaperMetadata(BaseModel):
    """Bibliographic and domain metadata extracted from the paper."""

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(..., min_length=1, description="Full title of the paper.")
    authors: list[str] = Field(
        default_factory=list, description="Ordered list of author names."
    )
    abstract: str | None = Field(None, description="Paper abstract.")
    venue: str | None = Field(
        None, description="Conference or journal where the paper was published."
    )
    year: int | None = Field(
        None, ge=1900, le=2100, description="Publication year (YYYY)."
    )
    arxiv_id: str | None = Field(
        None,
        pattern=r"^\d{4}\.\d{4,5}(v\d+)?$",
        description="ArXiv identifier, e.g. '2301.00001' or '2301.00001v2'.",
    )
    doi: str | None = Field(
        None,
        description="Digital Object Identifier, e.g. '10.1145/3292500.3330919'.",
    )
    page_count: int | None = Field(None, ge=1, description="Number of pages.")
    domain: str | None = Field(
        None, description="High-level domain, e.g. 'Computer Vision'."
    )
    sub_domain: str | None = Field(
        None, description="Sub-domain, e.g. 'Object Detection'."
    )


# ---------------------------------------------------------------------------
# Core entity
# ---------------------------------------------------------------------------


class Paper(BaseModel):
    """A research paper tracked by the pipeline."""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for this paper.",
    )
    source: PaperSource = Field(..., description="How this paper was provided.")
    source_url: AnyHttpUrl | None = Field(
        None,
        description="Original URL (ArXiv or DOI resolver) if not a direct upload.",
    )
    pdf_storage_path: str | None = Field(
        None,
        description="Relative path to the stored PDF file on disk / object storage.",
    )
    metadata: PaperMetadata | None = Field(
        None,
        description="Bibliographic metadata (populated after ingestion stage).",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the record was created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the last update.",
    )


class PaperListItem(BaseModel):
    """Paper payload enriched with the latest pipeline run."""

    model_config = ConfigDict(populate_by_name=True)

    paper: Paper
    latest_run: PipelineRun | None = None


# ---------------------------------------------------------------------------
# Input / creation model
# ---------------------------------------------------------------------------


class PaperCreate(BaseModel):
    """Input model for adding a new paper to the pipeline.

    Exactly one of ``source_url`` (for ArXiv / DOI) or ``pdf_file_path``
    (for direct upload) must be provided alongside the matching ``source``.
    """

    model_config = ConfigDict(populate_by_name=True)

    source: PaperSource = Field(..., description="Origin of the paper.")
    source_url: Annotated[
        AnyHttpUrl | None,
        Field(
            None,
            description="URL for ArXiv or DOI-resolver sources.",
        ),
    ] = None
    pdf_file_path: str | None = Field(
        None,
        description="Local path to PDF for direct upload source.",
    )
    title_hint: str | None = Field(
        None,
        description="Optional title hint to speed up metadata extraction.",
    )

    def model_post_init(self, __context: object) -> None:  # noqa: D102
        if self.source == PaperSource.PDF_UPLOAD:
            if not self.pdf_file_path:
                raise ValueError("pdf_file_path is required when source is PDF_UPLOAD.")
        else:
            if not self.source_url:
                raise ValueError(
                    "source_url is required when source is ARXIV_URL or DOI."
                )
