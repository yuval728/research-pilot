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
4. Stores 1536-d vectors in the ``embeddings`` table via pgvector.
5. Updates state with confirmation.
6. Emits ``STAGE_COMPLETED`` event.

This stage powers all semantic search functionality in the app.
"""

from __future__ import annotations

import uuid
import asyncio
from typing import Any

import litellm
from sqlalchemy import select
from src.db.session import get_db_context
from src.db.models import EmbeddingORM

from src.core.logger import get_logger
from src.graph.nodes._base import NodeContext
from src.graph.state import PipelineState
from src.domains.ai_ml.schema import AiMlExtraction

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
    list of (chunk_type, text) tuples, skipping empty or redundant chunks.
    """
    raw_chunks: list[tuple[str, str]] = []

    # Chunk 1: title + abstract / problem statement
    title_abstract = " ".join(filter(None, [paper_title, extraction.problem_statement]))
    if title_abstract.strip():
        raw_chunks.append(("title_abstract", title_abstract.strip()))

    # Chunk 2: key contributions
    if extraction.key_contributions:
        contributions_text = "\n".join(f"- {c}" for c in extraction.key_contributions)
        raw_chunks.append(("key_contributions", contributions_text))

    # Chunk 3: proposed method
    if extraction.proposed_method_summary:
        raw_chunks.append(("proposed_method", extraction.proposed_method_summary))

    # Chunk 4: results
    if extraction.main_results:
        raw_chunks.append(("main_results", extraction.main_results))

    # Deduplicate based on text to save tokens/costs
    seen_texts: set[str] = set()
    final_chunks: list[tuple[str, str]] = []
    for ctype, text in raw_chunks:
        if text not in seen_texts:
            seen_texts.add(text)
            final_chunks.append((ctype, text))

    return final_chunks


async def _embed_chunks(
    chunks: list[tuple[str, str]],
    model: str,
    api_key: str,
) -> list[tuple[str, list[float]]]:
    """Call litellm.aembedding() for each chunk concurrently, return (chunk_type, vector) pairs."""

    async def _embed_single(chunk_type: str, text: str) -> tuple[str, list[float]]:
        response = await litellm.aembedding(
            model=model,
            input=[text],
            api_key=api_key,
            dimensions=1536,
        )
        vector: list[float] = response.data[0]["embedding"]
        log.debug(
            "embed_node.chunk_embedded",
            chunk_type=chunk_type,
            dims=len(vector),
        )
        return chunk_type, vector

    tasks = [_embed_single(chunk_type, text) for chunk_type, text in chunks]
    return await asyncio.gather(*tasks)


async def _store_embeddings(
    paper_id: str,
    embedded_chunks: list[tuple[str, list[float]]],
) -> None:
    """Persist embedding vectors to the ``embeddings`` table."""
    try:
        async with get_db_context() as session:
            for chunk_type, vector in embedded_chunks:
                row = EmbeddingORM(
                    id=uuid.uuid4(),
                    paper_id=uuid.UUID(paper_id),
                    chunk_type=chunk_type,
                    embedding=vector,
                )
                session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("embed_store_failed", reason=str(exc))


async def _load_cached_embeddings(paper_id: str) -> bool:
    """Return True if embeddings already exist for this paper."""
    try:
        async with get_db_context() as session:
            stmt = (
                select(EmbeddingORM.id)
                .where(EmbeddingORM.paper_id == uuid.UUID(paper_id))
                .limit(1)
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none() is not None
    except Exception as exc:  # noqa: BLE001
        log.debug("embed_cache_miss", reason=str(exc))
        return False


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def embed_node(state: PipelineState) -> dict[str, Any]:
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
    ctx = NodeContext(state, _STAGE)
    ctx.mark_running()

    raw_extraction = state.get("extraction")
    extraction = (
        AiMlExtraction.model_validate(raw_extraction) if raw_extraction else None
    )
    paper_metadata = state.get("paper_metadata")

    # ── 1. Cache check ───────────────────────────────────────────────────────
    if ctx.settings.pipeline.cache_enabled and ctx.paper_id:
        is_cached = await _load_cached_embeddings(ctx.paper_id)
        if is_cached:
            return {
                **ctx.mark_cached(),
            }

    if extraction is None:
        return {
            **ctx.mark_skipped("extraction is None — skipping."),
        }

    try:
        model = ctx.settings.gemini.embedding_model
        api_key = ctx.settings.gemini.api_key.get_secret_value()

        paper_title: str | None = None
        if paper_metadata:
            paper_title = paper_metadata.title

        # ── 1. Build text chunks ─────────────────────────────────────────
        chunks = _build_chunks(extraction, paper_title)

        if not chunks:
            return ctx.mark_completed()

        # ── 2. Embed each chunk ──────────────────────────────────────────
        embedded_chunks = await _embed_chunks(chunks, model, api_key)

        # Approximate token usage: ~1 token per 4 chars
        approx_tokens = sum(len(t) // 4 for _, t in chunks)
        ctx.token_usage[_STAGE] = approx_tokens

        # ── 3. Store to DB ───────────────────────────────────────────────
        if ctx.paper_id:
            await _store_embeddings(ctx.paper_id, embedded_chunks)

        log.info(
            "embed_node.completed",
            run_id=ctx.run_id,
            chunk_count=len(embedded_chunks),
        )

        return ctx.mark_completed(
            {
                "chunk_count": len(embedded_chunks),
                "dims": len(embedded_chunks[0][1]) if embedded_chunks else 0,
            }
        )

    except Exception as exc:  # noqa: BLE001
        return ctx.mark_failed(exc)
