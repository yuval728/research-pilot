"""
pipeline.graph.nodes.summarise
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``summarise_node`` — generates four summary variants of a paper.

Responsibilities
----------------
1. Works entirely from ``state["extraction"]`` — no PDF needed.
2. Renders ``summarise_v1.j2`` with extraction JSON as context.
3. Makes four **parallel** LiteLLM calls — one per ``SummaryLevel``.
4. Stores all four ``SummaryOutput`` records in the ``outputs`` table.
5. Updates state with ``summaries``.
6. Emits ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import litellm  # type: ignore[import-untyped]
from jinja2 import Environment


from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.telemetry import TelemetryCollector, track_llm_call

from src.db.models import OutputORM
from src.domains.ai_ml.schema import AiMlExtraction
from src.graph.state import PipelineState
from src.models.output import SummaryLevel, SummaryOutput
from src.models.run import StageStatus
from src.core.events import Event, EventType, default_bus

_STAGE = "summarise"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "summarise_v1.j2"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _render_prompt(
    extraction: AiMlExtraction,
    level: SummaryLevel,
    paper_text: str | None = None,
) -> str:
    """Render summarise_v1.j2 with the extraction data and requested level."""
    import json
    import aiofiles  # type: ignore[import-untyped]

    async with aiofiles.open(_PROMPT_PATH, mode="r", encoding="utf-8") as f:
        template_str = await f.read()

    env = Environment(autoescape=False)
    template = env.from_string(template_str)
    return template.render(
        extraction_json=json.dumps(extraction.model_dump(mode="json"), indent=2),
        level=level.value,
        paper_text=paper_text,
    )


async def _call_gemini_summarise_async(
    prompt: str,
    level: SummaryLevel,
    run_id: str,
    collector: TelemetryCollector,
) -> str:
    """Async wrapper: calls Gemini for one summary level, returns the summary text."""
    settings = get_settings()
    model = settings.gemini.default_model

    messages = [{"role": "user", "content": prompt}]

    with track_llm_call(
        collector, stage_name=f"{_STAGE}.{level.value}", model=model
    ) as ctx:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=settings.gemini.temperature,
            max_tokens=2048,
            num_retries=3,
            api_key=settings.gemini.api_key.get_secret_value(),
        )
        ctx.set_response(response)

    content = (response.choices[0].message.content or "").strip()
    return content if content else f"Summary unavailable for level: {level.value}"


async def _store_summaries(paper_id: str, summaries: list[SummaryOutput]) -> None:
    """Persist all SummaryOutput records to the ``outputs`` table."""
    try:
        from src.db.session import get_db_context

        async with get_db_context() as session:
            for summary in summaries:
                row = OutputORM(
                    id=uuid.uuid4(),
                    paper_id=uuid.UUID(paper_id),
                    output_type=f"summary_{summary.level.value}",
                    storage_path=f"inline:summary_{summary.level.value}",
                )
                session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("summarise_store_failed", reason=str(exc))


async def _load_cached_summaries(paper_id: str) -> list[SummaryOutput]:
    """Return cached ``SummaryOutput`` records if they exist in the DB."""
    try:
        from src.db.session import get_db_context
        from src.db.models import OutputORM
        from sqlalchemy import select
        import uuid

        async with get_db_context() as session:
            stmt = (
                select(OutputORM)
                .where(OutputORM.paper_id == uuid.UUID(paper_id))
                .where(OutputORM.output_type.startswith("summary_"))
            )
            res = await session.execute(stmt)
            orms = res.scalars().all()

            summaries: list[SummaryOutput] = []
            for orm in orms:
                level_str = orm.output_type.replace("summary_", "")
                summaries.append(
                    SummaryOutput(
                        paper_id=uuid.UUID(paper_id),
                        level=SummaryLevel(level_str),
                        content="Summary content not available in DB (inline placeholder)"
                        if orm.storage_path.startswith("inline:")
                        else orm.storage_path,
                    )
                )
            return summaries
    except Exception as exc:  # noqa: BLE001
        log.debug("summarise_cache_miss", reason=str(exc))
    return []


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def summarise_node(state: PipelineState) -> dict[str, Any]:
    """Generate four summary variants from the structured extraction.

    All four LLM calls are made in parallel via ``asyncio.gather`` to
    reduce wall-clock time.

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

    cached_stages: set[str] = set(state.get("cached_stages", set()))

    # ── 1. Cache check ───────────────────────────────────────────────────────
    from src.core.config import get_settings

    settings = get_settings()

    if settings.pipeline.cache_enabled and paper_id:
        cached_summaries = await _load_cached_summaries(paper_id)
        if cached_summaries:
            log.info("summarise_node.cache_hit", run_id=run_id)
            stage_statuses[_STAGE] = StageStatus.CACHED
            cached_stages.add(_STAGE)

            default_bus.emit(
                Event(
                    type=EventType.STAGE_COMPLETED,
                    run_id=run_id,
                    stage_name=_STAGE,
                    payload={"cached": True},
                )
            )
            return {
                "summaries": cached_summaries,
                "stage_statuses": stage_statuses,
                "cached_stages": cached_stages,
            }

    if extraction is None:
        msg = f"[{_STAGE}] extraction is None — skipping."
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.SKIPPED
        log.warning("summarise_node.skipped", run_id=run_id, reason="no extraction")
        return {"stage_statuses": stage_statuses, "errors": errors, "summaries": []}

    try:
        # Extract text from PDF if available to improve summary accuracy (RC-1b)
        pdf_bytes: bytes | None = state.get("pdf_bytes")
        paper_text: str | None = None
        if pdf_bytes:
            try:
                import io
                import pypdf

                def _extract():
                    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
                    # Get first 3 pages or ~8000 chars for context
                    text_parts = []
                    for i in range(min(len(reader.pages), 3)):
                        text_parts.append(reader.pages[i].extract_text() or "")
                    return "\n".join(text_parts)[:8000]

                paper_text = await asyncio.to_thread(_extract)
                log.debug("summarise_node.text_extracted", length=len(paper_text or ""))
            except Exception as exc:  # noqa: BLE001
                log.warning("summarise_node.text_extraction_failed", reason=str(exc))

        collector = TelemetryCollector(run_id=run_id, paper_id=paper_id)
        levels = list(SummaryLevel)

        # Render prompts sequentially as it's fast
        prompts = [
            await _render_prompt(extraction, level, paper_text=paper_text)
            for level in levels
        ]

        # ── Parallel LLM calls: all 4 summary levels at once ─────────────
        tasks = [
            _call_gemini_summarise_async(prompt, level, run_id, collector)
            for prompt, level in zip(prompts, levels)
        ]
        contents = await asyncio.gather(*tasks)

        summaries: list[SummaryOutput] = []
        for level, content in zip(levels, contents):
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
            await _store_summaries(paper_id, summaries)

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
