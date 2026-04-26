"""
pipeline.graph.nodes.extract
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``extract_node`` — structured information extraction from the paper PDF.

Responsibilities
----------------
1. Check cache — if extraction exists in DB for this paper + schema version,
   load and mark cached.
2. Render ``extract_v1.j2`` with domain & sub_domain context.
3. Send PDF bytes + prompt to Gemini via LiteLLM + Instructor.
4. Instructor validates the response against ``AiMlExtraction`` schema;
   auto-retries with error feedback on validation failure.
5. Store validated extraction in ``extractions`` table as JSONB.
6. Track tokens via ``TelemetryCollector``.
7. Update state with ``extraction``.
8. Emit ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

import instructor  # type: ignore[import-untyped]
import litellm  # type: ignore[import-untyped]
from sqlalchemy import text

from jinja2 import Environment

from pipeline.core.config import get_settings
from pipeline.core.events import Event, EventType, default_bus
from pipeline.core.logger import get_logger
from pipeline.core.telemetry import TelemetryCollector, track_llm_call
from pipeline.graph.state import PipelineState
from pipeline.domains.ai_ml.schema import AiMlExtraction
from pipeline.db.models import ExtractionORM
from pipeline.models.run import StageStatus

_STAGE = "extract"
_SCHEMA_VERSION = "1.0"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "extract_v1.j2"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _render_prompt(domain: str | None, sub_domain: str | None) -> str:
    """Render the extract_v1.j2 template with domain context."""
    import aiofiles  # type: ignore[import-untyped]

    async with aiofiles.open(_PROMPT_PATH, mode="r", encoding="utf-8") as f:
        template_str = await f.read()

    env = Environment(autoescape=False)
    template = env.from_string(template_str)
    return template.render(
        domain=domain or "AI/ML",
        sub_domain=sub_domain or "General",
    )


async def _load_cached_extraction(paper_id: str) -> AiMlExtraction | None:
    """Return a cached ``AiMlExtraction`` if one exists in the DB."""
    try:
        from pipeline.db.session import get_db_context

        async with get_db_context() as session:
            res = await session.execute(
                text(
                    """
                    SELECT data FROM extractions
                    WHERE paper_id = :pid AND schema_version = :sv
                    ORDER BY extracted_at DESC
                    LIMIT 1
                    """
                ),
                {"pid": paper_id, "sv": _SCHEMA_VERSION},
            )
            row = res.fetchone()
        if row:
            return AiMlExtraction.model_validate(row.data)
    except Exception as exc:  # noqa: BLE001
        log.debug("extract_cache_miss", reason=str(exc))

    return None


async def _call_gemini_extract(
    pdf_bytes: bytes,
    prompt: str,
    run_id: str,
    collector: TelemetryCollector,
) -> AiMlExtraction:
    """Call Gemini via LiteLLM + Instructor, returning a validated extraction."""
    settings = get_settings()
    model = settings.gemini.vision_model

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:application/pdf;base64,{pdf_b64}",
                    },
                },
            ],
        }
    ]

    # Patch LiteLLM client with Instructor for structured output + auto-retry
    client = instructor.from_litellm(litellm.acompletion)

    with track_llm_call(collector, stage_name=_STAGE, model=model) as ctx:
        extraction, raw_response = await client.chat.completions.create_with_completion(
            model=model,
            response_model=AiMlExtraction,
            messages=messages,
            temperature=settings.gemini.temperature,
            max_tokens=settings.gemini.max_output_tokens,
            max_retries=settings.gemini.max_retries,
        )
        ctx.set_response(raw_response)

    return extraction


async def _store_extraction(
    paper_id: str,
    extraction: AiMlExtraction,
    domain: str | None,
) -> None:
    """Persist the extraction JSONB to the ``extractions`` table."""
    try:
        from pipeline.db.session import get_db_context

        async with get_db_context() as session:
            row = ExtractionORM(
                id=uuid.uuid4(),
                paper_id=uuid.UUID(paper_id),
                domain=domain or "Unknown",
                schema_version=_SCHEMA_VERSION,
                data=extraction.model_dump(mode="json"),
            )
            session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("extract_store_failed", reason=str(exc))


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def extract_node(state: PipelineState) -> dict[str, Any]:
    """Extract structured information from the paper PDF.

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``pdf_bytes``, ``domain``, ``sub_domain``

    Writes to state
    ---------------
    - ``extraction``
    - ``stage_statuses["extract"]``
    - ``token_usage["extract"]``
    - ``cached_stages`` — if result was from cache
    - ``errors`` — appended on failure
    """
    run_id = state["run_id"]
    paper_id: str | None = state.get("paper_id")
    pdf_bytes: bytes | None = state.get("pdf_bytes")
    domain: str | None = state.get("domain")
    sub_domain: str | None = state.get("sub_domain")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))
    token_usage: dict[str, int] = dict(state.get("token_usage", {}))
    cached_stages: set[str] = set(state.get("cached_stages", set()))

    log.info("extract_node.started", run_id=run_id, paper_id=paper_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    try:
        # ── 1. Cache check ───────────────────────────────────────────────
        if paper_id:
            cached = await _load_cached_extraction(paper_id)
            if cached:
                log.info("extract_node.cache_hit", run_id=run_id)
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
                    "extraction": cached,
                    "stage_statuses": stage_statuses,
                    "cached_stages": cached_stages,
                    "errors": errors,
                }

        # ── 2. Require PDF bytes ─────────────────────────────────────────
        if pdf_bytes is None:
            raise ValueError("extract_node requires pdf_bytes in state.")

        # ── 3. Render prompt and call Gemini + Instructor ────────────────
        prompt = await _render_prompt(domain, sub_domain)
        collector = TelemetryCollector(run_id=run_id, paper_id=paper_id)
        extraction = await _call_gemini_extract(pdf_bytes, prompt, run_id, collector)
        token_usage[_STAGE] = collector.total_tokens

        # ── 4. Persist to DB ─────────────────────────────────────────────
        if paper_id:
            await _store_extraction(paper_id, extraction, domain)

        # ── 5. Emit event ────────────────────────────────────────────────
        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"task": extraction.task, "tokens": token_usage[_STAGE]},
            )
        )

        log.info(
            "extract_node.completed",
            run_id=run_id,
            task=extraction.task,
            tokens=token_usage[_STAGE],
        )

        return {
            "extraction": extraction,
            "stage_statuses": stage_statuses,
            "token_usage": token_usage,
            "cached_stages": cached_stages,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("extract_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors}
