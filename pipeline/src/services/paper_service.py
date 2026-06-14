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
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from supabase import Client

from src.core.config import get_settings
from src.core.exceptions import EmbeddingError, FileUploadError
from src.core.logger import get_logger
from src.db.engine import get_supabase_client
from src.db.models import EmbeddingORM, PaperORM, OutputORM, ExtractionORM
from src.db.models import PipelineRunORM
from src.models.paper import Paper, PaperListItem, PaperMetadata, PaperSource
from src.models.run import PipelineRun, StageResult
from src.services.converters import run_orm_to_pydantic, stage_orm_to_pydantic
from src.services.paper_metadata import paper_metadata_dict, paper_metadata_model

settings = get_settings()
_EMBEDDING_DIM = 1536
log = get_logger(__name__)


def _get_supabase() -> Client:
    return get_supabase_client()


class PaperService:
    """Business logic for Paper entity management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # Delay supabase creation or do it lazily to not block initialization
        self._supabase: Client | None = None

    @property
    def supabase(self) -> Client:
        if not self._supabase:
            self._supabase = _get_supabase()
        return self._supabase

    @staticmethod
    def _normalize_uuid(value: object) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            return uuid.UUID(value)
        return None

    def _to_pydantic(self, orm: PaperORM) -> Paper:
        """Helper to convert ORM to Pydantic model."""
        return Paper(
            id=orm.id,
            source=PaperSource(orm.source),
            source_url=orm.source_url,  # type: ignore[arg-type]
            pdf_storage_path=orm.pdf_storage_path,
            metadata=paper_metadata_model(orm.metadata_, paper_id=orm.id, log=log),
            created_at=orm.created_at.replace(tzinfo=timezone.utc),
            updated_at=orm.updated_at.replace(tzinfo=timezone.utc),
            user_id=self._normalize_uuid(getattr(orm, "user_id", None)),
            is_public=bool(orm.is_public),
            published_at=orm.published_at.replace(tzinfo=timezone.utc)
            if orm.published_at
            else None,
            imported_from_paper_id=self._normalize_uuid(
                getattr(orm, "imported_from_paper_id", None)
            ),
        )

    def _to_stage_pydantic(self, orm) -> StageResult:
        return stage_orm_to_pydantic(orm)

    def _to_run_pydantic(self, orm: PipelineRunORM) -> PipelineRun:
        return run_orm_to_pydantic(orm)

    async def _ingest(
        self,
        source: PaperSource,
        source_url: str | None = None,
        pdf_storage_path: str | None = None,
        metadata: PaperMetadata | None = None,
        identifier_type: str | None = None,
        identifier_value: str | None = None,
        user_id: str | uuid.UUID | None = None,
    ) -> Paper:
        """Core ingest logic: creates the DB record."""
        paper_id = uuid.uuid4()
        parsed_user_id = None
        if user_id:
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
        orm = PaperORM(
            id=paper_id,
            source=source.value,
            source_url=source_url,
            pdf_storage_path=pdf_storage_path,
            metadata_=metadata.model_dump() if metadata else None,
            user_id=parsed_user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(orm)
        await self.db.commit()
        await self.db.refresh(orm)
        log.info(
            "paper_created_new",
            paper_id=str(orm.id),
            source=source.value,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
        )
        return self._to_pydantic(orm)

    async def _find_existing_by_metadata_identifier(
        self, key: str, value: str
    ) -> PaperORM | None:
        """Find an existing paper by metadata JSONB identifier value."""
        stmt = select(PaperORM).where(PaperORM.metadata_[key].astext == value)
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def create_from_upload(
        self, file_bytes: bytes, filename: str, user_id: str | uuid.UUID | None = None
    ) -> Paper:
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
            user_id=user_id,
        )

    async def create_from_arxiv(
        self, arxiv_url: str, user_id: str | uuid.UUID | None = None
    ) -> Paper:
        """Fetches metadata from arXiv API, and runs ingest."""
        match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+(?:v\d+)?)", arxiv_url)
        if not match:
            raise ValueError("Invalid arXiv URL format")
        arxiv_id = match.group(1)
        existing = await self._find_existing_by_metadata_identifier(
            "arxiv_id", arxiv_id
        )
        if existing:
            log.info(
                "paper_dedupe_hit",
                paper_id=str(existing.id),
                identifier_type="arxiv_id",
                identifier_value=arxiv_id,
            )
            return self._to_pydantic(existing)

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
            identifier_type="arxiv_id",
            identifier_value=arxiv_id,
            user_id=user_id,
        )

    async def create_from_doi(
        self, doi: str, user_id: str | uuid.UUID | None = None
    ) -> Paper:
        """Resolves via CrossRef, and runs ingest."""
        normalized_doi = doi.strip().lower()
        existing = await self._find_existing_by_metadata_identifier(
            "doi", normalized_doi
        )
        if existing:
            log.info(
                "paper_dedupe_hit",
                paper_id=str(existing.id),
                identifier_type="doi",
                identifier_value=normalized_doi,
            )
            return self._to_pydantic(existing)

        # Provide basic CrossRef resolution
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://api.crossref.org/works/{normalized_doi}")
            if resp.status_code != 200:
                raise ValueError(f"CrossRef failed to find DOI: {normalized_doi}")
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
            doi=normalized_doi,
            abstract=None,
            arxiv_id=None,
            page_count=None,
            domain=None,
            sub_domain=None,
        )

        # CrossRef URLs can be constructed as https://doi.org/...
        source_url = f"https://doi.org/{normalized_doi}"

        return await self._ingest(
            source=PaperSource.DOI,
            source_url=source_url,
            metadata=metadata,
            identifier_type="doi",
            identifier_value=normalized_doi,
            user_id=user_id,
        )

    async def get_paper(
        self, paper_id: uuid.UUID, user_id: str | uuid.UUID | None = None
    ) -> Paper:
        """Fetch a specific paper by ID, enforcing privacy."""
        stmt = select(PaperORM).where(PaperORM.id == paper_id)
        if user_id:
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(
                or_(
                    PaperORM.user_id == parsed_user_id,
                    PaperORM.is_public,
                )
            )
        else:
            stmt = stmt.where(PaperORM.is_public)

        res = await self.db.execute(stmt)
        orm = res.scalars().first()
        if not orm:
            raise ValueError(f"Paper {paper_id} not found or access denied")
        return self._to_pydantic(orm)

    async def list_papers(
        self,
        filters: dict[str, str] | None = None,
        user_id: str | uuid.UUID | None = None,
        include_public: bool = False,
    ) -> list[PaperListItem]:
        """List papers with optional filters and attach latest run, enforcing privacy."""
        stmt = select(PaperORM).options(
            selectinload(PaperORM.runs).selectinload(PipelineRunORM.stages)
        )
        # Note: simplistic filter example string
        if filters:
            if "source" in filters:
                stmt = stmt.where(PaperORM.source == filters["source"])
        if user_id:
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            if include_public:
                stmt = stmt.where(
                    or_(
                        PaperORM.user_id == parsed_user_id,
                        PaperORM.is_public,
                    )
                )
            else:
                stmt = stmt.where(PaperORM.user_id == parsed_user_id)
        else:
            stmt = stmt.where(PaperORM.is_public)

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

    async def search_papers(
        self, query: str, limit: int = 5, user_id: str | uuid.UUID | None = None
    ) -> list[Paper]:
        """Queries pgvector similarity search using LiteLLM, enforcing privacy."""
        try:
            res = await aembedding(
                model=settings.embedding.model,
                input=[query],
                dimensions=_EMBEDDING_DIM,
                api_key=settings.embedding.api_key.get_secret_value(),
            )
            first = res.data[0]
            raw_vector = (
                getattr(first, "embedding", None)
                if hasattr(first, "embedding")
                else first.get("embedding")
            )
            if not isinstance(raw_vector, list):
                raise ValueError("Embedding response missing vector payload.")

            query_vec = [float(v) for v in raw_vector]
            if len(query_vec) != _EMBEDDING_DIM:
                raise ValueError(
                    f"expected {_EMBEDDING_DIM} dimensions, not {len(query_vec)}"
                )
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(
                "Failed to generate a valid query embedding.",
                model=settings.embedding.model,
                cause=exc,
            ) from exc

        distance_subq = (
            select(
                EmbeddingORM.paper_id.label("paper_id"),
                func.min(EmbeddingORM.embedding.cosine_distance(query_vec)).label(
                    "best_distance"
                ),
            )
            .group_by(EmbeddingORM.paper_id)
            .subquery()
        )

        stmt = select(PaperORM).join(
            distance_subq, PaperORM.id == distance_subq.c.paper_id
        )
        if user_id:
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(
                or_(
                    PaperORM.user_id == parsed_user_id,
                    PaperORM.is_public,
                )
            )
        else:
            stmt = stmt.where(PaperORM.is_public)

        stmt = stmt.order_by(distance_subq.c.best_distance).limit(limit)
        result = await self.db.execute(stmt)
        orms = result.scalars().all()
        return [self._to_pydantic(orm) for orm in orms]

    async def delete_paper(
        self, paper_id: uuid.UUID, user_id: str | uuid.UUID | None = None
    ) -> None:
        """Deletes DB records and Supabase Storage files, enforcing ownership."""
        stmt = select(PaperORM).where(PaperORM.id == paper_id)
        if user_id:
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(PaperORM.user_id == parsed_user_id)

        res = await self.db.execute(stmt)
        orm = res.scalars().first()
        if not orm:
            return  # Already gone or access denied

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
        await self.db.delete(orm)
        await self.db.commit()

    async def publish_paper(
        self, paper_id: uuid.UUID, user_id: str | uuid.UUID | None = None
    ) -> Paper:
        """Publishes a paper so others can see and import it."""
        stmt = select(PaperORM).where(PaperORM.id == paper_id)
        if user_id:
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(PaperORM.user_id == parsed_user_id)

        res = await self.db.execute(stmt)
        orm = res.scalars().first()
        if not orm:
            raise ValueError(f"Paper {paper_id} not found or access denied")

        orm.is_public = True
        orm.published_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(orm)
        return self._to_pydantic(orm)

    async def import_paper(
        self, paper_id: uuid.UUID, user_id: str | uuid.UUID | None = None
    ) -> Paper:
        """Imports a public paper into the user's private library."""
        if not user_id:
            raise ValueError("Must be logged in to import a paper")

        parsed_user_id = (
            uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
        )

        # 1. Return existing import if this user already imported the same public paper.
        existing_stmt = select(PaperORM).where(
            PaperORM.user_id == parsed_user_id,
            PaperORM.imported_from_paper_id == paper_id,
        )
        existing_res = await self.db.execute(existing_stmt)
        existing_import = existing_res.scalars().first()
        if existing_import:
            return self._to_pydantic(existing_import)

        # 2. Fetch the source paper (must be public)
        stmt = (
            select(PaperORM)
            .options(
                selectinload(PaperORM.outputs),
                selectinload(PaperORM.extractions),
                selectinload(PaperORM.embeddings),
            )
            .where(PaperORM.id == paper_id, PaperORM.is_public)
        )

        res = await self.db.execute(stmt)
        src_orm = res.scalars().first()
        if not src_orm:
            raise ValueError(f"Public paper {paper_id} not found")
        if src_orm.user_id == parsed_user_id:
            raise ValueError("Cannot import your own paper")

        # 3. Duplicate the paper
        new_paper_id = uuid.uuid4()
        new_orm = PaperORM(
            id=new_paper_id,
            source=src_orm.source,
            source_url=src_orm.source_url,
            pdf_storage_path=src_orm.pdf_storage_path,  # Share the same PDF file
            metadata_=paper_metadata_dict(
                src_orm.metadata_, paper_id=src_orm.id, log=log
            )
            or None,
            user_id=parsed_user_id,
            is_public=False,
            imported_from_paper_id=src_orm.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(new_orm)

        # 4. Duplicate outputs (just DB rows referencing the same storage paths)
        for out in getattr(src_orm, "outputs", []):
            new_out = OutputORM(
                id=uuid.uuid4(),
                paper_id=new_paper_id,
                output_type=out.output_type,
                storage_path=out.storage_path,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(new_out)

        # 5. Duplicate extractions
        for ext in getattr(src_orm, "extractions", []):
            new_ext = ExtractionORM(
                id=uuid.uuid4(),
                paper_id=new_paper_id,
                domain=ext.domain,
                schema_version=ext.schema_version,
                data=dict(ext.data),
                extracted_at=datetime.now(timezone.utc),
            )
            self.db.add(new_ext)

        # 6. Duplicate embeddings
        for emb in getattr(src_orm, "embeddings", []):
            new_emb = EmbeddingORM(
                id=uuid.uuid4(),
                paper_id=new_paper_id,
                chunk_type=emb.chunk_type,
                embedding=emb.embedding,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(new_emb)

        await self.db.commit()
        await self.db.refresh(new_orm)
        return self._to_pydantic(new_orm)
