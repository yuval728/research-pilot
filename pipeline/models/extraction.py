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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Component-level building blocks
# ---------------------------------------------------------------------------


class ArchitectureComponent(BaseModel):
    """A discrete component of the proposed model / system architecture."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Short identifier, e.g. 'Encoder'.")
    type: str = Field(
        ...,
        description="Component category, e.g. 'transformer', 'CNN', 'attention head'.",
    )
    description: str = Field(
        ..., description="Plain-language description of what this component does."
    )
    inputs: list[str] = Field(
        default_factory=list,
        description="Logical inputs to this component (names or descriptions).",
    )
    outputs: list[str] = Field(
        default_factory=list,
        description="Logical outputs produced by this component.",
    )


class DatasetInfo(BaseModel):
    """Information about a dataset used for training or evaluation."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Dataset name, e.g. 'ImageNet-1K'.")
    size: str | None = Field(
        default=None,
        description="Size descriptor, e.g. '1.2M images', '400GB', '50k samples'.",
    )
    modality: str | None = Field(
        default=None,
        description="Data modality, e.g. 'image', 'text', 'audio', 'multimodal'.",
    )
    split_info: str | None = Field(
        default=None,
        description="Train / validation / test split details if reported.",
    )


class MetricResult(BaseModel):
    """A single evaluation metric reported in the paper."""

    model_config = ConfigDict(populate_by_name=True)

    metric_name: str = Field(
        ..., description="Metric identifier, e.g. 'Top-1 Accuracy', 'BLEU', 'FID'."
    )
    value: str = Field(
        ...,
        description="Reported value as a string to preserve formatting, e.g. '84.2%'.",
    )
    baseline_comparison: str | None = Field(
        default=None,
        description="How this result compares to the strongest baseline, if stated.",
    )


# ---------------------------------------------------------------------------
# Core extraction schema (AI/ML papers)
# ---------------------------------------------------------------------------


class AiMlExtraction(BaseModel):
    """Structured information extracted from an AI/ML research paper.

    Every field is optional at the schema level — partial extractions are
    valid and expected when the paper does not cover a particular aspect.
    """

    model_config = ConfigDict(populate_by_name=True)

    task: str | None = Field(
        default=None,
        description="The ML task addressed, e.g. 'image classification', 'NMT'.",
    )
    problem_statement: str | None = Field(
        default=None,
        description="The core research problem as stated by the authors.",
    )
    key_contributions: list[str] = Field(
        default_factory=list,
        description="Bulleted list of the paper's main contributions.",
    )
    proposed_method_summary: str | None = Field(
        default=None,
        description="High-level prose description of the proposed method.",
    )
    architecture_components: list[ArchitectureComponent] = Field(
        default_factory=list,
        description="Decomposed architecture components with I/O relationships.",
    )
    training_procedure: str | None = Field(
        default=None,
        description="Overview of the training process (optimizer, schedule, etc.).",
    )
    loss_functions: list[str] = Field(
        default_factory=list,
        description="Loss functions used during training.",
    )
    datasets: list[DatasetInfo] = Field(
        default_factory=list,
        description="Datasets used for training and/or evaluation.",
    )
    evaluation_metrics: list[MetricResult] = Field(
        default_factory=list,
        description="Quantitative results reported by the paper.",
    )
    baseline_comparisons: str | None = Field(
        default=None,
        description="Prose summary of which baselines are compared and how.",
    )
    main_results: str | None = Field(
        default=None,
        description="Summary of the headline experimental results.",
    )
    limitations: str | None = Field(
        default=None,
        description="Limitations or failure modes acknowledged by the authors.",
    )
    future_work: str | None = Field(
        default=None,
        description="Future directions suggested by the authors.",
    )
    visual_elements_description: str | None = Field(
        default=None,
        description="Description of key figures, tables, or diagrams in the paper.",
    )
    mathematical_contributions: str | None = Field(
        default=None,
        description="Key equations or mathematical innovations introduced.",
    )


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
        description="Version of AiMlExtraction schema used.",
    )
    extraction: AiMlExtraction = Field(
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
