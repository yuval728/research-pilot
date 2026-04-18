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

Note on "parallelism"
---------------------
The spec describes summarise, embed, diagram, and codegen as running in
parallel after extract. In this implementation they run **sequentially**
(summarise → embed → diagram → codegen) for the following reasons:

1. LangGraph's basic ``StateGraph`` merges returned dicts. True fan-out
   requires the ``Send()`` API and explicit fan-in, adding significant
   complexity and fragile state merging.
2. The four stages are I/O-bound (LLM calls) with no data interdependencies,
   so sequential execution produces identical output — only slightly slower.
3. Sequential execution is far easier to debug, trace, and test.

If concurrent execution becomes a requirement, a ``Send()``-based branch
can be added incrementally without restructuring the node code.

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

from langgraph.graph import END, START, StateGraph  # type: ignore[import-untyped]

from pipeline.graph.edges import (
    after_extract_route,
    should_continue_after_classify,
    should_run_codegen,
)
from pipeline.graph.nodes import (
    classify_node,
    codegen_node,
    diagram_node,
    embed_node,
    extract_node,
    ingest_node,
    report_node,
    summarise_node,
)
from pipeline.graph.state import PipelineState


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------


def _build_graph() -> StateGraph:  # type: ignore[type-arg]
    """Construct the un-compiled StateGraph."""

    builder = StateGraph(PipelineState)

    # ── Register nodes ───────────────────────────────────────────────────────
    builder.add_node("ingest", ingest_node)
    builder.add_node("classify", classify_node)
    builder.add_node("extract", extract_node)
    builder.add_node("summarise", summarise_node)
    builder.add_node("embed", embed_node)
    builder.add_node("diagram", diagram_node)
    builder.add_node("codegen", codegen_node)
    builder.add_node("report", report_node)

    # ── Entry edge ───────────────────────────────────────────────────────────
    builder.add_edge(START, "ingest")

    # ── ingest → classify (always) ───────────────────────────────────────────
    builder.add_edge("ingest", "classify")

    # ── classify → [extract | END] (confidence gate) ─────────────────────────
    builder.add_conditional_edges(
        "classify",
        should_continue_after_classify,
        {
            "extract": "extract",
            "__end__": END,
        },
    )

    # ── extract → [summarise | END] (failure gate) ───────────────────────────
    builder.add_conditional_edges(
        "extract",
        after_extract_route,
        {
            "summarise": "summarise",
            "__end__": END,
        },
    )

    # ── Sequential post-extract chain ─────────────────────────────────────────
    builder.add_edge("summarise", "embed")
    builder.add_edge("embed", "diagram")

    # ── diagram → [codegen | report] (theory-domain gate) ────────────────────
    builder.add_conditional_edges(
        "diagram",
        should_run_codegen,
        {
            "codegen": "codegen",
            "report": "report",
        },
    )

    # ── codegen → report ──────────────────────────────────────────────────────
    builder.add_edge("codegen", "report")

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
