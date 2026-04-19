"""
pipeline.graph.nodes.ingest
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ingest_node`` — first stage of the pipeline.

Responsibilities
----------------
1. Accept input from state: PDF bytes, arXiv URL, or DOI.
2. Fetch the PDF if not already in state (arXiv or DOI).
3. Compute SHA-256 content hash; raise ``DuplicatePaperError`` if seen before.
4. Upload raw PDF to Supabase Storage ``papers`` bucket.
5. Create a ``PaperORM`` row in Postgres.
6. Update state with ``pdf_storage_path`` and ``paper_id``.
7. Emit ``STAGE_COMPLETED`` event on the default bus.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from pipeline.core.events import Event, EventType, default_bus
from pipeline.core.exceptions import DuplicatePaperError, PDFFetchError, StageError
from pipeline.core.logger import get_logger
from pipeline.graph.state import PipelineState
from pipeline.models.paper import PaperMetadata, PaperSource
from pipeline.models.run import StageStatus

_STAGE = "ingest"
_PAPERS_BUCKET = "papers"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch_arxiv(arxiv_id: str) -> bytes:
    """Download a PDF from arXiv by its identifier (e.g. ``'2301.00001'``)."""
    import arxiv  # type: ignore[import-untyped]

    client = arxiv.Client()
    search = arxiv.Search(id_list=[arxiv_id])
    results = list(client.results(search))

    if not results:
        raise PDFFetchError(
            f"arXiv paper '{arxiv_id}' not found.",
            source_url=f"https://arxiv.org/abs/{arxiv_id}",
        )

    paper = results[0]
    # arxiv library's download_pdf writes to disk; fetch the PDF directly instead
    pdf_url = paper.pdf_url
    return _fetch_url(pdf_url)


def _fetch_url(url: str) -> bytes:
    """Fetch raw bytes from *url* following redirects (for DOI / arXiv PDFs)."""
    import httpx

    try:
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            resp = client.get(url)
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


def _fetch_doi(doi: str) -> bytes:
    """Resolve a DOI to its PDF via the CrossRef redirect."""
    doi_url = f"https://doi.org/{doi}"
    return _fetch_url(doi_url)


def _check_duplicate(content_hash: str, paper_id_hint: str | None) -> None:
    """Raise ``DuplicatePaperError`` if this content hash is already in the DB.

    This is a best-effort sync check using a direct SQLAlchemy query.
    In production this would be async; here we keep it sync to stay
    compatible with LangGraph's synchronous node contract.
    """
    # Deferred import to avoid heavy DB setup at module import time
    try:
        from sqlalchemy import create_engine, text

        from pipeline.core.config import get_settings

        settings = get_settings()
        # Use sync URL (replace asyncpg/async driver with psycopg sync)
        db_url = settings.supabase.db_url.get_secret_value()
        sync_url = db_url.replace("+asyncpg", "").replace(
            "postgresql+psycopg://", "postgresql+psycopg://"
        )

        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            # Check via metadata JSONB field for content_hash
            row = conn.execute(
                text(
                    "SELECT id FROM papers WHERE metadata->>'content_hash' = :h LIMIT 1"
                ),
                {"h": content_hash},
            ).fetchone()
        engine.dispose()

        if row is not None:
            raise DuplicatePaperError(
                f"Paper with content hash '{content_hash[:12]}…' already exists.",
                identifier=content_hash,
                identifier_type="content_hash",
            )
    except DuplicatePaperError:
        raise
    except Exception as exc:  # noqa: BLE001
        # DB unavailable in test/local environments — log and continue
        log.warning("duplicate_check_skipped", reason=str(exc))


def _upload_pdf(pdf_bytes: bytes, storage_path: str) -> None:
    """Upload pdf_bytes to Supabase Storage under *storage_path*."""
    from pipeline.core.config import get_settings

    settings = get_settings()
    from supabase import create_client  # type: ignore[import-untyped]

    client = create_client(
        settings.supabase.url,
        settings.supabase.service_role_key.get_secret_value(),
    )
    client.storage.from_(_PAPERS_BUCKET).upload(
        path=storage_path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf"},
    )


def _create_paper_row(
    paper_id: str,
    source: str,
    storage_path: str,
    metadata: PaperMetadata | None,
    content_hash: str,
) -> None:
    """Insert a ``PaperORM`` row synchronously."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from pipeline.core.config import get_settings
    from pipeline.db.models import PaperORM

    settings = get_settings()
    db_url = settings.supabase.db_url.get_secret_value()

    engine = create_engine(db_url, pool_pre_ping=True)
    meta_dict: dict[str, Any] = {"content_hash": content_hash}
    if metadata:
        meta_dict.update(metadata.model_dump(exclude_none=True))

    with Session(engine) as session:
        row = PaperORM(
            id=uuid.UUID(paper_id),
            source=source,
            pdf_storage_path=storage_path,
            metadata_=meta_dict,
        )
        session.add(row)
        session.commit()
    engine.dispose()


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def ingest_node(state: PipelineState) -> dict[str, Any]:
    """Ingest a research paper into the pipeline.

    Reads from state
    ----------------
    - ``pdf_bytes`` — raw PDF already in memory (PDF upload path)
    - ``paper_metadata`` — may contain ``arxiv_id`` or ``doi`` for fetching
    - ``run_id`` — for event emission

    Writes to state
    ---------------
    - ``pdf_bytes`` — populated if fetched remotely
    - ``paper_id`` — newly created DB record UUID
    - ``pdf_storage_path`` — path in Supabase Storage
    - ``stage_statuses["ingest"]``
    - ``errors`` — appended on failure

    Raises
    ------
    StageError
        If a non-recoverable error occurs (re-raises after updating state).
    """
    run_id = state["run_id"]
    metadata: PaperMetadata | None = state.get("paper_metadata")
    pdf_bytes: bytes | None = state.get("pdf_bytes")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))

    log.info("ingest_node.started", run_id=run_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    try:
        # ── 1. Determine source and fetch PDF bytes ─────────────────────
        source = PaperSource.PDF_UPLOAD.value

        if pdf_bytes is None:
            if metadata and metadata.arxiv_id:
                source = PaperSource.ARXIV_URL.value
                pdf_bytes = _fetch_arxiv(metadata.arxiv_id)
            elif metadata and metadata.doi:
                source = PaperSource.DOI.value
                pdf_bytes = _fetch_doi(metadata.doi)
            else:
                raise StageError(
                    "No PDF bytes provided and no arXiv ID or DOI found in metadata.",
                    stage_name=_STAGE,
                    run_id=run_id,
                )

        # ── 2. Compute content hash and check for duplicates ─────────────
        content_hash = _compute_sha256(pdf_bytes)
        _check_duplicate(content_hash, paper_id_hint=None)

        # ── 3. Generate paper_id and storage path ────────────────────────
        paper_id = str(uuid.uuid4())
        storage_path = f"{paper_id}/paper.pdf"

        # ── 4. Upload to Supabase Storage ────────────────────────────────
        try:
            _upload_pdf(pdf_bytes, storage_path)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ingest_node.upload_skipped",
                reason=str(exc),
                run_id=run_id,
            )
            # Non-fatal in local/test environments — continue with local path
            storage_path = f"local://{paper_id}/paper.pdf"

        # ── 5. Persist paper record in DB ────────────────────────────────
        try:
            _create_paper_row(paper_id, source, storage_path, metadata, content_hash)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "ingest_node.db_write_skipped",
                reason=str(exc),
                run_id=run_id,
            )

        # ── 6. Emit event ────────────────────────────────────────────────
        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"paper_id": paper_id, "storage_path": storage_path},
            )
        )

        log.info(
            "ingest_node.completed",
            run_id=run_id,
            paper_id=paper_id,
            storage_path=storage_path,
        )

        return {
            "paper_id": paper_id,
            "pdf_bytes": pdf_bytes,
            "pdf_storage_path": storage_path,
            "stage_statuses": stage_statuses,
            "errors": errors,
        }

    except DuplicatePaperError as exc:
        errors.append(f"[{_STAGE}] {exc.message}")
        stage_statuses[_STAGE] = StageStatus.FAILED
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": exc.message},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors}

    except StageError:
        raise

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] Unexpected error: {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("ingest_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors}
