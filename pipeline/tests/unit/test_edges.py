"""
tests/unit/test_edges.py
~~~~~~~~~~~~~~~~~~~~~~~~
Pure-function tests for pipeline/graph/edges.py.

All functions under test are pure: they take a PipelineState dict and return
a routing string. No I/O, no LLM calls, no DB. Each test variant exercises a
distinct branching condition.

Edge functions tested
---------------------
* should_continue_after_classify  — confidence gate + upstream failure detection
* after_extract_route             — extract failure → __end__
* should_run_codegen              — theory-keyword gate + extract-failure gate
* route_on_error                  — generic helper with custom fatal-stage sets
"""

from __future__ import annotations

import pytest

from src.graph.edges import (
    CLASSIFICATION_CONFIDENCE_THRESHOLD,
    THEORY_DOMAIN_KEYWORDS,
    after_extract_route,
    route_on_error,
    should_continue_after_classify,
    should_run_codegen,
)
from src.graph.state import PipelineState, make_initial_state
from src.models.run import StageStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(
    *,
    confidence: float = 0.9,
    sub_domain: str = "Object Detection",
    stage_statuses: dict[str, StageStatus] | None = None,
    errors: list[str] | None = None,
) -> PipelineState:
    """Return a minimal PipelineState dict for edge-function testing."""
    s = make_initial_state()
    s["classification_confidence"] = confidence
    s["sub_domain"] = sub_domain
    s["stage_statuses"] = stage_statuses or {}
    s["errors"] = errors or []
    return s


# ===========================================================================
# should_continue_after_classify
# ===========================================================================


class TestShouldContinueAfterClassify:
    """Routing logic after the classify node."""

    def test_high_confidence_routes_to_extract(self):
        state = _state(confidence=0.95)
        assert should_continue_after_classify(state) == "extract"

    def test_exact_threshold_routes_to_extract(self):
        """Edge: confidence == threshold should pass (>= check)."""
        state = _state(confidence=CLASSIFICATION_CONFIDENCE_THRESHOLD)
        assert should_continue_after_classify(state) == "extract"

    def test_below_threshold_routes_to_end(self):
        state = _state(confidence=CLASSIFICATION_CONFIDENCE_THRESHOLD - 0.01)
        assert should_continue_after_classify(state) == "__end__"

    def test_zero_confidence_routes_to_end(self):
        state = _state(confidence=0.0)
        assert should_continue_after_classify(state) == "__end__"

    def test_failed_ingest_stage_routes_to_end(self):
        state = _state(
            confidence=0.99,
            stage_statuses={"ingest": StageStatus.FAILED},
        )
        assert should_continue_after_classify(state) == "__end__"

    def test_failed_classify_stage_routes_to_end(self):
        state = _state(
            confidence=0.99,
            stage_statuses={"classify": StageStatus.FAILED},
        )
        assert should_continue_after_classify(state) == "__end__"

    def test_completed_stages_do_not_block(self):
        state = _state(
            confidence=0.99,
            stage_statuses={
                "ingest": StageStatus.COMPLETED,
                "classify": StageStatus.COMPLETED,
            },
        )
        assert should_continue_after_classify(state) == "extract"

    def test_empty_stage_statuses_dict_passes(self):
        state = _state(confidence=0.75, stage_statuses={})
        assert should_continue_after_classify(state) == "extract"

    def test_classification_confidence_missing_treated_as_zero(self):
        """Verify default when key is absent from state dict."""
        state = make_initial_state()
        # classification_confidence defaults to 0.0 in make_initial_state
        state["stage_statuses"] = {}
        assert should_continue_after_classify(state) == "__end__"


# ===========================================================================
# after_extract_route
# ===========================================================================


class TestAfterExtractRoute:
    """Routing logic after the extract node."""

    def test_successful_extract_routes_to_summarise(self):
        state = _state(stage_statuses={"extract": StageStatus.COMPLETED})
        assert after_extract_route(state) == "summarise"

    def test_failed_extract_routes_to_end(self):
        state = _state(stage_statuses={"extract": StageStatus.FAILED})
        assert after_extract_route(state) == "__end__"

    def test_pending_extract_routes_to_summarise(self):
        """PENDING is not FAILED, so pipeline continues."""
        state = _state(stage_statuses={"extract": StageStatus.PENDING})
        assert after_extract_route(state) == "summarise"

    def test_no_extract_status_routes_to_summarise(self):
        """Missing key means no failure — pipeline continues."""
        state = _state(stage_statuses={})
        assert after_extract_route(state) == "summarise"

    def test_cached_extract_routes_to_summarise(self):
        state = _state(stage_statuses={"extract": StageStatus.CACHED})
        assert after_extract_route(state) == "summarise"


