"""
pipeline.services.pipeline_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Business logic for managing LangGraph pipeline runs and viewing statuses.
"""

import asyncio
import uuid
import uuid as uuid_pkg
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipeline.db.models import PaperORM, PipelineRunORM, StageResultORM
from pipeline.graph.pipeline import research_pipeline
from pipeline.graph.state import make_initial_state
from pipeline.models.paper import PaperMetadata
from pipeline.models.run import PipelineRun, RunStatus, StageResult, StageStatus


class PipelineService:
    """Manages the lifecycle of pipeline executions for a paper."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_stage_pydantic(self, orm: StageResultORM) -> StageResult:
        """Convert StageResultORM to StageResult."""
        return StageResult(
            stage_name=orm.stage_name,
            status=StageStatus(orm.status),
            started_at=orm.started_at.replace(tzinfo=timezone.utc)
            if orm.started_at
            else None,
            completed_at=orm.completed_at.replace(tzinfo=timezone.utc)
            if orm.completed_at
            else None,
            error_message=orm.error_message,
            cached=orm.cached,
            token_count=orm.token_count,
        )

    def _to_run_pydantic(self, orm: PipelineRunORM) -> PipelineRun:
        """Convert PipelineRunORM to PipelineRun, including its stages."""
        run = PipelineRun(
            id=orm.id,
            paper_id=orm.paper_id,
            status=RunStatus(orm.status),
            started_at=orm.started_at.replace(tzinfo=timezone.utc)
            if orm.started_at
            else None,
            completed_at=orm.completed_at.replace(tzinfo=timezone.utc)
            if orm.completed_at
            else None,
            total_tokens=orm.total_tokens,
            error=orm.error,
            created_at=orm.created_at.replace(tzinfo=timezone.utc),
            stages={},
        )
        if orm.stages:
            for s in orm.stages:
                run.stages[s.stage_name] = self._to_stage_pydantic(s)
        return run

    async def trigger_run(self, paper_id: uuid.UUID) -> PipelineRun:
        """Sets up a new PipelineRunORM and invokes the LangGraph research pipeline in background."""
        paper_orm = await self.db.get(PaperORM, paper_id)
        if not paper_orm:
            raise ValueError(f"Paper {paper_id} not found")

        run_id = uuid_pkg.uuid4()
        run_orm = PipelineRunORM(
            id=run_id,
            paper_id=paper_id,
            status=RunStatus.PENDING.value,
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(run_orm)
        await self.db.commit()
        await self.db.refresh(run_orm)

        metadata = PaperMetadata(**paper_orm.metadata_) if paper_orm.metadata_ else None

        initial_state = make_initial_state(
            run_id=str(run_id),
            paper_metadata=metadata,
            extra={
                "paper_id": str(paper_id),
                "pdf_storage_path": paper_orm.pdf_storage_path,
            },
        )

        # Trigger execution safely in background via asyncio
        loop = asyncio.get_running_loop()

        async def _run_pipeline() -> None:
            # We must create a new session or be aware that db session lifetime might end.
            # In a robust system, the graph nodes would manage their own DB sessions.
            try:
                await research_pipeline.ainvoke(initial_state)
            except Exception:
                # Basic top level catcher if it fails completely
                # Graph usually catches in its nodes, but this ensures no silent deadlocks
                pass

        loop.create_task(_run_pipeline())

        return self._to_run_pydantic(run_orm)

    async def get_run_status(self, run_id: uuid.UUID) -> PipelineRun:
        """Fetches a run configuration and all stage outcomes."""
        stmt = (
            select(PipelineRunORM)
            .where(PipelineRunORM.id == run_id)
            .options(selectinload(PipelineRunORM.stages))
        )
        res = await self.db.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            raise ValueError(f"PipelineRun {run_id} not found")
        return self._to_run_pydantic(orm)

    async def get_stage_result(self, run_id: uuid.UUID, stage_name: str) -> StageResult:
        """Outputs specific stage configuration result."""
        stmt = (
            select(StageResultORM)
            .where(StageResultORM.run_id == run_id)
            .where(StageResultORM.stage_name == stage_name)
        )
        res = await self.db.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            raise ValueError(f"Stage {stage_name} not found for run {run_id}")
        return self._to_stage_pydantic(orm)

    async def retry_stage(self, run_id: uuid.UUID, stage_name: str) -> None:
        """Manually wipes cached state for a given stage and triggers pipeline re-run."""
        # We need the base pipeline state
        # Usually from graph checkpointer or reconstructing from the DB context.
        # We will assume graph reads from StageResultORM locally and caching logic dictates resume

        stmt = (
            select(StageResultORM)
            .where(StageResultORM.run_id == run_id)
            .where(StageResultORM.stage_name == stage_name)
        )
        res = await self.db.execute(stmt)
        stage_orm = res.scalar_one_or_none()
        if stage_orm:
            # Reset
            stage_orm.status = StageStatus.PENDING.value
            stage_orm.completed_at = None
            stage_orm.error_message = None
            stage_orm.cached = False
            stage_orm.token_count = 0
            await self.db.commit()

        run_orm_stmt = select(PipelineRunORM).where(PipelineRunORM.id == run_id)
        run_res = await self.db.execute(run_orm_stmt)
        run_orm = run_res.scalar_one_or_none()
        if not run_orm:
            raise ValueError(f"PipelineRun {run_id} not found")

        paper_orm = await self.db.get(PaperORM, run_orm.paper_id)
        if not paper_orm:
            raise ValueError("Associated Paper not found for retry")

        metadata = PaperMetadata(**paper_orm.metadata_) if paper_orm.metadata_ else None

        # Build initial state. Graph nodes checking DB will skip completed stages, executing only pending.
        initial_state = make_initial_state(
            run_id=str(run_id),
            paper_metadata=metadata,
            extra={
                "paper_id": str(run_orm.paper_id),
                "pdf_storage_path": paper_orm.pdf_storage_path,
            },
        )

        loop = asyncio.get_running_loop()

        async def _rerun_pipeline() -> None:
            try:
                await research_pipeline.ainvoke(initial_state)
            except Exception:
                pass

        loop.create_task(_rerun_pipeline())
