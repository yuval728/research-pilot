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

import litellm
import io
import json
import pypdf
from sqlalchemy import select
from src.db.session import get_db_context


from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.telemetry import TelemetryCollector, track_llm_call

from src.db.models import OutputORM
from src.domains.ai_ml.schema import AiMlExtraction
from src.graph.nodes._base import NodeContext, render_prompt
from src.graph.state import PipelineState
from src.models.output import SummaryLevel, SummaryOutput
from src.services.converters import OutputDeserializer

_STAGE = "summarise"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "summarise_v1.j2"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _call_llm_summarise_async(
    prompt: str,
    level: SummaryLevel,
    run_id: str,
    collector: TelemetryCollector,
) -> str:
    """Async wrapper: calls LLM for one summary level, returns the summary text."""
    settings = get_settings()
    model = settings.llm.model

    messages = [{"role": "user", "content": prompt}]

    with track_llm_call(
        collector, stage_name=f"{_STAGE}.{level.value}", model=model
    ) as ctx:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=settings.llm.temperature,
            max_tokens=2048,
            num_retries=3,
            api_key=settings.llm.api_key.get_secret_value(),
        )
        ctx.set_response(response)

    content = (response.choices[0].message.content or "").strip()
    return content if content else f"Summary unavailable for level: {level.value}"


async def _store_summaries(paper_id: str, summaries: list[SummaryOutput]) -> None:
    """Persist all SummaryOutput records to the ``outputs`` table."""
    try:
        async with get_db_context() as session:
            for summary in summaries:
                row = OutputORM(
                    id=uuid.uuid4(),
                    paper_id=uuid.UUID(paper_id),
                    output_type=f"summary_{summary.level.value}",
                    storage_path=f"inline:{summary.content}",
                )
                session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("summarise_store_failed", reason=str(exc))


async def _load_cached_summaries(paper_id: str) -> list[SummaryOutput]:
    """Return cached ``SummaryOutput`` records if they exist in the DB."""
    try:
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
                summaries.append(OutputDeserializer.parse_summary(orm))
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
    ctx = NodeContext(state, _STAGE)
    ctx.mark_running()

    raw_extraction = state.get("extraction")
    extraction = (
        AiMlExtraction.model_validate(raw_extraction) if raw_extraction else None
    )

    # ── 1. Cache check ───────────────────────────────────────────────────────
    if ctx.settings.pipeline.cache_enabled and ctx.paper_id:
        cached_summaries = await _load_cached_summaries(ctx.paper_id)
        if cached_summaries:
            return {
                "summaries": cached_summaries,
                **ctx.mark_cached(),
            }

    if extraction is None:
        return {
            "summaries": [],
            **ctx.mark_skipped("extraction is None — skipping."),
        }

    try:
        # Extract text from PDF if available to improve summary accuracy (RC-1b)
        pdf_bytes: bytes | None = state.get("pdf_bytes")
        paper_text: str | None = None
        if pdf_bytes:
            try:

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

        collector = TelemetryCollector(run_id=ctx.run_id, paper_id=ctx.paper_id)
        levels = list(SummaryLevel)

        extraction_json = json.dumps(extraction.model_dump(mode="json"), indent=2)

        # Render prompts sequentially as it's fast
        prompts = [
            render_prompt(
                _PROMPT_PATH,
                extraction_json=extraction_json,
                level=level.value,
                paper_text=paper_text,
            )
            for level in levels
        ]

        # ── Parallel LLM calls: all 4 summary levels at once ─────────────
        tasks = [
            _call_llm_summarise_async(prompt, level, ctx.run_id, collector)
            for prompt, level in zip(prompts, levels)
        ]
        contents = await asyncio.gather(*tasks)

        summaries: list[SummaryOutput] = []
        for level, content in zip(levels, contents):
            if not content:
                log.warning(
                    "summarise_node.empty_response",
                    run_id=ctx.run_id,
                    level=level.value,
                )
                content = f"Summary unavailable for level: {level.value}"

            summaries.append(
                SummaryOutput(
                    paper_id=uuid.UUID(ctx.paper_id) if ctx.paper_id else uuid.uuid4(),
                    level=level,
                    content=content,
                )
            )
            log.info(
                "summarise_node.level_done",
                run_id=ctx.run_id,
                level=level.value,
                length=len(content),
            )

        ctx.token_usage[_STAGE] = collector.total_tokens

        if ctx.paper_id:
            await _store_summaries(ctx.paper_id, summaries)

        log.info(
            "summarise_node.completed",
            run_id=ctx.run_id,
            count=len(summaries),
            tokens=ctx.token_usage[_STAGE],
        )

        return {
            "summaries": summaries,
            **ctx.mark_completed(
                {
                    "summary_count": len(summaries),
                    "tokens": ctx.token_usage[_STAGE],
                }
            ),
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "summaries": [],
            **ctx.mark_failed(exc),
        }
