"""
pipeline.graph.nodes.summarise
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``summarise_node`` — generates four summary variants of a paper.

Responsibilities
----------------
1. Works entirely from ``state["extraction"]`` — no PDF needed.
2. Renders ``summarise_v1.j2`` with extraction JSON as context.
3. Makes four separate LiteLLM calls — one per ``SummaryLevel``.
4. Stores all four ``SummaryOutput`` records in the ``outputs`` table.
5. Updates state with ``summaries``.
6. Emits ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pipeline.core.events import Event, EventType, default_bus
from pipeline.core.logger import get_logger
from pipeline.core.telemetry import TelemetryCollector, track_llm_call
from pipeline.graph.state import PipelineState
from pipeline.models.extraction import AiMlExtraction
from pipeline.models.output import SummaryLevel, SummaryOutput
from pipeline.models.run import StageStatus

_STAGE = "summarise"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "summarise_v1.j2"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_prompt(extraction: AiMlExtraction, level: SummaryLevel) -> str:
    """Render summarise_v1.j2 with the extraction data and requested level."""
    import json

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(_PROMPT_PATH.parent)),
        autoescape=False,
    )
    template = env.get_template(_PROMPT_PATH.name)
    return template.render(
        extraction_json=json.dumps(extraction.model_dump(mode="json"), indent=2),
        level=level.value,
    )


def _call_gemini_summarise(
    prompt: str,
    level: SummaryLevel,
    run_id: str,
    collector: TelemetryCollector,
) -> str:
    """Call Gemini for one summary level, return the summary text."""
    import litellm  # type: ignore[import-untyped]

    from pipeline.core.config import get_settings

    settings = get_settings()
    model = settings.gemini.default_model

    messages = [{"role": "user", "content": prompt}]

    with track_llm_call(
        collector, stage_name=f"{_STAGE}.{level.value}", model=model
    ) as ctx:
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=settings.gemini.temperature,
            max_tokens=2048,
            api_key=settings.gemini.api_key.get_secret_value(),
        )
        ctx.set_response(response)

    return (response.choices[0].message.content or "").strip()


def _store_summaries(paper_id: str, summaries: list[SummaryOutput]) -> None:
    """Persist all SummaryOutput records to the ``outputs`` table."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from pipeline.core.config import get_settings
        from pipeline.db.models import OutputORM

        settings = get_settings()
        engine = create_engine(
            settings.supabase.db_url.get_secret_value(), pool_pre_ping=True
        )

        with Session(engine) as session:
            for summary in summaries:
                row = OutputORM(
                    id=uuid.uuid4(),
                    paper_id=uuid.UUID(paper_id),
                    output_type=f"summary_{summary.level.value}",
                    storage_path=f"inline:summary_{summary.level.value}",
                )
                session.add(row)
            session.commit()
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        log.warning("summarise_store_failed", reason=str(exc))


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def summarise_node(state: PipelineState) -> dict[str, Any]:
    """Generate four summary variants from the structured extraction.

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``extraction``

    Writes to state
    ---------------
    - ``summaries``
    - ``stage_statuses["summarise"]``
    - ``token_usage["summarise"]``
    - ``errors`` — appended on failure
    """
    run_id = state["run_id"]
    paper_id: str | None = state.get("paper_id")
    extraction: AiMlExtraction | None = state.get("extraction")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))
    token_usage: dict[str, int] = dict(state.get("token_usage", {}))

    log.info("summarise_node.started", run_id=run_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    if extraction is None:
        msg = f"[{_STAGE}] extraction is None — skipping."
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.SKIPPED
        log.warning("summarise_node.skipped", run_id=run_id, reason="no extraction")
        return {"stage_statuses": stage_statuses, "errors": errors, "summaries": []}

    try:
        collector = TelemetryCollector(run_id=run_id)
        summaries: list[SummaryOutput] = []

        for level in SummaryLevel:
            prompt = _render_prompt(extraction, level)
            content = _call_gemini_summarise(prompt, level, run_id, collector)

            if not content:
                log.warning(
                    "summarise_node.empty_response",
                    run_id=run_id,
                    level=level.value,
                )
                content = f"Summary unavailable for level: {level.value}"

            summaries.append(
                SummaryOutput(
                    paper_id=uuid.UUID(paper_id) if paper_id else uuid.uuid4(),
                    level=level,
                    content=content,
                )
            )
            log.info(
                "summarise_node.level_done",
                run_id=run_id,
                level=level.value,
                length=len(content),
            )

        token_usage[_STAGE] = collector.total_tokens

        if paper_id:
            _store_summaries(paper_id, summaries)

        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={
                    "summary_count": len(summaries),
                    "tokens": token_usage[_STAGE],
                },
            )
        )

        log.info(
            "summarise_node.completed",
            run_id=run_id,
            count=len(summaries),
            tokens=token_usage[_STAGE],
        )

        return {
            "summaries": summaries,
            "stage_statuses": stage_statuses,
            "token_usage": token_usage,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("summarise_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors, "summaries": []}