# ===========================================================================
# should_run_codegen
# ===========================================================================


class TestShouldRunCodegen:
    """Routing logic from the diagram node to codegen or report."""

    def test_cv_domain_runs_codegen(self):
        state = _state(sub_domain="Object Detection")
        assert should_run_codegen(state) == "codegen"

    def test_nlp_domain_runs_codegen(self):
        state = _state(sub_domain="Named Entity Recognition")
        assert should_run_codegen(state) == "codegen"

    @pytest.mark.parametrize("keyword", sorted(THEORY_DOMAIN_KEYWORDS))
    def test_theory_keyword_skips_codegen(self, keyword: str):
        """Every keyword in THEORY_DOMAIN_KEYWORDS should route to report."""
        state = _state(sub_domain=f"Advanced {keyword} methods")
        assert should_run_codegen(state) == "report"

    def test_theory_keyword_case_insensitive(self):
        """The check is performed after .lower(), so casing must not matter."""
        state = _state(sub_domain="OPTIMIZATION Algorithms")
        assert should_run_codegen(state) == "report"

    def test_empty_sub_domain_runs_codegen(self):
        """Empty or None sub_domain means no theory keyword match → codegen."""
        state = _state(sub_domain="")
        assert should_run_codegen(state) == "codegen"

    def test_none_sub_domain_runs_codegen(self):
        s = make_initial_state()
        s["sub_domain"] = None
        s["stage_statuses"] = {}
        assert should_run_codegen(s) == "codegen"

    def test_failed_extract_skips_codegen(self):
        state = _state(
            sub_domain="Object Detection",
            stage_statuses={"extract": StageStatus.FAILED},
        )
        assert should_run_codegen(state) == "report"

    def test_completed_extract_plus_normal_domain_runs_codegen(self):
        state = _state(
            sub_domain="Generative Adversarial Networks",
            stage_statuses={"extract": StageStatus.COMPLETED},
        )
        assert should_run_codegen(state) == "codegen"

    def test_theory_keyword_overrides_even_with_good_extract(self):
        state = _state(
            sub_domain="probability theory",
            stage_statuses={"extract": StageStatus.COMPLETED},
        )
        assert should_run_codegen(state) == "report"


# ===========================================================================
# route_on_error
# ===========================================================================


class TestRouteOnError:
    """Generic error-aware routing helper."""

    def test_no_failures_routes_to_next_node(self):
        state = _state(stage_statuses={})
        result = route_on_error(state, next_node="summarise")
        assert result == "summarise"

    def test_ingest_failure_uses_default_fatal_stages(self):
        state = _state(stage_statuses={"ingest": StageStatus.FAILED})
        result = route_on_error(state, next_node="extract")
        assert result == "__end__"

    def test_extract_failure_uses_default_fatal_stages(self):
        state = _state(stage_statuses={"extract": StageStatus.FAILED})
        result = route_on_error(state, next_node="summarise")
        assert result == "__end__"

    def test_non_fatal_stage_failure_continues(self):
        """Summarise failure is not in default FATAL_STAGES."""
        state = _state(stage_statuses={"summarise": StageStatus.FAILED})
        result = route_on_error(state, next_node="diagram")
        assert result == "diagram"

    def test_custom_fatal_set_honoured(self):
        state = _state(stage_statuses={"summarise": StageStatus.FAILED})
        result = route_on_error(
            state, next_node="diagram", fatal_if_failed=frozenset({"summarise"})
        )
        assert result == "__end__"

    def test_empty_custom_fatal_set_never_halts(self):
        state = _state(stage_statuses={"ingest": StageStatus.FAILED})
        result = route_on_error(state, next_node="extract", fatal_if_failed=frozenset())
        assert result == "extract"

    def test_completed_stages_in_fatal_set_does_not_halt(self):
        """Only FAILED status triggers the halt — COMPLETED is fine."""
        state = _state(stage_statuses={"ingest": StageStatus.COMPLETED})
        result = route_on_error(state, next_node="extract")
        assert result == "extract"
