"""
pipeline.services.export_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Retrieves generated assets from Supabase Storage and DB.
"""

import uuid

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client, create_client  # type: ignore[import-untyped]

from src.core.config import get_settings
from src.core.exceptions import FileNotFoundError, StorageError
from src.db.models import OutputORM
from src.models.output import (
    CodeOutput,
    DiagramOutput,
    DiagramType,
    OutputBundle,
    ReportOutput,
    SummaryLevel,
    SummaryOutput,
)

settings = get_settings()


def _get_supabase() -> Client:
    return create_client(
        settings.supabase.url, settings.supabase.service_role_key.get_secret_value()
    )


class ExportService:
    """Retrieves generated pipeline artifacts for a paper."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._supabase: Client | None = None

    @property
    def supabase(self) -> Client:
        if not self._supabase:
            self._supabase = _get_supabase()
        return self._supabase

    async def _download_file(self, filepath: str) -> bytes:
        """Download file and map storage errors."""

        def _download() -> bytes:
            try:
                # `download` returns bytes in supabase 2.x
                return self.supabase.storage.from_(
                    settings.supabase.outputs_bucket
                ).download(filepath)
            except Exception as e:
                # The python supabase client raises generic Exceptions or StorageException
                error_str = str(e).lower()
                if "not found" in error_str or "object not found" in error_str:
                    raise FileNotFoundError(
                        f"File {filepath} not found in outputs",
                        bucket=settings.supabase.outputs_bucket,
                        path=filepath,
                    ) from e
                raise StorageError(f"Failed to download {filepath}: {e}") from e

        return await anyio.to_thread.run_sync(_download)

    async def _get_output_path(self, paper_id: uuid.UUID, output_type: str) -> str:
        """Helper to get the storage path from DB."""
        stmt = (
            select(OutputORM.storage_path)
            .where(OutputORM.paper_id == paper_id)
            .where(OutputORM.output_type == output_type)
        )
        res = await self.db.execute(stmt)
        path = res.scalar_one_or_none()
        if not path:
            raise ValueError(f"No {output_type} found for paper {paper_id}")
        return path

    async def get_report_markdown(self, paper_id: uuid.UUID) -> str:
        """Fetches markdown report from Supabase Storage."""
        path = await self._get_output_path(paper_id, "report")
        data = await self._download_file(path)
        return data.decode("utf-8")

    async def get_diagram_svg(
        self, paper_id: uuid.UUID, diagram_type: DiagramType
    ) -> str:
        """Fetches SVG from storage."""
        path = await self._get_output_path(paper_id, f"diagram_{diagram_type.value}")
        data = await self._download_file(path)
        return data.decode("utf-8")

    async def get_code_file(self, paper_id: uuid.UUID) -> bytes:
        """Fetches .py file."""
        path = await self._get_output_path(paper_id, "code_python")
        return await self._download_file(path)

    async def get_notebook(self, paper_id: uuid.UUID) -> bytes:
        """Fetches .ipynb file."""
        path = await self._get_output_path(paper_id, "code_notebook")
        return await self._download_file(path)

    async def get_output_bundle(self, paper_id: uuid.UUID) -> OutputBundle:
        """Assembles all outputs into one response."""
        stmt = select(OutputORM).where(OutputORM.paper_id == paper_id)
        res = await self.db.execute(stmt)
        orms = res.scalars().all()

        bundle = OutputBundle(
            paper_id=paper_id,
            summaries=[],
            diagrams=[],
            code=None,
            report=None,
        )
        code_paths = {}

        for orm in orms:
            t = orm.output_type
            if t.startswith("summary_"):
                level_str = t.replace("summary_", "")
                # Note: Actual text is missing from inline DB storage in current schema,
                # but we will build what we can.
                # If `inline:` we treat it as placeholder, else we could download.
                content = orm.storage_path
                if content.startswith("inline:"):
                    content = "Summary content not available in DB (inline placeholder)"
                bundle.summaries.append(
                    SummaryOutput(
                        paper_id=paper_id,
                        level=SummaryLevel(level_str),
                        content=content,
                    )
                )
            elif t.startswith("diagram_"):
                level_str = t.replace("diagram_", "")
                bundle.diagrams.append(
                    DiagramOutput(
                        paper_id=paper_id,
                        diagram_type=DiagramType(level_str),
                        dsl_code="DSL Code Omitted",  # Omitted since DB just has path
                        svg_path=orm.storage_path,
                    )
                )
            elif t == "report":
                bundle.report = ReportOutput(
                    paper_id=paper_id, markdown_path=orm.storage_path
                )
            elif t == "code_python":
                code_paths["python"] = orm.storage_path
            elif t == "code_notebook":
                code_paths["notebook"] = orm.storage_path

        if code_paths or any(orm.output_type == "codegen" for orm in orms):
            # Sometimes single "codegen" type is inserted
            bundle.code = CodeOutput(
                paper_id=paper_id,
                python_path=code_paths.get("python"),
                notebook_path=code_paths.get("notebook"),
                synthetic_data_description=None,
            )

        return bundle
