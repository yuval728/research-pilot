"""
pipeline/core/telemetry.py

Token usage, latency, and cost tracking per LLM call and per pipeline run.

Every LLM call in the pipeline goes through ``track_llm_call()``, which:
  1. Measures wall-clock latency.
  2. Extracts token counts from the LiteLLM response object.
  3. Estimates cost using LiteLLM's built-in cost calculation.
  4. Appends a TelemetryRecord to the run's TelemetryCollector.
  5. Flushes the record to Langfuse (if enabled in settings).

Usage
-----
    from pipeline.core.telemetry import TelemetryCollector, track_llm_call

    collector = TelemetryCollector(run_id="abc-123")

    async with track_llm_call(collector, stage_name="extract", model="gemini/gemini-2.0-flash") as ctx:
        response = await litellm.acompletion(**ctx.litellm_kwargs)
        ctx.set_response(response)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generator


# ---------------------------------------------------------------------------
# TelemetryRecord — one LLM call
# ---------------------------------------------------------------------------


@dataclass
class TelemetryRecord:
    """Snapshot of token usage and latency for a single LLM call.

    Fields
    ------
    run_id:
        UUID of the pipeline run.
    stage_name:
        Name of the stage that made the call (e.g. ``"extract"``).
    model:
        LiteLLM model string (e.g. ``"gemini/gemini-2.0-flash"``).
    input_tokens:
        Prompt token count (from LiteLLM usage object).
    output_tokens:
        Completion token count.
    latency_ms:
        Wall-clock time for the LLM call in milliseconds.
    cost_usd:
        Estimated cost in USD (via ``litellm.completion_cost``).
    cached:
        Whether the result came from the pipeline cache (no LLM call made).
    timestamp:
        UTC datetime when the call was made.
    """

    run_id: str
    stage_name: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cached: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# TelemetryCollector — accumulates records per run
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """Accumulates LLM telemetry records for a single pipeline run.

    One collector is created per run and passed through the pipeline context.
    At the end of each stage the collector can be flushed to Langfuse.

    Parameters
    ----------
    run_id:
        UUID of the pipeline run.
    """

    def __init__(self, run_id: str, paper_id: str | None = None) -> None:
        self.run_id = run_id
        self.paper_id = paper_id
        self._records: list[TelemetryRecord] = []

    # ------------------------------------------------------------------
    # Record management
    # ------------------------------------------------------------------

    def add(self, record: TelemetryRecord) -> None:
        """Append a telemetry record and flush it to Langfuse."""
        self._records.append(record)
        self._flush_to_langfuse(record)

    @property
    def records(self) -> list[TelemetryRecord]:
        return list(self._records)

    # ------------------------------------------------------------------
    # Aggregate helpers
    # ------------------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self._records)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self._records)

    @property
    def total_latency_ms(self) -> float:
        return sum(r.latency_ms for r in self._records)

    def tokens_by_stage(self) -> dict[str, int]:
        """Return total tokens consumed, grouped by stage name."""
        result: dict[str, int] = {}
        for r in self._records:
            result[r.stage_name] = result.get(r.stage_name, 0) + r.total_tokens
        return result

    def summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for logging or Sentry breadcrumbs."""
        return {
            "run_id": self.run_id,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_latency_ms": round(self.total_latency_ms, 1),
            "call_count": len(self._records),
            "tokens_by_stage": self.tokens_by_stage(),
        }

    def set_paper_id(self, paper_id: str) -> None:
        """Associate this run with a paper ID (Langfuse session_id)."""
        self.paper_id = paper_id

    # ------------------------------------------------------------------
    # Langfuse integration
    # ------------------------------------------------------------------

    def _flush_to_langfuse(self, record: TelemetryRecord) -> None:
        """Send a single record to Langfuse as a generation event.

        Silently skips if Langfuse is disabled in settings.
        """
        try:
            from src.core.config import get_settings

            settings = get_settings()
            if not settings.langfuse.enabled:
                return

            lf = _get_langfuse()
            if not lf:
                return

            # Langfuse SDK: use create_event with trace_context (consistent hyphens).
            lf.create_event(
                name=f"{record.stage_name}.llm_call",
                trace_context={
                    "trace_id": record.run_id.replace("-", ""),
                    "session_id": getattr(self, "paper_id", "").replace("-", ""),
                },
                input=record.input_tokens,
                output=record.output_tokens,
                metadata={
                    "model": record.model,
                    "stage": record.stage_name,
                    "latency_ms": record.latency_ms,
                    "cost_usd": record.cost_usd,
                    "cached": record.cached,
                },
            )

        except Exception as exc:  # noqa: BLE001
            from src.core.logger import get_logger

            get_logger(__name__).warning(
                "langfuse_flush_failed",
                run_id=record.run_id,
                stage=record.stage_name,
                error=str(exc),
            )


