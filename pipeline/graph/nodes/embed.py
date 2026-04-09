"""
pipeline.graph.nodes.embed
~~~~~~~~~~~~~~~~~~~~~~~~~~
``embed_node`` — generates and stores vector embeddings for semantic search.

Responsibilities
----------------
1. Works from ``state["extraction"]`` — no PDF needed.
2. Prepares four embedding chunks:
   - title + abstract
   - key contributions
   - proposed method
   - headline results
3. Calls ``litellm.embedding()`` with ``gemini/text-embedding-004`` per chunk.
4. Stores 768-d vectors in the ``embeddings`` table via pgvector.
5. Updates state with confirmation.
6. Emits ``STAGE_COMPLETED`` event.

This stage powers all semantic search functionality in the app.
"""

from __future__ import annotations

import uuid
from typing import Any

from pipeline.core.events import Event, EventType, default_bus
from pipeline.core.logger import get_logger
from pipeline.graph.state import PipelineState
from pipeline.domains.ai_ml.schema import AiMlExtraction
from pipeline.models.run import StageStatus

_STAGE = "embed"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_chunks(
    extraction: AiMlExtraction, paper_title: str | None
) -> list[tuple[str, str]]:
    """Build (chunk_type, text) pairs from the extraction.

    Returns
    -------
    list of (chunk_type, text) tuples, skipping empty chunks.
    """
    chunks: list[tuple[str, str]] = []

    # Chunk 1: title + abstract / problem statement
    title_abstract = " ".join(filter(None, [paper_title, extraction.problem_statement]))
    if title_abstract.strip():
        chunks.append(("title_abstract", title_abstract.strip()))

    # Chunk 2: key contributions
    if extraction.key_contributions:
        contributions_text = "\n".join(f"- {c}" for c in extraction.key_contributions)
        chunks.append(("key_contributions", contributions_text))

    # Chunk 3: proposed method
    if extraction.proposed_method_summary:
        chunks.append(("proposed_method", extraction.proposed_method_summary))

    # Chunk 4: results
    if extraction.main_results:
        chunks.append(("main_results", extraction.main_results))

    return chunks


def _embed_chunks(
    chunks: list[tuple[str, str]],
    model: str,
    api_key: str,
) -> list[tuple[str, list[float]]]:
    """Call litellm.embedding() for each chunk, return (chunk_type, vector) pairs."""
    import litellm  # type: ignore[import-untyped]

    results: list[tuple[str, list[float]]] = []

    for chunk_type, text in chunks:
        response = litellm.embedding(
            model=model,
            input=[text],
            api_key=api_key,
        )
        vector: list[float] = response.data[0]["embedding"]
        results.append((chunk_type, vector))
        log.debug(
            "embed_node.chunk_embedded",
            chunk_type=chunk_type,
            dims=len(vector),
        )

    return results


def _store_embeddings(
    paper_id: str,
    embedded_chunks: list[tuple[str, list[float]]],
) -> None:
    """Persist embedding vectors to the ``embeddings`` table."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from pipeline.core.config import get_settings
        from pipeline.db.models import EmbeddingORM

        settings = get_settings()
        engine = create_engine(
            settings.supabase.db_url.get_secret_value(), pool_pre_ping=True
        )

        with Session(engine) as session:
            for chunk_type, vector in embedded_chunks:
                row = EmbeddingORM(
                    id=uuid.uuid4(),
                    paper_id=uuid.UUID(paper_id),
                    chunk_type=chunk_type,
                    embedding=vector,
                )
                session.add(row)
            session.commit()
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        log.warning("embed_store_failed", reason=str(exc))


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def embed_node(state: PipelineState) -> dict[str, Any]:
    """Generate and store vector embeddings for semantic search.

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``extraction``, ``paper_metadata``

    Writes to state
    ---------------
    - ``stage_statuses["embed"]``
    - ``token_usage["embed"]``  (approximated from chunk count)
    - ``errors`` — appended on failure
    """
    run_id = state["run_id"]
    paper_id: str | None = state.get("paper_id")
    extraction: AiMlExtraction | None = state.get("extraction")
    paper_metadata = state.get("paper_metadata")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))
    token_usage: dict[str, int] = dict(state.get("token_usage", {}))

    log.info("embed_node.started", run_id=run_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    if extraction is None:
        msg = f"[{_STAGE}] extraction is None — skipping."
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.SKIPPED
        log.warning("embed_node.skipped", run_id=run_id, reason="no extraction")
        return {"stage_statuses": stage_statuses, "errors": errors}

    try:
        from pipeline.core.config import get_settings

        settings = get_settings()
        model = settings.gemini.embedding_model
        api_key = settings.gemini.api_key.get_secret_value()

        paper_title: str | None = None
        if paper_metadata:
            paper_title = paper_metadata.title

        # ── 1. Build text chunks ─────────────────────────────────────────
        chunks = _build_chunks(extraction, paper_title)

        if not chunks:
            log.warning("embed_node.no_chunks", run_id=run_id)
            stage_statuses[_STAGE] = StageStatus.COMPLETED
            return {"stage_statuses": stage_statuses, "errors": errors}

        # ── 2. Embed each chunk ──────────────────────────────────────────
        embedded_chunks = _embed_chunks(chunks, model, api_key)

        # Approximate token usage: ~1 token per 4 chars
        approx_tokens = sum(len(t) // 4 for _, t in chunks)
        token_usage[_STAGE] = approx_tokens

        # ── 3. Store to DB ───────────────────────────────────────────────
        if paper_id:
            _store_embeddings(paper_id, embedded_chunks)

        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={
                    "chunk_count": len(embedded_chunks),
                    "dims": len(embedded_chunks[0][1]) if embedded_chunks else 0,
                },
            )
        )

        log.info(
            "embed_node.completed",
            run_id=run_id,
            chunk_count=len(embedded_chunks),
        )

        return {
            "stage_statuses": stage_statuses,
            "token_usage": token_usage,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("embed_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors}
