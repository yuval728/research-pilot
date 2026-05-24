"""
tests/unit/core/test_telemetry.py

Unit tests for pipeline/core/telemetry.py

Tests verify:
- TelemetryRecord holds correct data and computes total_tokens
- TelemetryCollector accumulates records and produces correct aggregates
- track_llm_call() measures latency and extracts tokens from a mock response
- Langfuse flush failures are silently swallowed (don't crash the pipeline)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.telemetry import (
    TelemetryCollector,
    TelemetryRecord,
    track_llm_call,
)


# ---------------------------------------------------------------------------
# TelemetryRecord
# ---------------------------------------------------------------------------


class TestTelemetryRecord:
    def test_total_tokens(self):
        rec = TelemetryRecord(
            run_id="r1",
            stage_name="extract",
            model="gemini/flash",
            input_tokens=1000,
            output_tokens=500,
        )
        assert rec.total_tokens == 1500

    def test_defaults(self):
        rec = TelemetryRecord(run_id="r1", stage_name="s", model="m")
        assert rec.input_tokens == 0
        assert rec.output_tokens == 0
        assert rec.latency_ms == 0.0
        assert rec.cost_usd == 0.0
        assert rec.cached is False


# ---------------------------------------------------------------------------
# TelemetryCollector
# ---------------------------------------------------------------------------


class TestTelemetryCollector:
    def _make_record(
        self, stage: str, input_t: int = 100, output_t: int = 50
    ) -> TelemetryRecord:
        return TelemetryRecord(
            run_id="run-001",
            stage_name=stage,
            model="gemini/flash",
            input_tokens=input_t,
            output_tokens=output_t,
            latency_ms=200.0,
            cost_usd=0.001,
        )

    def test_add_record(self):
        collector = TelemetryCollector(run_id="r1")
        with patch.object(collector, "_flush_to_langfuse"):
            rec = self._make_record("ingest")
            collector.add(rec)
        assert len(collector.records) == 1
        assert collector.records[0] is rec

    def test_total_tokens_sum(self):
        collector = TelemetryCollector(run_id="r1")
        with patch.object(collector, "_flush_to_langfuse"):
            collector.add(self._make_record("ingest", input_t=100, output_t=50))  # 150
            collector.add(self._make_record("extract", input_t=200, output_t=80))  # 280
        assert collector.total_tokens == 430

    def test_total_cost_sum(self):
        collector = TelemetryCollector(run_id="r1")
        with patch.object(collector, "_flush_to_langfuse"):
            r1 = self._make_record("ingest")
            r1 = TelemetryRecord(**{**r1.__dict__, "cost_usd": 0.001})
            r2 = self._make_record("extract")
            r2 = TelemetryRecord(**{**r2.__dict__, "cost_usd": 0.003})
            collector.add(r1)
            collector.add(r2)
        assert collector.total_cost_usd == pytest.approx(0.004)

    def test_tokens_by_stage(self):
        collector = TelemetryCollector(run_id="r1")
        with patch.object(collector, "_flush_to_langfuse"):
            collector.add(self._make_record("ingest", input_t=100, output_t=50))
            collector.add(self._make_record("extract", input_t=200, output_t=100))
            collector.add(self._make_record("ingest", input_t=50, output_t=25))
        result = collector.tokens_by_stage()
        assert result["ingest"] == 225
        assert result["extract"] == 300

    def test_summary_keys(self):
        collector = TelemetryCollector(run_id="r1")
        summary = collector.summary()
        assert "run_id" in summary
        assert "total_tokens" in summary
        assert "total_cost_usd" in summary
        assert "total_latency_ms" in summary
        assert "call_count" in summary
        assert "tokens_by_stage" in summary

    def test_langfuse_flush_failure_does_not_raise(self):
        """Langfuse errors must not crash the pipeline."""
        collector = TelemetryCollector(run_id="r1")
        with patch.object(
            collector, "_flush_to_langfuse", side_effect=RuntimeError("network error")
        ):
            # The error is swallowed inside add() only if _flush_to_langfuse
            # itself swallows it. Let's verify the collector's _flush_to_langfuse
            # handles errors gracefully by testing with a real call that will
            # fail due to no settings:
            pass

        # Now test that the real implementation doesn't crash when Langfuse
        # fails on a real add() (settings not configured):
        rec = self._make_record("embed")
        # This will try to import and initialise Langfuse; it should fail
        # silently because LANGFUSE_* env vars aren't set in tests.
        with patch(
            "pipeline.core.config.get_settings", side_effect=Exception("no settings")
        ):
            collector._flush_to_langfuse(rec)  # should not raise


# ---------------------------------------------------------------------------
# track_llm_call context manager
# ---------------------------------------------------------------------------


class _MockUsage:
    prompt_tokens = 400
    completion_tokens = 200


class _MockResponse:
    usage = _MockUsage()


class TestTrackLLMCall:
    def _make_collector(self) -> TelemetryCollector:
        c = TelemetryCollector(run_id="run-test")
        # Patch Langfuse flush so tests don't require real credentials
        c._flush_to_langfuse = MagicMock()  # type: ignore[method-assign]
        return c

    def test_record_added_after_context(self):
        collector = self._make_collector()
        with track_llm_call(
            collector, stage_name="extract", model="gemini/flash"
        ) as ctx:
            ctx.set_response(_MockResponse())
        assert len(collector.records) == 1

    def test_token_counts_extracted(self):
        collector = self._make_collector()
        with track_llm_call(
            collector, stage_name="extract", model="gemini/flash"
        ) as ctx:
            ctx.set_response(_MockResponse())
        rec = collector.records[0]
        assert rec.input_tokens == 400
        assert rec.output_tokens == 200

    def test_latency_is_positive(self):
        collector = self._make_collector()
        with track_llm_call(
            collector, stage_name="ingest", model="gemini/flash"
        ) as ctx:
            time.sleep(0.01)  # 10ms minimum
            ctx.set_response(_MockResponse())
        rec = collector.records[0]
        assert rec.latency_ms >= 5.0

    def test_record_added_even_on_exception(self):
        """Telemetry should be recorded even if the LLM call raises."""
        collector = self._make_collector()
        with pytest.raises(RuntimeError):
            with track_llm_call(collector, stage_name="extract", model="gemini/flash"):
                raise RuntimeError("boom")
        # Record is still appended (with zeroed counts)
        assert len(collector.records) == 1

    def test_no_response_set_gives_zero_tokens(self):
        """If ctx.set_response() is never called, token counts default to 0."""
        collector = self._make_collector()
        with track_llm_call(collector, stage_name="summarise", model="gemini/flash"):
            pass  # no response set
        rec = collector.records[0]
        assert rec.input_tokens == 0
        assert rec.output_tokens == 0

    def test_stage_and_model_fields_set(self):
        collector = self._make_collector()
        with track_llm_call(
            collector, stage_name="classify", model="gemini/pro"
        ) as ctx:
            ctx.set_response(_MockResponse())
        rec = collector.records[0]
        assert rec.stage_name == "classify"
        assert rec.model == "gemini/pro"
        assert rec.run_id == "run-test"
