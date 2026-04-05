"""
pipeline.graph.state
~~~~~~~~~~~~~~~~~~~~
Defines PipelineState — the single TypedDict that flows through every
LangGraph node. All node inputs and outputs are sub-dicts of this type.

Design rules
------------
- Every field is ``NotRequired`` so nodes can return partial state dicts.
- LangGraph merges the returned partial dict into the live state.
- Nothing is passed between nodes outside of state.
- Mutation never happens in-place; nodes return new values via the dict.
"""

from __future__ import annotations

import uuid
from typing import Any

from typing_extensions import NotRequired, TypedDict

from pipeline.models.extraction import AiMlExtraction
from pipeline.models.output import CodeOutput, DiagramOutput, SummaryOutput
from pipeline.models.paper import PaperMetadata
from pipeline.models.run import StageStatus


class PipelineState(TypedDict):
    """The single state object that flows through every LangGraph node.

    Fields
    ------
    run_id:
        UUID string of the pipeline run (set at pipeline entry).
    paper_id:
        UUID string of the paper record in the DB (set after ingest).
    pdf_storage_path:
        Supabase Storage path to the uploaded PDF in the ``papers`` bucket.
    pdf_bytes:
        In-memory raw PDF bytes — fetched once in ``classify`` and reused
        by subsequent stages so we avoid redundant Storage round-trips.
    paper_metadata:
        Bibliographic metadata populated during ingest.
    domain:
        High-level classification domain, e.g. ``"Computer Vision"``.
    sub_domain:
        Fine-grained sub-domain, e.g. ``"Object Detection"``.
    classification_confidence:
        LLM confidence for the classification (0–1).
    extraction:
        Validated ``AiMlExtraction`` payload produced by extract_node.
    summaries:
        List of ``SummaryOutput`` records, one per ``SummaryLevel``.
    diagrams:
        List of ``DiagramOutput`` records, one per ``DiagramType``.
    code_output:
        Generated code artefacts (paths to .py file and .ipynb notebook).
    report_path:
        Supabase Storage path to the assembled Markdown report.
    stage_statuses:
        Dict mapping stage name → ``StageStatus`` enum value.
    errors:
        Accumulated human-readable error messages across all stages.
    token_usage:
        Dict mapping stage name → total tokens consumed by that stage.
    cached_stages:
        Set of stage names whose results were served from cache.
    """

    run_id: str
    paper_id: NotRequired[str | None]
    pdf_storage_path: NotRequired[str | None]
    pdf_bytes: NotRequired[bytes | None]
    paper_metadata: NotRequired[PaperMetadata | None]
    domain: NotRequired[str | None]
    sub_domain: NotRequired[str | None]
    classification_confidence: NotRequired[float]
    extraction: NotRequired[AiMlExtraction | None]
    summaries: NotRequired[list[SummaryOutput]]
    diagrams: NotRequired[list[DiagramOutput]]
    code_output: NotRequired[CodeOutput | None]
    report_path: NotRequired[str | None]
    stage_statuses: NotRequired[dict[str, StageStatus]]
    errors: NotRequired[list[str]]
    token_usage: NotRequired[dict[str, int]]
    cached_stages: NotRequired[set[str]]


def make_initial_state(
    run_id: str | None = None,
    *,
    paper_metadata: PaperMetadata | None = None,
    pdf_bytes: bytes | None = None,
    extra: dict[str, Any] | None = None,
) -> PipelineState:
    """Build a fully-initialised ``PipelineState`` with safe defaults.

    Parameters
    ----------
    run_id:
        UUID string for the pipeline run. Auto-generated if not provided.
    paper_metadata:
        Optional pre-populated bibliographic metadata (e.g. from API call
        before pipeline invocation).
    pdf_bytes:
        Optional raw PDF bytes if the caller already has them in memory.
    extra:
        Any additional key/value pairs to merge into the initial state.

    Returns
    -------
    PipelineState
        A fully initialised state dict ready to pass into the graph.
    """
    state: PipelineState = {
        "run_id": run_id or str(uuid.uuid4()),
        "paper_id": None,
        "pdf_storage_path": None,
        "pdf_bytes": pdf_bytes,
        "paper_metadata": paper_metadata,
        "domain": None,
        "sub_domain": None,
        "classification_confidence": 0.0,
        "extraction": None,
        "summaries": [],
        "diagrams": [],
        "code_output": None,
        "report_path": None,
        "stage_statuses": {},
        "errors": [],
        "token_usage": {},
        "cached_stages": set(),
    }

    if extra:
        # TypedDict doesn't support dynamic update; use cast-safe merge
        for k, v in extra.items():
            state[k] = v  # type: ignore[literal-required]

    return state
