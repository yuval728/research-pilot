"""
pipeline.graph.nodes.metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``metadata_node`` — bibliographic metadata extraction from the paper PDF.

Designed for PDF uploads that arrive without metadata. For arXiv and DOI
sources the metadata is already populated by PaperService, so this node
skips immediately.

Responsibilities
----------------
1. Skip if ``paper_metadata`` is already in state (arXiv/DOI path).
2. Check cache — load existing metadata from ``papers.metadata`` JSONB.
3. Render ``metadata_v1.j2`` prompt.
4. Send PDF bytes + prompt to LLM via LiteLLM.
5. Parse response into ``PaperMetadataExtraction`` Pydantic model.
6. Persist to ``papers.metadata`` JSONB column.
7. Update state with ``paper_metadata``.
8. Emit ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any

import litellm  # type: ignore[import-untyped]

from src.core.logger import get_logger
from src.core.telemetry import TelemetryCollector, track_llm_call
from src.core.utils import extract_json
from src.graph.nodes._base import NodeContext, render_prompt
from src.graph.state import PipelineState
from src.core.config import get_settings
from src.db.engine import get_supabase_client
from src.db.session import get_db_context
import asyncio
from sqlalchemy import text

from src.models.paper import PaperMetadata, PaperMetadataExtraction

_STAGE = "metadata"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "metadata_v1.j2"

log = get_logger(__name__)


def _extraction_to_metadata(ext: PaperMetadataExtraction) -> PaperMetadata | None:
    """Convert a ``PaperMetadataExtraction`` (optional title) to ``PaperMetadata`` (required title).

    Returns ``None`` when title is missing so the caller can fall back to
    the LLM extraction path.
    """
    if not ext.title:
        return None
    return PaperMetadata(
        title=ext.title,
        authors=ext.authors or [],
        abstract=ext.abstract,
        venue=ext.venue,
        year=ext.year,
        arxiv_id=ext.arxiv_id,
        doi=ext.doi,
        page_count=ext.page_count,
        domain=None,
        sub_domain=None,
    )


async def _load_cached_metadata(paper_id: str) -> PaperMetadata | None:
    """Try to load existing bibliographic metadata from papers.metadata JSONB.

    If the paper already has a title stored, treat it as a cache hit.
    """
    try:
        async with get_db_context() as session:
            res = await session.execute(
                text(
                    """
                    SELECT
                        metadata->>'title'      AS title,
                        metadata->'authors'     AS authors,
                        metadata->>'abstract'   AS abstract,
                        metadata->>'venue'      AS venue,
                        (metadata->>'year')::int AS year,
                        metadata->>'arxiv_id'   AS arxiv_id,
                        metadata->>'doi'        AS doi,
                        (metadata->>'page_count')::int AS page_count
                    FROM papers
                    WHERE id = CAST(:pid AS UUID)
                      AND metadata->>'title' IS NOT NULL
                    LIMIT 1
                    """
                ),
                {"pid": str(uuid.UUID(paper_id))},
            )
            row = res.fetchone()

        if row and row.title:
            raw_authors = json.loads(row.authors) if row.authors else []
            ext = PaperMetadataExtraction(
                title=row.title,
                authors=raw_authors if isinstance(raw_authors, list) else [],
                abstract=row.abstract,
                venue=row.venue,
                year=int(row.year) if row.year else None,
                arxiv_id=row.arxiv_id,
                doi=row.doi,
                page_count=int(row.page_count) if row.page_count else None,
            )
            return _extraction_to_metadata(
                ext
            )  # Always non-None since title is set above
    except Exception as exc:  # noqa: BLE001
        log.debug("metadata_cache_miss", reason=str(exc))

    return None


async def _call_llm_metadata(
    pdf_bytes: bytes,
    prompt: str,
    run_id: str,
    collector: TelemetryCollector,
) -> PaperMetadataExtraction:
    """Send the PDF + metadata prompt to LLM and parse the response."""
    settings = get_settings()
    model = settings.llm.model

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "file",
                    "file": {
                        "file_data": f"data:application/pdf;base64,{pdf_b64}",
                    },
                },
            ],
        }
    ]

    with track_llm_call(collector, stage_name=_STAGE, model=model) as ctx:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=settings.llm.temperature,
            max_tokens=4096,
            num_retries=3,
            response_format=PaperMetadataExtraction,
            api_key=settings.llm.api_key.get_secret_value(),
        )
        ctx.set_response(response)

    raw = response.choices[0].message.content or "{}"
    cleaned = extract_json(raw)

    try:
        data = json.loads(cleaned)
        return PaperMetadataExtraction.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        log.error(
            "metadata_node.parse_failed", error=str(exc), raw=raw, cleaned=cleaned
        )
        raise


async def _persist_metadata(paper_id: str, result: PaperMetadataExtraction) -> None:
    """Merge bibliographic metadata into papers.metadata JSONB."""
    meta_dict: dict[str, Any] = {}
    if result.title:
        meta_dict["title"] = result.title
    if result.authors:
        meta_dict["authors"] = result.authors
    if result.abstract:
        meta_dict["abstract"] = result.abstract
    if result.venue:
        meta_dict["venue"] = result.venue
    if result.year:
        meta_dict["year"] = result.year
    if result.arxiv_id:
        meta_dict["arxiv_id"] = result.arxiv_id
    if result.doi:
        meta_dict["doi"] = result.doi
    if result.page_count:
        meta_dict["page_count"] = result.page_count

    if not meta_dict:
        log.warning("metadata_node.nothing_to_persist", paper_id=paper_id)
        return

    try:
        async with get_db_context() as session:
            await session.execute(
                text(
                    """
                    UPDATE papers
                    SET metadata = CASE WHEN jsonb_typeof(metadata) = 'object' THEN metadata ELSE '{}'::jsonb END || CAST(:new_meta AS JSONB)
                    WHERE id = CAST(:pid AS UUID)
                    """
                ),
                {
                    "pid": str(uuid.UUID(paper_id)),
                    "new_meta": json.dumps(meta_dict),
                },
            )
            await session.commit()
        log.debug("metadata_node.persisted", paper_id=paper_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("metadata_node.persist_failed", reason=str(exc))


async def _fetch_pdf_bytes(storage_path: str) -> bytes:
    """Download PDF bytes from Supabase Storage."""
    client = get_supabase_client()

    def _do_download():
        response = client.storage.from_("papers").download(storage_path)
        return bytes(response)

    return await asyncio.to_thread(_do_download)


async def metadata_node(state: PipelineState) -> dict[str, Any]:
    """Extract bibliographic metadata from the paper PDF.

    Skips if paper_metadata is already populated (arXiv/DOI sources).

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``pdf_bytes``, ``paper_metadata``

    Writes to state
    ---------------
    - ``paper_metadata`` (as PaperMetadata)
    - ``stage_statuses["metadata"]``
    - ``token_usage["metadata"]``
    - ``cached_stages`` — if result was from cache
    - ``errors`` — appended on failure
    """
    ctx = NodeContext(state, _STAGE)
    ctx.mark_running()

    existing_metadata = state.get("paper_metadata")
    pdf_bytes: bytes | None = state.get("pdf_bytes")
    storage_path: str | None = state.get("pdf_storage_path")

    try:
        # Only run for PDF uploads that lack bibliographic metadata
        if existing_metadata is not None:
            log.info(
                "metadata_node.skipped_already_populated",
                run_id=ctx.run_id,
                paper_id=ctx.paper_id,
            )
            return ctx.mark_skipped("Paper metadata already populated.")

        # Cache check
        if ctx.settings.pipeline.cache_enabled and ctx.paper_id:
            cached = await _load_cached_metadata(ctx.paper_id)
            if cached:
                return {
                    "paper_metadata": cached,
                    **ctx.mark_cached({"title": cached.title}),
                }

        # Ensure we have PDF bytes
        if pdf_bytes is None:
            if storage_path and not storage_path.startswith("local://"):
                pdf_bytes = await _fetch_pdf_bytes(storage_path)
            else:
                raise ValueError(
                    "metadata_node requires pdf_bytes or a valid pdf_storage_path."
                )

        prompt = render_prompt(_PROMPT_PATH)
        collector = TelemetryCollector(run_id=ctx.run_id, paper_id=ctx.paper_id)
        result = await _call_llm_metadata(pdf_bytes, prompt, ctx.run_id, collector)

        ctx.token_usage[_STAGE] = collector.total_tokens

        # Persist to DB
        if ctx.paper_id:
            await _persist_metadata(ctx.paper_id, result)

        log.info(
            "metadata_node.completed",
            run_id=ctx.run_id,
            title=result.title,
            tokens=ctx.token_usage[_STAGE],
        )

        metadata = _extraction_to_metadata(result)
        if metadata is None:
            return ctx.mark_failed(
                ValueError("LLM did not return a title for this paper.")
            )

        return {
            "paper_metadata": metadata,
            **ctx.mark_completed(
                {"title": metadata.title, "tokens": ctx.token_usage[_STAGE]}
            ),
        }

    except Exception as exc:  # noqa: BLE001
        return ctx.mark_failed(exc)