# ---------------------------------------------------------------------------

_LANGFUSE_CLIENT: Any = None
_LANGFUSE_INITED: bool = False


def _get_langfuse() -> Any:
    global _LANGFUSE_CLIENT, _LANGFUSE_INITED
    if _LANGFUSE_INITED:
        return _LANGFUSE_CLIENT

    _LANGFUSE_INITED = True
    try:
        from src.core.config import get_settings

        settings = get_settings()

        if not settings.langfuse.enabled:
            return None

        from langfuse import Langfuse

        _LANGFUSE_CLIENT = Langfuse(
            public_key=settings.langfuse.public_key.get_secret_value(),
            secret_key=settings.langfuse.secret_key.get_secret_value(),
            host=settings.langfuse.host,
        )
        return _LANGFUSE_CLIENT
    except Exception:
        return None


# ---------------------------------------------------------------------------
# track_llm_call — context manager
# ---------------------------------------------------------------------------


class _LLMCallContext:
    """Mutable context object yielded inside ``track_llm_call``."""

    def __init__(
        self,
        collector: TelemetryCollector,
        stage_name: str,
        model: str,
    ) -> None:
        self._collector = collector
        self._stage_name = stage_name
        self._model = model
        self._response: Any = None
        self._start_time: float = 0.0

    def set_response(self, response: Any) -> None:
        """Pass the raw LiteLLM response so token counts can be extracted."""
        self._response = response

    def _build_record(self, latency_ms: float) -> TelemetryRecord:
        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0

        if self._response is not None:
            try:
                usage = self._response.usage
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0
            except AttributeError:
                pass

            try:
                import litellm

                cost_usd = litellm.completion_cost(completion_response=self._response)
            except Exception:  # noqa: BLE001
                pass

        return TelemetryRecord(
            run_id=self._collector.run_id,
            stage_name=self._stage_name,
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )


@contextmanager
def track_llm_call(
    collector: TelemetryCollector,
    *,
    stage_name: str,
    model: str,
) -> Generator[_LLMCallContext, None, None]:
    """Context manager that wraps any LiteLLM call with telemetry tracking.

    Measures wall-clock latency, extracts token counts, estimates cost,
    and flushed the record to Langfuse via the collector.

    Parameters
    ----------
    collector:
        The :class:`TelemetryCollector` for the current pipeline run.
    stage_name:
        Name of the stage making the call.
    model:
        LiteLLM model string.

    Example
    -------
    ::

        with track_llm_call(collector, stage_name="extract", model="gemini/gemini-2.0-flash") as ctx:
            response = litellm.completion(model=model, messages=messages)
            ctx.set_response(response)
    """
    ctx = _LLMCallContext(collector, stage_name, model)
    start = time.perf_counter()
    try:
        yield ctx
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        record = ctx._build_record(latency_ms)
        collector.add(record)

        from src.core.logger import get_logger

        get_logger(__name__).debug(
            "llm_call_tracked",
            run_id=collector.run_id,
            stage=stage_name,
            model=model,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            latency_ms=round(latency_ms, 1),
            cost_usd=round(record.cost_usd, 6),
        )
