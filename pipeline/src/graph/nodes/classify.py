"""
pipeline.graph.nodes.classify
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``classify_node`` — classifies the paper's domain and sub-domain.

Responsibilities
----------------
1. Check cache — load from DB if this paper was already classified.
2. Fetch PDF bytes from Supabase Storage if not already in state.
3. Render ``classify_v1.j2`` prompt.
4. Send PDF + prompt to Gemini via LiteLLM (vision).
5. Parse response into ``ClassificationResult`` Pydantic model.
6. **Persist classification** to the ``papers`` metadata JSONB column.
7. Update state: ``domain``, ``sub_domain``, ``classification_confidence``.
8. Emit ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any

import litellm  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.telemetry import TelemetryCollector, track_llm_call
from src.core.utils import extract_json
from src.graph.nodes._base import NodeContext, render_prompt
from src.graph.state import PipelineState
from src.db.engine import get_supabase_client
from src.db.session import get_db_context
import asyncio
from sqlalchemy import text

_STAGE = "classify"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "classify_v1.j2"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class ClassificationResult(BaseModel):
    """Parsed LLM classification response."""

    domain: str = Field(..., description="High-level domain.")
    sub_domain: str = Field(..., description="Specific sub-domain.")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(default="")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_pdf_bytes(storage_path: str) -> bytes:
    """Download PDF bytes from Supabase Storage."""
    client = get_supabase_client()

    def _do_download():
        response = client.storage.from_("papers").download(storage_path)
        return bytes(response)

    return await asyncio.to_thread(_do_download)


async def _call_gemini_classify(
    pdf_bytes: bytes,
    prompt: str,
    run_id: str,
    collector: TelemetryCollector,
) -> ClassificationResult:
    """Send the PDF + classify prompt to Gemini and parse the response."""
    settings = get_settings()
    model = settings.gemini.vision_model

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:application/pdf;base64,{pdf_b64}",
                    },
                },
            ],
        }
    ]

    with track_llm_call(collector, stage_name=_STAGE, model=model) as ctx:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=settings.gemini.temperature,
            max_tokens=4096,  # Increased to prevent truncation
            num_retries=3,
            response_format=ClassificationResult,
            api_key=settings.gemini.api_key.get_secret_value(),
        )
        ctx.set_response(response)

    raw = response.choices[0].message.content or "{}"
    cleaned = extract_json(raw)

    try:
        data = json.loads(cleaned)
        return ClassificationResult.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        log.error(
            "classify_node.parse_failed", error=str(exc), raw=raw, cleaned=cleaned
        )
        raise


async def _load_cached_classification(paper_id: str) -> ClassificationResult | None:
    """Try to load an existing classification from the papers.metadata JSONB column.

    Classification is persisted into ``papers.metadata`` under the keys
    ``cls_domain``, ``cls_sub_domain``, and ``cls_confidence`` so it
    survives across pipeline re-runs without a dedicated table.
    """
    try:
        async with get_db_context() as session:
            res = await session.execute(
                text(
                    """
                    SELECT
                        metadata->>'cls_domain'      AS domain,
                        metadata->>'cls_sub_domain'  AS sub_domain,
                        (metadata->>'cls_confidence')::float AS confidence
                    FROM papers
                    WHERE id = CAST(:pid AS UUID)
                      AND metadata->>'cls_domain' IS NOT NULL
                    LIMIT 1
                    """
                ),
                {"pid": str(uuid.UUID(paper_id))},
            )
            row = res.fetchone()

        if row and row.domain:
            return ClassificationResult(
                domain=row.domain,
                sub_domain=row.sub_domain or "",
                confidence=float(row.confidence or 0.0),
            )
    except Exception as exc:  # noqa: BLE001
        log.debug("classify_cache_miss", reason=str(exc))

    return None


async def _persist_classification(paper_id: str, result: ClassificationResult) -> None:
    """Merge classification result into papers.metadata JSONB."""
    try:
        async with get_db_context() as session:
            await session.execute(
                text(
                    """
                    UPDATE papers
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:new_meta AS JSONB)
                    WHERE id = CAST(:pid AS UUID)
                    """
                ),
                {
                    "pid": str(uuid.UUID(paper_id)),
                    "new_meta": json.dumps(
                        {
                            "cls_domain": result.domain,
                            "cls_sub_domain": result.sub_domain,
                            "cls_confidence": str(result.confidence),
                        }
                    ),
                },
            )
            await session.commit()
        log.debug("classify_node.classification_persisted", paper_id=paper_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("classify_node.persist_failed", reason=str(exc))


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def classify_node(state: PipelineState) -> dict[str, Any]:
    """Classify the paper into a domain and sub-domain.

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``pdf_bytes``, ``pdf_storage_path``

    Writes to state
    ---------------
    - ``domain``, ``sub_domain``, ``classification_confidence``
    - ``stage_statuses["classify"]``
    - ``token_usage["classify"]``
    - ``cached_stages`` — if result was from cache
    - ``errors`` — appended on failure
    """
    ctx = NodeContext(state, _STAGE)
    ctx.mark_running()

    pdf_bytes: bytes | None = state.get("pdf_bytes")
    storage_path: str | None = state.get("pdf_storage_path")

    try:
        # ── 1. Cache check ───────────────────────────────────────────────
        if ctx.settings.pipeline.cache_enabled and ctx.paper_id:
            cached = await _load_cached_classification(ctx.paper_id)
            if cached:
                return {
                    "domain": cached.domain,
                    "sub_domain": cached.sub_domain,
                    "classification_confidence": cached.confidence,
                    **ctx.mark_cached({"domain": cached.domain}),
                }

        # ── 2. Ensure we have PDF bytes ──────────────────────────────────
        if pdf_bytes is None:
            if storage_path and not storage_path.startswith("local://"):
                pdf_bytes = await _fetch_pdf_bytes(storage_path)
            else:
                raise ValueError(
                    "classify_node requires pdf_bytes or a valid pdf_storage_path."
                )

        # ── 3. Load prompt and call Gemini ───────────────────────────────
        prompt = render_prompt(_PROMPT_PATH)
        collector = TelemetryCollector(run_id=ctx.run_id, paper_id=ctx.paper_id)
        result = await _call_gemini_classify(pdf_bytes, prompt, ctx.run_id, collector)

        ctx.token_usage[_STAGE] = collector.total_tokens

        # ── 4. Persist classification to DB (enables future cache hits) ──
        if ctx.paper_id:
            await _persist_classification(ctx.paper_id, result)

        # ── 5. Emit event and return ─────────────────────────────────────
        log.info(
            "classify_node.completed",
            run_id=ctx.run_id,
            domain=result.domain,
            sub_domain=result.sub_domain,
            confidence=result.confidence,
        )

        return {
            "pdf_bytes": pdf_bytes,
            "domain": result.domain,
            "sub_domain": result.sub_domain,
            "classification_confidence": result.confidence,
            **ctx.mark_completed(
                {
                    "domain": result.domain,
                    "sub_domain": result.sub_domain,
                    "confidence": result.confidence,
                }
            ),
        }

    except Exception as exc:  # noqa: BLE001
        return ctx.mark_failed(exc)
