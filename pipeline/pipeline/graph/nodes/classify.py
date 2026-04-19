"""
pipeline.graph.nodes.classify
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``classify_node`` — classifies the paper's domain and sub-domain.

Responsibilities
----------------
1. Check cache — if this paper was already classified, load from DB.
2. Fetch PDF bytes from Supabase Storage if not already in state.
3. Render ``classify_v1.j2`` prompt.
4. Send PDF + prompt to Gemini via LiteLLM (vision).
5. Parse response into ``ClassificationResult`` Pydantic model.
6. Update state: ``domain``, ``sub_domain``, ``classification_confidence``.
7. Emit ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import litellm  # type: ignore[import-untyped]
from pydantic import BaseModel, Field
from supabase import create_client  # type: ignore[import-untyped]

from pipeline.core.config import get_settings
from pipeline.core.events import Event, EventType, default_bus
from pipeline.core.logger import get_logger
from pipeline.core.telemetry import TelemetryCollector, track_llm_call
from pipeline.core.utils import extract_json
from pipeline.graph.state import PipelineState
from pipeline.models.run import StageStatus

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


def _load_prompt() -> str:
    """Load the Jinja2 template as a plain string (no variables needed)."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _fetch_pdf_bytes(storage_path: str) -> bytes:
    """Download PDF bytes from Supabase Storage."""
    settings = get_settings()
    client = create_client(
        settings.supabase.url,
        settings.supabase.service_role_key.get_secret_value(),
    )
    response = client.storage.from_("papers").download(storage_path)
    return bytes(response)


def _call_gemini_classify(
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
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=settings.gemini.temperature,
            max_tokens=1024,  # Increased to prevent truncation
            num_retries=3,
            response_format=ClassificationResult,  # Native JSON schema mode
            api_key=settings.gemini.api_key.get_secret_value(),
        )
        ctx.set_response(response)

    raw = response.choices[0].message.content or "{}"

    # Even in JSON mode, LiteLLM/Gemini sometimes wraps in markdown or prose.
    # We use a robust extractor before parsing.
    cleaned = extract_json(raw)

    try:
        data = json.loads(cleaned)
        return ClassificationResult.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        log.error(
            "classify_node.parse_failed", error=str(exc), raw=raw, cleaned=cleaned
        )
        # Fallback: if native mode failed, try to find ANY JSON in the raw response
        try:
            fallback_cleaned = extract_json(raw)
            data = json.loads(fallback_cleaned)
            return ClassificationResult.model_validate(data)
        except Exception:
            raise


def _load_cached_classification(paper_id: str) -> ClassificationResult | None:
    """Try to load an existing classification from the DB."""
    try:
        from sqlalchemy import create_engine, text

        from pipeline.core.config import get_settings

        settings = get_settings()
        db_url = settings.supabase.db_url.get_secret_value()
        engine = create_engine(db_url, pool_pre_ping=True)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT data->>'domain' AS domain,
                           data->>'sub_domain' AS sub_domain,
                           (data->>'confidence_score')::float AS confidence
                    FROM extractions
                    WHERE paper_id = :pid
                    LIMIT 1
                    """
                ),
                {"pid": paper_id},
            ).fetchone()
        engine.dispose()

        if row and row.domain:
            return ClassificationResult(
                domain=row.domain,
                sub_domain=row.sub_domain or "",
                confidence=float(row.confidence or 0.0),
            )
    except Exception as exc:  # noqa: BLE001
        log.debug("classify_cache_miss", reason=str(exc))

    return None


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def classify_node(state: PipelineState) -> dict[str, Any]:
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
    run_id = state["run_id"]
    paper_id: str | None = state.get("paper_id")
    pdf_bytes: bytes | None = state.get("pdf_bytes")
    storage_path: str | None = state.get("pdf_storage_path")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))
    token_usage: dict[str, int] = dict(state.get("token_usage", {}))
    cached_stages: set[str] = set(state.get("cached_stages", set()))

    log.info("classify_node.started", run_id=run_id, paper_id=paper_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    try:
        # ── 1. Cache check ───────────────────────────────────────────────
        if paper_id:
            cached = _load_cached_classification(paper_id)
            if cached:
                log.info("classify_node.cache_hit", run_id=run_id)
                stage_statuses[_STAGE] = StageStatus.CACHED
                cached_stages.add(_STAGE)
                default_bus.emit(
                    Event(
                        type=EventType.STAGE_COMPLETED,
                        run_id=run_id,
                        stage_name=_STAGE,
                        payload={"cached": True, "domain": cached.domain},
                    )
                )
                return {
                    "domain": cached.domain,
                    "sub_domain": cached.sub_domain,
                    "classification_confidence": cached.confidence,
                    "stage_statuses": stage_statuses,
                    "cached_stages": cached_stages,
                    "errors": errors,
                }

        # ── 2. Ensure we have PDF bytes ──────────────────────────────────
        if pdf_bytes is None:
            if storage_path and not storage_path.startswith("local://"):
                pdf_bytes = _fetch_pdf_bytes(storage_path)
            else:
                raise ValueError(
                    "classify_node requires pdf_bytes or a valid pdf_storage_path."
                )

        # ── 3. Load prompt and call Gemini ───────────────────────────────
        prompt = _load_prompt()
        collector = TelemetryCollector(run_id=run_id)
        result = _call_gemini_classify(pdf_bytes, prompt, run_id, collector)

        token_usage[_STAGE] = collector.total_tokens

        # ── 4. Emit event and return ─────────────────────────────────────
        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={
                    "domain": result.domain,
                    "sub_domain": result.sub_domain,
                    "confidence": result.confidence,
                },
            )
        )

        log.info(
            "classify_node.completed",
            run_id=run_id,
            domain=result.domain,
            sub_domain=result.sub_domain,
            confidence=result.confidence,
        )

        return {
            "pdf_bytes": pdf_bytes,  # cache in state for downstream nodes
            "domain": result.domain,
            "sub_domain": result.sub_domain,
            "classification_confidence": result.confidence,
            "stage_statuses": stage_statuses,
            "token_usage": token_usage,
            "cached_stages": cached_stages,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("classify_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors}
