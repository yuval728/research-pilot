"""
pipeline.api.routes.papers
~~~~~~~~~~~~~~~~~~~~~~~~~~
Paper ingestion, retrieval, and deletion endpoints.
All business logic is delegated to PaperService / ExportService.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from pipeline.api.dependencies import (
    CurrentUserDep,
    ExportServiceDep,
    PaperServiceDep,
)
from pipeline.models.output import OutputBundle
from pipeline.models.paper import Paper

router = APIRouter(prefix="/papers", tags=["papers"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ArxivRequest(BaseModel):
    url: str


class DoiRequest(BaseModel):
    doi: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=Paper,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a paper via PDF upload",
)
async def upload_paper(
    paper_service: PaperServiceDep,
    _user: CurrentUserDep,
    file: UploadFile = File(..., description="PDF file to upload"),
) -> Paper:
    """Accept a PDF file, upload it to Supabase Storage, and create a Paper record."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PDF files are accepted",
        )
    filename = file.filename or "upload.pdf"
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    return await paper_service.create_from_upload(file_bytes, filename)


@router.post(
    "/arxiv",
    response_model=Paper,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a paper via arXiv URL",
)
async def ingest_from_arxiv(
    body: ArxivRequest,
    paper_service: PaperServiceDep,
    _user: CurrentUserDep,
) -> Paper:
    """Fetch metadata from the arXiv API, then create a Paper record."""
    return await paper_service.create_from_arxiv(body.url)


@router.post(
    "/doi",
    response_model=Paper,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a paper via DOI",
)
async def ingest_from_doi(
    body: DoiRequest,
    paper_service: PaperServiceDep,
    _user: CurrentUserDep,
) -> Paper:
    """Resolve the DOI via CrossRef, fetch metadata, and create a Paper record."""
    return await paper_service.create_from_doi(body.doi)


@router.get(
    "",
    response_model=list[Paper],
    summary="List all papers",
)
async def list_papers(
    paper_service: PaperServiceDep,
    _user: CurrentUserDep,
    source: str | None = Query(
        None,
        description="Filter by source (pdf_upload, arxiv_url, doi)",
    ),
) -> list[Paper]:
    """Return all papers in the library, with optional source filter."""
    filters: dict[str, str] | None = {"source": source} if source else None
    return await paper_service.list_papers(filters)


@router.get(
    "/{paper_id}",
    response_model=Paper,
    summary="Get a single paper",
)
async def get_paper(
    paper_id: uuid.UUID,
    paper_service: PaperServiceDep,
    _user: CurrentUserDep,
) -> Paper:
    """Fetch a single paper record with full metadata by its UUID."""
    try:
        return await paper_service.get_paper(paper_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.delete(
    "/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a paper and all its outputs",
)
async def delete_paper(
    paper_id: uuid.UUID,
    paper_service: PaperServiceDep,
    _user: CurrentUserDep,
) -> None:
    """Delete a paper record, its Supabase Storage files, and all cascade DB records."""
    await paper_service.delete_paper(paper_id)


@router.get(
    "/{paper_id}/outputs",
    response_model=OutputBundle,
    summary="Fetch a paper's full output bundle",
)
async def get_paper_outputs(
    paper_id: uuid.UUID,
    export_service: ExportServiceDep,
    _user: CurrentUserDep,
) -> OutputBundle:
    """Return all pipeline outputs (summaries, diagrams, code, report) for a paper."""
    try:
        return await export_service.get_output_bundle(paper_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
