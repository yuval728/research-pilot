"""
pipeline.graph.nodes.ingest
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ingest_node`` — first stage of the pipeline.

Three execution paths
---------------------
1. **Full skip** — ``paper_id`` AND ``pdf_storage_path`` are already set
   (e.g. ``PaperService.create_from_upload()`` uploaded the PDF already).
   Nothing to do; return immediately.

2. **Fetch-only** — ``paper_id`` is set but ``pdf_storage_path`` is None
   (e.g. ``PaperService.create_from_arxiv()`` created the DB record but
   deferred the PDF download).  Download + upload the PDF under the
   *existing* ``paper_id`` so all storage paths and cache keys are stable.

3. **Full ingestion** — neither is set (standalone / raw-bytes path).
   Compute hash, check for duplicates, generate new UUID, upload PDF, write DB.

This three-path design is the fix for both the cross-contamination bug
(RC-3b) and the broken cache (RC-2a) — the ``paper_id`` is now always
stable across the whole pipeline run.
"""

from __future__ import annotations

import hashlib
import uuid
import arxiv  # type: ignore[import-untyped]
import asyncio
import httpx
import json
from sqlalchemy import text
from typing import Any

from src.db.session import get_db_context
from src.db.engine import get_supabase_client
from src.db.models import PaperORM

from src.core.exceptions import PDFFetchError, DuplicatePaperError, StageError
from src.core.logger import get_logger
from src.graph.nodes._base import NodeContext
from src.graph.state import PipelineState
from src.models.paper import PaperMetadata, PaperSource

_STAGE = "ingest"
_PAPERS_BUCKET = "papers"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _fetch_arxiv(arxiv_id: str) -> bytes:
    def _search():
        client = arxiv.Client()
        search = arxiv.Search(id_list=[arxiv_id])
        return list(client.results(search))

    results = await asyncio.to_thread(_search)

    if not results:
        raise PDFFetchError(
            f"arXiv paper '{arxiv_id}' not found.",
            source_url=f"https://arxiv.org/abs/{arxiv_id}",
        )

    pdf_url = results[0].pdf_url
    return await _fetch_url(pdf_url)


