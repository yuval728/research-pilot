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

from pydantic import BaseModel
from src.models.output import CodeOutput, DiagramOutput, SummaryOutput
from src.models.paper import PaperMetadata
from src.models.run import StageStatus


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
        **Why StageStatus enum**: LangGraph conditional edges need deterministic
        routing. String statuses like "done" vs "completed" would be fragile.
        The enum ensures edges in edges.py can do exact comparisons.
    errors:
        Accumulated human-readable error messages across all stages.
        **Error accumulation pattern**: Instead of failing fast, stages append
        errors and continue. The ``report`` node runs regardless and surfaces
        all errors in the final markdown. This makes partial failures debuggable
        without losing successful stage outputs.
    token_usage:
        Dict mapping stage name → total tokens consumed by that stage.
        **Token budget enforcement**: Before each LLM call, stages check
        ``sum(token_usage.values())`` against ``PIPELINE_TOKEN_BUDGET_PER_PAPER``
        (default 500k). Stages early-return with TokenBudgetExceededError
        if the budget would be exceeded.
    cached_stages:
        Set of stage names whose results were served from cache.
        **Cache key derivation**: Cache hits are determined by
        (paper_id, stage_name, schema_version, prompt_version). The extraction
        stage includes schema_version from the domain plugin; diagram includes
        diagram_type in the key. Implemented in each node's _load_cached_*
        helper.
    """

    run_id: str
    paper_id: NotRequired[str | None]
    pdf_storage_path: NotRequired[str | None]
    pdf_bytes: NotRequired[bytes | None]
    paper_metadata: NotRequired[PaperMetadata | None]
    domain: NotRequired[str | None]
    sub_domain: NotRequired[str | None]
    classification_confidence: NotRequired[float]
    extraction: NotRequired[BaseModel | None]
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
