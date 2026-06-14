"""
pipeline.graph.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~
Builds and compiles the LangGraph ``StateGraph``.

This is the **only** file that knows the full graph topology. All other
modules are concerned only with their own node or edge logic.

Graph topology
--------------
::

    START
      │
      ▼
    ingest
      │
      ▼
    metadata ──[already populated?]─► classify (skip)
      │
      ▼
    classify ──[confidence < 0.5]──► END
      │
      ▼ (confidence ≥ 0.5)
    extract ──[extract failed]──────► END
      │
      ▼
    summarise
      │
      ▼
    embed
      │
      ▼
    diagram
      │
      ▼ [conditional: theory domain?]
    codegen ──────────────────────────┐
      │                               │ (skipped for theory papers)
      ▼                               ▼
    report ◄──────────────────────────┘
      │
      ▼
     END

Parallelism
-----------
After ``extract``, the four independent stages (summarise, embed, diagram,
codegen) have **zero data dependencies** between them — they all read from
``extraction`` and write to disjoint state fields.  Rather than the original
sequential chain, they now run inside a single ``parallel_stages_node`` that
uses ``asyncio.gather`` to fan out all four LLM workloads concurrently.

This eliminates the idle time between stages (previously each waited for the
previous to finish before even starting its first LLM call).

Exports
-------
    research_pipeline : CompiledGraph
        The compiled LangGraph graph. Import and call ``.invoke()`` or
        ``.stream()`` to run the pipeline.

Usage
-----
::

    from pipeline.graph.pipeline import research_pipeline
    from pipeline.graph.state import make_initial_state

    state = make_initial_state(run_id="abc-123", pdf_bytes=pdf_bytes)
    result = research_pipeline.invoke(state)
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.core.logger import get_logger

from langgraph.graph import END, START, StateGraph  # type: ignore[import-untyped]

from src.graph.edges import (
    after_extract_route,
    should_continue_after_classify,
    should_run_codegen,
)
from src.graph.nodes import (
    classify_node,
    codegen_node,
    diagram_node,
    embed_node,
    extract_node,
    ingest_node,
    metadata_node,
    report_node,
    summarise_node,
)
from src.graph.state import PipelineState
from src.models.run import StageStatus


# ---------------------------------------------------------------------------
# Parallel stages node
# ---------------------------------------------------------------------------


def _merge_parallel_results(
    base: PipelineState, results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Merge results from parallel stage dicts into a single update dict.

    Each parallel node returns a partial state dict.  We merge them
    carefully: list fields are unioned, dict fields are merged shallowly,
    set fields are unioned.
    """
    merged: dict[str, Any] = {}

    for result in results:
        for key, value in result.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(value, dict) and isinstance(merged[key], dict):
                merged[key] = {**merged[key], **value}
            elif isinstance(value, list) and isinstance(merged[key], list):
                merged[key] = merged[key] + value
            elif isinstance(value, set) and isinstance(merged[key], set):
                merged[key] = merged[key] | value
            else:
                # For scalar fields (stage_statuses individual keys handled via dict merge above)
                merged[key] = value

    return merged


async def parallel_stages_node(state: PipelineState) -> dict[str, Any]:
    """Run summarise, embed, diagram, and codegen in parallel.

    All four stages read from ``state["extraction"]`` and write to
    disjoint state fields.  They are fanned out via ``asyncio.gather``
    and their results are merged into a single state update dict.

    Reads from state
    ----------------
    - All fields that summarise / embed / diagram / codegen individually read

    Writes to state
    ---------------
    - All fields that summarise / embed / diagram / codegen individually write
    """
    log = get_logger(__name__)
    run_id = state["run_id"]

    run_codegen = should_run_codegen(state) == "codegen"

    log.info(
        "parallel_stages_node.started",
        run_id=run_id,
        run_codegen=run_codegen,
    )

    # Run each async node concurrently
    tasks = [
        summarise_node(state),
        embed_node(state),
        diagram_node(state),
    ]
    if run_codegen:
        tasks.append(codegen_node(state))

    results = list(await asyncio.gather(*tasks))

    # If codegen was skipped, inject a SKIPPED status
    if not run_codegen:
        results.append(
            {
                "stage_statuses": {
                    **state.get("stage_statuses", {}),
                    "codegen": StageStatus.SKIPPED,
                },
                "code_output": None,
            }
        )

    merged = _merge_parallel_results(state, results)
    log.info("parallel_stages_node.completed", run_id=run_id)
    return merged


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:  # type: ignore[type-arg]
    """Construct the un-compiled StateGraph."""

    builder = StateGraph(PipelineState)

    # ── Register nodes ───────────────────────────────────────────────────────
    builder.add_node("ingest", ingest_node)
    builder.add_node("metadata", metadata_node)
    builder.add_node("classify", classify_node)
    builder.add_node("extract", extract_node)
    builder.add_node("parallel_stages", parallel_stages_node)
    builder.add_node("report", report_node)

    # ── Entry edge ───────────────────────────────────────────────────────────
    builder.add_edge(START, "ingest")

    # ── ingest → metadata → classify (always) ─────────────────────────────────
    builder.add_edge("ingest", "metadata")
    builder.add_edge("metadata", "classify")

    # ── classify → [extract | END] (confidence gate) ─────────────────────────
    builder.add_conditional_edges(
        "classify",
        should_continue_after_classify,
        {
            "extract": "extract",
            "__end__": END,
        },
    )

    # ── extract → [parallel_stages | END] (failure gate) ────────────────────
    builder.add_conditional_edges(
        "extract",
        after_extract_route,
        {
            "summarise": "parallel_stages",  # "summarise" key maps to parallel node
            "__end__": END,
        },
    )

    # ── parallel_stages → report ──────────────────────────────────────────────
    builder.add_edge("parallel_stages", "report")

    # ── report → END ─────────────────────────────────────────────────────────
    builder.add_edge("report", END)

    return builder


# ---------------------------------------------------------------------------
# Compile and export
# ---------------------------------------------------------------------------

#: The compiled LangGraph pipeline. This is the primary public API of the
#: graph module. Invoke with a ``PipelineState`` dict.
research_pipeline = _build_graph().compile()

__all__ = ["research_pipeline"]
