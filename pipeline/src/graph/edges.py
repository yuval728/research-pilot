"""
pipeline.graph.edges
~~~~~~~~~~~~~~~~~~~~~
Conditional routing logic for the LangGraph StateGraph.

All edge functions are **pure functions** — they receive the current
``PipelineState`` and return the name of the next node as a string.
They have no side-effects, no I/O, and no imports of heavy libraries.

Constants
---------
CLASSIFICATION_CONFIDENCE_THRESHOLD
    If classification confidence falls below this value the graph routes
    to ``END`` instead of ``extract``, since low-confidence domain
    classification would produce unreliable downstream extractions.

THEORY_DOMAIN_KEYWORDS
    Sub-domains that indicate a purely theoretical paper with no
    implementable architecture. ``codegen`` is skipped for these.
"""

from __future__ import annotations

from typing import Literal

from src.graph.state import PipelineState
from src.models.run import StageStatus
from src.core.events import Event, EventType, default_bus
from src.core.logger import get_logger

# ---------------------------------------------------------------------------
# Thresholds and constants
# ---------------------------------------------------------------------------

#: Minimum classification confidence required to continue the pipeline.
CLASSIFICATION_CONFIDENCE_THRESHOLD: float = 0.50

#: Sub-domain keywords that suggest a purely theoretical paper.
#: Code generation is skipped when the sub_domain contains any of these.
THEORY_DOMAIN_KEYWORDS: frozenset[str] = frozenset(
    {
        "theory",
        "theoretical",
        "mathematics",
        "mathematical",
        "optimization",
        "optimisation",
        "convergence",
        "complexity",
        "statistics",
        "statistical learning",
        "information theory",
        "game theory",
        "probability",
        "causal inference",
        "pac learning",
        "vc theory",
        "formal verification",
        "logic",
    }
)

#: Stage names where an error is considered fatal (halt the pipeline).
FATAL_STAGES: frozenset[str] = frozenset({"ingest", "extract"})

# ---------------------------------------------------------------------------
# Edge functions
# ---------------------------------------------------------------------------


def should_continue_after_classify(
    state: PipelineState,
) -> Literal["extract", "__end__"]:
    """Route after ``classify_node``.

    If classification confidence is below the threshold the domain is too
    uncertain to trust — route to ``END`` and surface the error.
    If the ``ingest`` or ``classify`` stage failed (error in state), also
    halt early to avoid cascading failures.

    Parameters
    ----------
    state:
        Current pipeline state.

    Returns
    -------
    ``"extract"`` if confidence is acceptable and no fatal errors exist,
    ``"__end__"`` otherwise.
    """
    # Check for hard failures in already-completed stages
    stage_statuses = state.get("stage_statuses", {})
    for stage in ("ingest", "classify"):
        if stage_statuses.get(stage) == StageStatus.FAILED:
            return "__end__"

    # Confidence gate
    confidence: float = state.get("classification_confidence", 0.0)
    if confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD:
        # Edge functions return only a string — they cannot mutate state.
        # Emit an event so the message is surfaced via SSE / telemetry.
        log = get_logger(__name__)
        msg = (
            f"Classification confidence {confidence:.2f} is below "
            f"threshold {CLASSIFICATION_CONFIDENCE_THRESHOLD}. Halting pipeline."
        )
        log.warning(
            "routing.low_confidence",
            confidence=confidence,
            threshold=CLASSIFICATION_CONFIDENCE_THRESHOLD,
        )
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=state.get("run_id", ""),
                stage_name="classify",
                payload={"error": msg},
            )
        )
        return "__end__"

    return "extract"


def should_run_codegen(
    state: PipelineState,
) -> Literal["codegen", "report"]:
    """Route from ``diagram_node`` to either ``codegen`` or ``report``.

    Skips code generation for purely theoretical papers whose sub-domain
    signals there is no implementable architecture.

    Parameters
    ----------
    state:
        Current pipeline state.

    Returns
    -------
    ``"codegen"`` if the sub_domain supports implementation,
    ``"report"`` to skip directly to the final reporting stage.
    """
    sub_domain: str = (state.get("sub_domain") or "").lower()

    for keyword in THEORY_DOMAIN_KEYWORDS:
        if keyword in sub_domain:
            return "report"

    # Also skip if extract failed (no structured data to generate code from)

    stage_statuses = state.get("stage_statuses", {})
    if stage_statuses.get("extract") == StageStatus.FAILED:
        return "report"

    return "codegen"


def route_on_error(
    state: PipelineState,
    *,
    next_node: str,
    fatal_if_failed: frozenset[str] | None = None,
) -> str:
    """Generic error-aware routing helper.

    Checks whether any stage listed in *fatal_if_failed* has a FAILED
    status. If so, routes to ``"__end__"``. Otherwise routes to
    *next_node*.

    This is a helper intended for use in ``pipeline.py`` when building
    conditional edges that wrap a fixed next-node with error detection,
    rather than being registered directly as a LangGraph edge function.

    Parameters
    ----------
    state:
        Current pipeline state.
    next_node:
        The intended next node name if no fatal error is found.
    fatal_if_failed:
        Set of stage names whose failure should halt the pipeline.
        Defaults to ``FATAL_STAGES``.

    Returns
    -------
    ``next_node`` or ``"__end__"``.
    """
    fatal = fatal_if_failed if fatal_if_failed is not None else FATAL_STAGES
    stage_statuses = state.get("stage_statuses", {})

    for stage in fatal:
        if stage_statuses.get(stage) == StageStatus.FAILED:
            return "__end__"

    return next_node


# ---------------------------------------------------------------------------
# Convenience wrappers registered as LangGraph conditional edges
# ---------------------------------------------------------------------------


def after_extract_route(
    state: PipelineState,
) -> Literal["summarise", "__end__"]:
    """Route after ``extract_node``.

    Halts if extraction itself failed (downstream nodes would be no-ops).
    """

    stage_statuses = state.get("stage_statuses", {})
    if stage_statuses.get("extract") == StageStatus.FAILED:
        return "__end__"
    return "summarise"
