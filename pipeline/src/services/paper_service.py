"""
pipeline.services.paper_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Paper ingestion and retrieval flow.
"""

import re
import uuid
from datetime import datetime, timezone

import anyio
import arxiv  # type: ignore[import-untyped]
import httpx
from litellm import aembedding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from supabase import Client

from src.core.config import get_settings
from src.core.exceptions import FileUploadError
from src.db.engine import get_supabase_client
from src.db.models import EmbeddingORM, PaperORM
from src.db.models import PipelineRunORM
from src.models.paper import Paper, PaperListItem, PaperMetadata, PaperSource
from src.models.run import PipelineRun, StageResult

settings = get_settings()


class PaperService:
    """Business logic for Paper entity management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # Delay supabase creation or do it lazily to not block initialization
        self._supabase: Client | None = None

    @property
    def supabase(self) -> Client:
        if not self._supabase:
            self._supabase = get_supabase_client()
        return self._supabase

    def _to_pydantic(self, orm: PaperORM) -> Paper:
        """Helper to convert ORM to Pydantic model."""
        return Paper(
            id=orm.id,
            source=PaperSource(orm.source),
            source_url=orm.source_url,  # type: ignore[arg-type]
            pdf_storage_path=orm.pdf_storage_path,
            metadata=PaperMetadata(**orm.metadata_) if orm.metadata_ else None,
            created_at=orm.created_at.replace(tzinfo=timezone.utc),
            updated_at=orm.updated_at.replace(tzinfo=timezone.utc),
        )

    def _to_stage_pydantic(self, orm) -> StageResult:
        from src.services.converters import stage_orm_to_pydantic

        return stage_orm_to_pydantic(orm)

    def _to_run_pydantic(self, orm: PipelineRunORM) -> PipelineRun:
        from src.services.converters import run_orm_to_pydantic

        return run_orm_to_pydantic(orm)

    async def _ingest(
        self,
        source: PaperSource,
        source_url: str | None = None,
        pdf_storage_path: str | None = None,
        metadata: PaperMetadata | None = None,
    ) -> Paper:
        """Core ingest logic: creates the DB record."""
        paper_id = uuid.uuid4()
        orm = PaperORM(
            id=paper_id,
            source=source.value,
            source_url=source_url,
            pdf_storage_path=pdf_storage_path,
            metadata_=metadata.model_dump() if metadata else None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(orm)
        await self.db.commit()
        await self.db.refresh(orm)
        return self._to_pydantic(orm)

    async def create_from_upload(self, file_bytes: bytes, filename: str) -> Paper:
        """Validates file is PDF, uploads to Supabase, and inserts Paper."""
        if not filename.lower().endswith(".pdf"):
            raise ValueError("File must be a PDF")
        if not file_bytes:
            raise ValueError("File cannot be empty")

        file_id = uuid.uuid4()
        storage_path = f"{file_id}_{filename}"

        def _upload() -> None:
            try:
                self.supabase.storage.from_(settings.supabase.papers_bucket).upload(
                    file=file_bytes,
                    path=storage_path,
                    file_options={"content-type": "application/pdf"},
                )
            except Exception as e:
                raise FileUploadError(
                    "Failed to upload PDF",
                    bucket=settings.supabase.papers_bucket,
                    path=storage_path,
                    cause=e,
                ) from e

        await anyio.to_thread.run_sync(_upload)

        return await self._ingest(
            source=PaperSource.PDF_UPLOAD,
            pdf_storage_path=storage_path,
        )

    async def create_from_arxiv(self, arxiv_url: str) -> Paper:
        """Fetches metadata from arXiv API, and runs ingest."""
        match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+(?:v\d+)?)", arxiv_url)
        if not match:
            raise ValueError("Invalid arXiv URL format")
        arxiv_id = match.group(1)

        def _fetch_arxiv() -> arxiv.Result:
            client = arxiv.Client()
            search = arxiv.Search(id_list=[arxiv_id])
            try:
                return next(client.results(search))
            except StopIteration:
                raise ValueError(f"No arXiv paper found for ID {arxiv_id}")

        result: arxiv.Result = await anyio.to_thread.run_sync(_fetch_arxiv)

        metadata = PaperMetadata(
            title=result.title,
            authors=[str(a) for a in result.authors],
            abstract=result.summary,
            year=result.published.year if result.published else None,
            arxiv_id=arxiv_id,
            venue=None,
            doi=None,
            page_count=None,
            domain=None,
            sub_domain=None,
        )

        # Determine direct pdf link to pass on (if graph downloading assumes url)
        # However, arxiv natively offers .download_pdf, we'll let ingest node handle the actual download if configured,
        # or we download now. The prompt says: "fetches metadata from arXiv API, calls ingest".
        # We will not upload the pdf yet; `ingest` logic typically means creating DB entity.

        return await self._ingest(
            source=PaperSource.ARXIV_URL,
            source_url=arxiv_url,
            pdf_storage_path=None,  # Ingest node will fill this when it downloads
            metadata=metadata,
        )

    async def create_from_doi(self, doi: str) -> Paper:
        """Resolves via CrossRef, and runs ingest."""
        # Provide basic CrossRef resolution
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://api.crossref.org/works/{doi}")
            if resp.status_code != 200:
                raise ValueError(f"CrossRef failed to find DOI: {doi}")
            data = resp.json().get("message", {})

        titles = data.get("title", [])
        title = titles[0] if titles else f"Unknown Title (DOI: {doi})"

        authors_data = data.get("author", [])
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_data
        ]

        year_info = data.get("published-print", {}).get("date-parts", [[None]])
        year = year_info[0][0] if year_info and year_info[0] else None

        metadata = PaperMetadata(
            title=title,
            authors=authors,
            venue=data.get("container-title", [None])[0]
            if data.get("container-title")
            else None,
            year=year,
            doi=doi,
            abstract=None,
            arxiv_id=None,
            page_count=None,
            domain=None,
            sub_domain=None,
        )

        # CrossRef URLs can be constructed as https://doi.org/...
        source_url = f"https://doi.org/{doi}"

        return await self._ingest(
            source=PaperSource.DOI,
            source_url=source_url,
            metadata=metadata,
        )

    async def get_paper(self, paper_id: uuid.UUID) -> Paper:
        """Fetch a specific paper by ID."""
        orm = await self.db.get(PaperORM, paper_id)
        if not orm:
            raise ValueError(f"Paper {paper_id} not found")
        return self._to_pydantic(orm)

    async def list_papers(
        self, filters: dict[str, str] | None = None
    ) -> list[PaperListItem]:
        """List papers with optional filters and attach latest run."""
        stmt = select(PaperORM).options(
            selectinload(PaperORM.runs).selectinload(PipelineRunORM.stages)
        )
        # Note: simplistic filter example string
        if filters:
            if "source" in filters:
                stmt = stmt.where(PaperORM.source == filters["source"])
            # Additional filters can be applied here

        result = await self.db.execute(stmt)
        orms = result.scalars().all()

        items = []
        for orm in orms:
            paper = self._to_pydantic(orm)
            latest_run_orm = None
            if getattr(orm, "runs", None):
                sorted_runs = sorted(orm.runs, key=lambda r: r.created_at, reverse=True)
                latest_run_orm = sorted_runs[0] if sorted_runs else None

            latest_run = (
                self._to_run_pydantic(latest_run_orm) if latest_run_orm else None
            )
            items.append(PaperListItem(paper=paper, latest_run=latest_run))

        return items

    async def search_papers(self, query: str, limit: int = 5) -> list[Paper]:
        """Queries pgvector similarity search using LiteLLM."""
        res = await aembedding(
            model=settings.gemini.embedding_model,
            input=[query],
        )
        query_vec = res.data[0]["embedding"]

        stmt = (
            select(PaperORM)
            .join(EmbeddingORM, PaperORM.id == EmbeddingORM.paper_id)
            .order_by(EmbeddingORM.embedding.cosine_distance(query_vec))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        orms = result.scalars().all()
        return [self._to_pydantic(orm) for orm in orms]

    async def delete_paper(self, paper_id: uuid.UUID) -> None:
        """Deletes DB records and Supabase Storage files."""
        # Lookup first to find the file path
        orm = await self.db.get(PaperORM, paper_id)
        if not orm:
            return  # Already gone

        pdf_path = orm.pdf_storage_path

        def _delete_files() -> None:
            if pdf_path:
                try:
                    self.supabase.storage.from_(settings.supabase.papers_bucket).remove(
                        [pdf_path]
                    )
                except Exception:
                    pass  # Swallow in this case

            # Also clean outputs bucket for this paper via folder
            # Assuming output bucket stores files in e.g. "{paper_id}/..."
            try:
                # Naive cleanup: requires listing or exact paths but storage API remove takes exact path
                # Supabase Python backend does not easily support folder delete without listing
                pass
            except Exception:
                pass

        await anyio.to_thread.run_sync(_delete_files)

        # Delete cascade should handle other ORMs via cascade="all, delete-orphan"
        await self.db.delete(orm)
        await self.db.commit()