async def _fetch_url(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        raise PDFFetchError(
            f"HTTP {exc.response.status_code} fetching PDF.",
            source_url=url,
            status_code=exc.response.status_code,
        ) from exc
    except httpx.RequestError as exc:
        raise PDFFetchError(
            f"Network error fetching PDF: {exc}",
            source_url=url,
        ) from exc


async def _fetch_doi(doi: str) -> bytes:
    """Resolve a DOI to its PDF via the CrossRef redirect."""
    return await _fetch_url(f"https://doi.org/{doi}")


async def _check_duplicate(content_hash: str) -> None:
    """Raise ``DuplicatePaperError`` if this content hash is already in the DB."""
    try:
        async with get_db_context() as session:
            res = await session.execute(
                text(
                    "SELECT id FROM papers WHERE metadata->>'content_hash' = :h LIMIT 1"
                ),
                {"h": content_hash},
            )
            row = res.fetchone()

        if row is not None:
            raise DuplicatePaperError(
                f"Paper with content hash '{content_hash[:12]}…' already exists.",
                identifier=content_hash,
                identifier_type="content_hash",
            )
    except DuplicatePaperError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("duplicate_check_skipped", reason=str(exc))


async def _upload_pdf(pdf_bytes: bytes, storage_path: str) -> None:
    client = get_supabase_client()

    def _do_upload():
        client.storage.from_(_PAPERS_BUCKET).upload(
            path=storage_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf"},
        )

    await asyncio.to_thread(_do_upload)


async def _create_paper_row(
    paper_id: str,
    source: str,
    storage_path: str,
    metadata: PaperMetadata | None,
    content_hash: str,
) -> None:
    meta_dict: dict[str, Any] = {"content_hash": content_hash}
    if metadata:
        meta_dict.update(metadata.model_dump(exclude_none=True))

    async with get_db_context() as session:
        row = PaperORM(
            id=uuid.UUID(paper_id),
            source=source,
            pdf_storage_path=storage_path,
            metadata_=meta_dict,
        )
        session.add(row)
        await session.commit()


async def _update_paper_storage_path(
    paper_id: str, storage_path: str, content_hash: str
) -> None:
    """Update an existing paper record with its PDF storage path and content hash."""
    try:
        async with get_db_context() as session:
            # Passing the dict as a single JSONB parameter is more robust than jsonb_build_object
            await session.execute(
                text(
                    """
                    UPDATE papers
                    SET pdf_storage_path = :path,
                        metadata = CASE WHEN jsonb_typeof(metadata) = 'object' THEN metadata ELSE '{}'::jsonb END || CAST(:new_meta AS JSONB)
                    WHERE id = CAST(:pid AS UUID)
                    """
                ),
                {
                    "path": storage_path,
                    "new_meta": json.dumps({"content_hash": content_hash}),
                    "pid": str(uuid.UUID(paper_id)),
                },
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("ingest_node.db_update_skipped", reason=str(exc))


async def _fetch_pdf_bytes(
    metadata: PaperMetadata | None, run_id: str
) -> tuple[bytes, str]:
    """Fetch PDF bytes and return (pdf_bytes, source_value)."""
    if metadata and metadata.arxiv_id:
        return await _fetch_arxiv(metadata.arxiv_id), PaperSource.ARXIV_URL.value
    elif metadata and metadata.doi:
        return await _fetch_doi(metadata.doi), PaperSource.DOI.value
    else:
        raise StageError(
            "No PDF bytes provided and no arXiv ID or DOI found in metadata.",
            stage_name=_STAGE,
            run_id=run_id,
        )


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def ingest_node(state: PipelineState) -> dict[str, Any]:
    """Ingest a research paper into the pipeline.

    See module docstring for the three execution paths.
    """
    ctx = NodeContext(state, _STAGE)
    ctx.mark_running()

    existing_paper_id = ctx.paper_id
    existing_storage_path: str | None = state.get("pdf_storage_path")
    metadata: PaperMetadata | None = state.get("paper_metadata")
    pdf_bytes: bytes | None = state.get("pdf_bytes")

    # ── PATH 1: Fully pre-ingested — both paper_id and storage_path are set ──
    if existing_paper_id and existing_storage_path:
        log.info(
            "ingest_node.skipped_already_ingested",
            run_id=ctx.run_id,
            paper_id=existing_paper_id,
        )
        return ctx.mark_completed(
            {"paper_id": existing_paper_id, "storage_path": existing_storage_path}
        )

    try:
        # ── PATH 2: paper_id exists but PDF not yet fetched/uploaded ─────────
        # PaperService.create_from_arxiv() creates the DB record but defers the
        # PDF download.  We fetch it here under the EXISTING paper_id.
        if existing_paper_id and not existing_storage_path:
            paper_id = existing_paper_id
            source_hint = (
                "arxiv"
                if metadata and metadata.arxiv_id
                else "doi"
                if metadata and metadata.doi
                else "unknown"
            )
            log.info(
                "ingest_node.fetching_pdf_for_existing_paper",
                run_id=ctx.run_id,
                paper_id=paper_id,
                source_hint=source_hint,
                has_metadata=metadata is not None,
            )

            if pdf_bytes is None:
                try:
                    pdf_bytes, _ = await _fetch_pdf_bytes(metadata, ctx.run_id)
                except StageError as exc:
                    raise StageError(
                        "Failed to fetch PDF for existing paper: missing or invalid source metadata.",
                        stage_name=_STAGE,
                        run_id=ctx.run_id,
                        cause=exc,
                    ) from exc
                except Exception as exc:  # noqa: BLE001
                    raise StageError(
                        "Failed to fetch PDF for existing paper.",
                        stage_name=_STAGE,
                        run_id=ctx.run_id,
                        cause=exc,
                    ) from exc

            content_hash = _compute_sha256(pdf_bytes)
            log.info(
                "ingest_node.pdf_fetched_for_existing_paper",
                run_id=ctx.run_id,
                paper_id=paper_id,
                bytes_len=len(pdf_bytes),
            )
            storage_path = f"{paper_id}/paper.pdf"

            try:
                await _upload_pdf(pdf_bytes, storage_path)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "ingest_node.upload_skipped", reason=str(exc), run_id=ctx.run_id
                )
                storage_path = f"local://{paper_id}/paper.pdf"

            await _update_paper_storage_path(paper_id, storage_path, content_hash)

            log.info(
                "ingest_node.completed",
                run_id=ctx.run_id,
                paper_id=paper_id,
                storage_path=storage_path,
            )
            return {
                "paper_id": paper_id,
                "pdf_bytes": pdf_bytes,
                "pdf_storage_path": storage_path,
                **ctx.mark_completed(
                    {"paper_id": paper_id, "storage_path": storage_path}
                ),
            }

        # ── PATH 3: Full ingestion from scratch ───────────────────────────────
        if pdf_bytes is None:
            pdf_bytes, source = await _fetch_pdf_bytes(metadata, ctx.run_id)
        else:
            source = PaperSource.PDF_UPLOAD.value

        content_hash = _compute_sha256(pdf_bytes)
        await _check_duplicate(content_hash)

        paper_id = str(uuid.uuid4())
        storage_path = f"{paper_id}/paper.pdf"

        try:
            await _upload_pdf(pdf_bytes, storage_path)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ingest_node.upload_skipped", reason=str(exc), run_id=ctx.run_id
            )
            storage_path = f"local://{paper_id}/paper.pdf"

        try:
            await _create_paper_row(
                paper_id, source, storage_path, metadata, content_hash
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ingest_node.db_write_skipped", reason=str(exc), run_id=ctx.run_id
            )

        log.info(
            "ingest_node.completed",
            run_id=ctx.run_id,
            paper_id=paper_id,
            storage_path=storage_path,
        )

        return {
            "paper_id": paper_id,
            "pdf_bytes": pdf_bytes,
            "pdf_storage_path": storage_path,
            **ctx.mark_completed({"paper_id": paper_id, "storage_path": storage_path}),
        }

    except DuplicatePaperError as exc:
        return ctx.mark_failed(exc)

    except StageError:
        raise

    except Exception as exc:  # noqa: BLE001
        return ctx.mark_failed(exc)
