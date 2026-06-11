"""
pipeline.services.pipeline_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Business logic for managing LangGraph pipeline runs and viewing statuses.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import PaperORM, PipelineRunORM, StageResultORM
from src.db.session import get_db_context
from src.graph.pipeline import research_pipeline
from src.graph.state import PipelineState, make_initial_state
from src.models.paper import PaperMetadata
from src.models.run import PipelineRun, RunStatus, StageResult, StageStatus
from src.services.converters import run_orm_to_pydantic, stage_orm_to_pydantic
import structlog


class PipelineService:
    """Manages the lifecycle of pipeline executions for a paper."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_stage_pydantic(self, orm: StageResultORM) -> StageResult:
        """Convert StageResultORM to StageResult."""
        return stage_orm_to_pydantic(orm)

    def _to_run_pydantic(self, orm: PipelineRunORM) -> PipelineRun:
        """Convert PipelineRunORM to PipelineRun, including its stages."""
        return run_orm_to_pydantic(orm)

    @staticmethod
    def _resolve_final_status(stage_orms: list[StageResultORM]) -> str:
        statuses = {stage.status for stage in stage_orms}
        success_statuses = {"completed", "cached", "skipped"}
        has_success = any(status in success_statuses for status in statuses)
        has_failure = "failed" in statuses
        if has_failure and has_success:
            return RunStatus.PARTIAL.value
        if has_failure:
            return RunStatus.FAILED.value
        if has_success:
            return RunStatus.COMPLETED.value
        return RunStatus.FAILED.value

    @staticmethod
    def _extract_state(update_dict: dict[str, Any]) -> dict[str, Any] | None:
        last_state: dict[str, Any] | None = None
        for _, state in update_dict.items():
            last_state = state
        return last_state

    async def _persist_stage_deltas(
        self,
        *,
        session,
        run_id: uuid.UUID,
        stage_statuses: dict[str, Any],
        token_usage: dict[str, int],
        cached_stages: set[str],
        errors: list[Any],
    ) -> None:
        if not stage_statuses:
            return

        existing_stmt = select(StageResultORM).where(StageResultORM.run_id == run_id)
        existing_res = await session.execute(existing_stmt)
        existing_rows = existing_res.scalars().all()
        existing_by_stage = {row.stage_name: row for row in existing_rows}

        now = datetime.now(timezone.utc)
        for stage_name, status in stage_statuses.items():
            status_val = status.value if hasattr(status, "value") else status
            token_count = token_usage.get(stage_name)
            cached = stage_name in cached_stages
            error_message = next(
                (
                    err
                    for err in errors
                    if isinstance(err, str) and err.startswith(f"[{stage_name}]")
                ),
                None,
            )

            stage_orm = existing_by_stage.get(stage_name)
            if stage_orm is None:
                stage_orm = StageResultORM(
                    run_id=run_id,
                    stage_name=stage_name,
                    status=status_val,
                    started_at=now,
                    cached=cached,
                    token_count=token_count,
                    error_message=error_message,
                )
                if status_val in ("completed", "failed", "cached", "skipped"):
                    stage_orm.completed_at = now
                session.add(stage_orm)
                existing_by_stage[stage_name] = stage_orm
                continue

            # Persist only real deltas to avoid churn.
            stage_orm.status = status_val
            stage_orm.cached = cached
            stage_orm.token_count = token_count
            stage_orm.error_message = error_message
            if stage_orm.started_at is None:
                stage_orm.started_at = now
            if (
                status_val in ("completed", "failed", "cached", "skipped")
                and stage_orm.completed_at is None
            ):
                stage_orm.completed_at = now

    async def _execute_pipeline_run(
        self, run_id: uuid.UUID, initial_state: PipelineState
    ) -> None:
        try:
            async with get_db_context() as session:
                run_orm = await session.get(PipelineRunORM, run_id)
                if run_orm:
                    run_orm.status = RunStatus.RUNNING.value
                    if run_orm.started_at is None:
                        run_orm.started_at = datetime.now(timezone.utc)
                    await session.commit()

            async for update_dict in research_pipeline.astream(initial_state):  # type: ignore[arg-type]
                async with get_db_context() as session:
                    run_orm = await session.get(PipelineRunORM, run_id)
                    if not run_orm:
                        continue

                    last_state = self._extract_state(update_dict)
                    if last_state is None:
                        continue

                    stage_statuses = dict(last_state.get("stage_statuses", {}))
                    token_usage = dict(last_state.get("token_usage", {}))
                    cached_stages = set(last_state.get("cached_stages", set()))
                    errors = list(last_state.get("errors", []))

                    await self._persist_stage_deltas(
                        session=session,
                        run_id=run_id,
                        stage_statuses=stage_statuses,
                        token_usage=token_usage,
                        cached_stages=cached_stages,
                        errors=errors,
                    )

                    await session.commit()

            async with get_db_context() as session:
                run_orm = await session.get(
                    PipelineRunORM,
                    run_id,
                    options=[selectinload(PipelineRunORM.stages)],
                )
                if run_orm:
                    run_orm.total_tokens = sum(
                        stage.token_count or 0 for stage in run_orm.stages
                    )
                    run_orm.status = self._resolve_final_status(run_orm.stages)
                    run_orm.error = next(
                        (
                            stage.error_message
                            for stage in run_orm.stages
                            if stage.error_message
                        ),
                        None,
                    )
                    run_orm.completed_at = datetime.now(timezone.utc)
                    await session.commit()
        except Exception as exc:
            async with get_db_context() as session:
                run_orm = await session.get(PipelineRunORM, run_id)
                if run_orm:
                    run_orm.status = RunStatus.FAILED.value
                    run_orm.error = str(exc)
                    run_orm.completed_at = datetime.now(timezone.utc)
                    await session.commit()
            raise

    async def trigger_run(
        self, paper_id: uuid.UUID, user_id: str | uuid.UUID | None = None
    ) -> PipelineRun:
        """Sets up a new PipelineRunORM and invokes the LangGraph research pipeline in background."""
        paper_orm = None
        if user_id:
            stmt = select(PaperORM).where(PaperORM.id == paper_id)
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(
                PaperORM.user_id == parsed_user_id
            )  # Must own the paper to run pipeline

            res = await self.db.execute(stmt)
            paper_orm = res.scalars().first()
        else:
            paper_orm = await self.db.get(PaperORM, paper_id)
        if not paper_orm:
            raise ValueError(
                f"Paper {paper_id} not found or you don't have permission to modify it"
            )

        run_id = uuid.uuid4()
        run_orm = PipelineRunORM(
            id=run_id,
            paper_id=paper_id,
            status=RunStatus.PENDING.value,
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(run_orm)
        await self.db.commit()

        run_stmt = (
            select(PipelineRunORM)
            .where(PipelineRunORM.id == run_id)
            .options(selectinload(PipelineRunORM.stages))
        )
        run_res = await self.db.execute(run_stmt)
        run_orm = run_res.scalar_one()

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
        task = loop.create_task(self._execute_pipeline_run(run_id, initial_state))
        task.add_done_callback(self._on_pipeline_task_done)

        return self._to_run_pydantic(run_orm)

    @staticmethod
    def _on_pipeline_task_done(task: asyncio.Task) -> None:
        """Log unhandled exceptions from background pipeline tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            structlog.get_logger("pipeline_service").error(
                "background_pipeline_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    async def get_run_status(
        self, run_id: uuid.UUID, user_id: str | uuid.UUID | None = None
    ) -> PipelineRun:
        """Fetches a run configuration and all stage outcomes."""
        stmt = (
            select(PipelineRunORM)
            .join(PaperORM, PipelineRunORM.paper_id == PaperORM.id)
            .where(PipelineRunORM.id == run_id)
            .options(selectinload(PipelineRunORM.stages))
        )
        if user_id:
            from sqlalchemy import or_

            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(
                or_(PaperORM.user_id == parsed_user_id, PaperORM.is_public)
            )
        else:
            stmt = stmt.where(PaperORM.is_public)

        res = await self.db.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            raise ValueError(f"PipelineRun {run_id} not found or access denied")
        return self._to_run_pydantic(orm)

    async def get_latest_run_for_paper(
        self, paper_id: uuid.UUID, user_id: str | uuid.UUID | None = None
    ) -> PipelineRun | None:
        stmt = (
            select(PipelineRunORM)
            .join(PaperORM, PipelineRunORM.paper_id == PaperORM.id)
            .where(PipelineRunORM.paper_id == paper_id)
            .order_by(desc(PipelineRunORM.created_at))
            .options(selectinload(PipelineRunORM.stages))
            .limit(1)
        )
        if user_id:
            from sqlalchemy import or_

            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(
                or_(PaperORM.user_id == parsed_user_id, PaperORM.is_public)
            )
        else:
            stmt = stmt.where(PaperORM.is_public)

        res = await self.db.execute(stmt)
        orm = res.scalar_one_or_none()
        if orm is None:
            return None
        return self._to_run_pydantic(orm)

    async def get_stage_result(
        self, run_id: uuid.UUID, stage_name: str, user_id: str | uuid.UUID | None = None
    ) -> StageResult:
        """Outputs specific stage configuration result."""
        stmt = (
            select(StageResultORM)
            .join(PipelineRunORM, StageResultORM.run_id == PipelineRunORM.id)
            .join(PaperORM, PipelineRunORM.paper_id == PaperORM.id)
            .where(StageResultORM.run_id == run_id)
            .where(StageResultORM.stage_name == stage_name)
        )
        if user_id:
            from sqlalchemy import or_

            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            stmt = stmt.where(
                or_(PaperORM.user_id == parsed_user_id, PaperORM.is_public)
            )
        else:
            stmt = stmt.where(PaperORM.is_public)

        res = await self.db.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            raise ValueError(
                f"Stage {stage_name} not found for run {run_id} or access denied"
            )
        return self._to_stage_pydantic(orm)

    async def retry_stage(
        self, run_id: uuid.UUID, stage_name: str, user_id: str | uuid.UUID | None = None
    ) -> None:
        """Manually wipes cached state for a given stage and triggers pipeline re-run."""
        # Check permissions first via PipelineRun
        run_stmt = (
            select(PipelineRunORM)
            .join(PaperORM, PipelineRunORM.paper_id == PaperORM.id)
            .where(PipelineRunORM.id == run_id)
        )
        if user_id:
            parsed_user_id = (
                uuid.UUID(str(user_id)) if isinstance(user_id, str) else user_id
            )
            run_stmt = run_stmt.where(
                PaperORM.user_id == parsed_user_id
            )  # Must own the paper to run pipeline

        run_res = await self.db.execute(run_stmt)
        run_orm = run_res.scalar_one_or_none()
        if not run_orm:
            raise ValueError(
                f"PipelineRun {run_id} not found or you don't have permission to modify it"
            )

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
        task = loop.create_task(self._execute_pipeline_run(run_id, initial_state))
        task.add_done_callback(self._on_pipeline_task_done)
