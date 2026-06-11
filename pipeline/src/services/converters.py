"""
pipeline.services.converters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared ORM → Pydantic model converters.

Extracted from paper_service.py and pipeline_service.py where identical
conversion logic was duplicated (Issue #18).
"""

from __future__ import annotations

from datetime import timezone
import json

from src.db.models import OutputORM, PipelineRunORM, StageResultORM
from src.models.output import (
    CodeOutput,
    DiagramOutput,
    DiagramType,
    ReportOutput,
    SummaryLevel,
    SummaryOutput,
)
from src.models.run import PipelineRun, RunStatus, StageResult, StageStatus


class OutputDeserializer:
    """Shared logic for parsing OutputORM records into Pydantic models."""

    @staticmethod
    def parse_summary(orm: OutputORM) -> SummaryOutput:
        """Parse an OutputORM record into a SummaryOutput."""
        level_str = orm.output_type.replace("summary_", "")
        content = getattr(orm, "content", None)
        # Guard: content must be an actual string. During tests, ORM attributes
        # that are not explicitly set on a MagicMock return a new MagicMock,
        # which is truthy but not a valid string for Pydantic.
        if not isinstance(content, str):
            content = None
        if not content and orm.storage_path and orm.storage_path.startswith("inline:"):
            content = orm.storage_path[len("inline:") :]
            if content == f"summary_{level_str}":  # Backwards compatibility
                content = "Summary content not available in DB (inline placeholder)"

        return SummaryOutput(
            paper_id=orm.paper_id,
            level=SummaryLevel(level_str),
            content=content or "",
        )

    @staticmethod
    def parse_diagram(orm: OutputORM) -> DiagramOutput:
        """Parse an OutputORM record into a DiagramOutput."""
        level_str = orm.output_type.replace("diagram_", "")
        svg_path = orm.storage_path
        dsl_code = getattr(orm, "content", None) or "DSL Code Omitted"

        # Legacy JSON format compatibility
        if orm.storage_path and orm.storage_path.startswith("json:"):
            try:
                data = json.loads(orm.storage_path[5:])
                dsl_code = data.get("dsl_code", dsl_code)
                svg_path = data.get("svg_path")
            except Exception:
                pass
        # Legacy inline format compatibility
        elif orm.storage_path and orm.storage_path.startswith("inline:"):
            dsl_code = orm.storage_path[len("inline:") :]
            svg_path = None
            if dsl_code == level_str:
                dsl_code = "DSL Code Omitted"

        return DiagramOutput(
            paper_id=orm.paper_id,
            diagram_type=DiagramType(level_str),
            dsl_code=dsl_code,
            svg_path=svg_path,
        )

    @staticmethod
    def parse_report(orm: OutputORM) -> ReportOutput:
        """Parse an OutputORM record into a ReportOutput."""
        return ReportOutput(
            paper_id=orm.paper_id,
            markdown_path=orm.storage_path or "",
        )

    @staticmethod
    def parse_code(orms: list[OutputORM]) -> CodeOutput | None:
        """Parse a list of OutputORM records into a single CodeOutput."""
        if not orms:
            return None

        python_path = None
        notebook_path = None
        paper_id = orms[0].paper_id

        for orm in orms:
            if orm.output_type == "code_python":
                python_path = orm.storage_path
            elif orm.output_type == "code_notebook":
                notebook_path = orm.storage_path

        return CodeOutput(
            paper_id=paper_id,
            python_path=python_path,
            notebook_path=notebook_path,
            synthetic_data_description=None,
        )


def stage_orm_to_pydantic(orm: StageResultORM) -> StageResult:
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


def run_orm_to_pydantic(orm: PipelineRunORM) -> PipelineRun:
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
            run.stages[s.stage_name] = stage_orm_to_pydantic(s)
    return run
