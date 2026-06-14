"""
tests/unit/test_services.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for pipeline/services/ — PaperService, PipelineService,
ExportService. All external I/O (DB, Supabase, arxiv, httpx, LiteLLM) is
mocked so no network or database connection is required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.paper import Paper, PaperListItem
from src.models.run import PipelineRun, StageResult, StageStatus


# ---------------------------------------------------------------------------
# Fixtures — lightweight ORM stand-ins
# ---------------------------------------------------------------------------


def _paper_orm(
    paper_id: uuid.UUID | None = None,
    source: str = "arxiv_url",
    source_url: str | None = "https://arxiv.org/abs/1706.03762",
    pdf_storage_path: str | None = None,
    metadata_: Any | None = None,
) -> MagicMock:
    orm = MagicMock()
    orm.id = paper_id or uuid.uuid4()
    orm.source = source
    orm.source_url = source_url
    orm.pdf_storage_path = pdf_storage_path
    orm.metadata_ = (
        metadata_
        if metadata_ is not None
        else {
            "title": "Test Paper",
            "authors": [],
            "abstract": None,
            "venue": None,
            "year": 2024,
            "arxiv_id": None,
            "doi": None,
            "page_count": None,
            "domain": None,
            "sub_domain": None,
        }
    )
    orm.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    orm.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return orm


def _run_orm(
    run_id: uuid.UUID | None = None,
    paper_id: uuid.UUID | None = None,
    status: str = "pending",
) -> MagicMock:
    orm = MagicMock()
    orm.id = run_id or uuid.uuid4()
    orm.paper_id = paper_id or uuid.uuid4()
    orm.status = status
    orm.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    orm.completed_at = None
    orm.total_tokens = 0
    orm.error = None
    orm.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    orm.stages = []
    orm.pdf_storage_path = None
    return orm


def _make_db(
    *,
    get_return=None,
    execute_return=None,
) -> AsyncMock:
    """Create an AsyncMock session."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=get_return)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    result_mock = MagicMock()
    result_data = execute_return if execute_return is not None else get_return
    if isinstance(result_data, list):
        result_mock.scalars.return_value.first.return_value = (
            result_data[0] if result_data else None
        )
        result_mock.scalars.return_value.all.return_value = result_data
        result_mock.scalar_one_or_none.return_value = (
            result_data[0] if result_data else None
        )
    else:
        result_mock.scalars.return_value.first.return_value = result_data
        result_mock.scalars.return_value.all.return_value = (
            [] if result_data is None else [result_data]
        )
        result_mock.scalar_one_or_none.return_value = result_data
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ===========================================================================
# PaperService
# ===========================================================================


class TestPaperServiceCreateFromUpload:
    @pytest.mark.asyncio
    async def test_valid_pdf_creates_record(self, pdf_bytes):
        paper_orm = _paper_orm(source="pdf_upload", source_url=None)
        db = _make_db(get_return=None)
        db.refresh = AsyncMock(side_effect=lambda o: None)

        with (
            patch("src.services.paper_service.get_settings") as mock_cfg,
            patch("src.services.paper_service._get_supabase") as mock_sup,
            patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_thread,
        ):
            mock_cfg.return_value = _fake_settings()
            mock_sup.return_value = MagicMock()
            mock_thread.return_value = None  # upload succeeded

            # After commit + refresh, db.get returns the ORM
            db.get = AsyncMock(return_value=paper_orm)

            # Simulate _ingest: patch PaperORM constructor and db.commit
            with patch("src.services.paper_service.PaperORM", return_value=paper_orm):
                from src.services.paper_service import PaperService  # noqa: PLC0415

                svc = PaperService(db)
                paper = await svc.create_from_upload(pdf_bytes, "paper.pdf")

        assert isinstance(paper, Paper)

    @pytest.mark.asyncio
    async def test_non_pdf_filename_raises(self, pdf_bytes):
        from src.services.paper_service import PaperService  # noqa: PLC0415

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            db = _make_db()
            svc = PaperService(db)
            with pytest.raises(ValueError, match="PDF"):
                await svc.create_from_upload(pdf_bytes, "document.docx")

    @pytest.mark.asyncio
    async def test_empty_bytes_raises(self):
        from src.services.paper_service import PaperService  # noqa: PLC0415

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            db = _make_db()
            svc = PaperService(db)
            with pytest.raises(ValueError, match="empty"):
                await svc.create_from_upload(b"", "paper.pdf")


class TestPaperServiceGetPaper:
    @pytest.mark.asyncio
    async def test_found_returns_paper(self):
        paper_id = uuid.uuid4()
        orm = _paper_orm(paper_id=paper_id)
        db = _make_db(get_return=orm)

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            paper = await svc.get_paper(paper_id)

        assert paper.id == orm.id
        assert isinstance(paper, Paper)

    @pytest.mark.asyncio
    async def test_malformed_metadata_does_not_break_paper_conversion(self):
        paper_id = uuid.uuid4()
        orm = _paper_orm(paper_id=paper_id, metadata_=["not", "an", "object"])
        db = _make_db(get_return=orm)

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            paper = await svc.get_paper(paper_id)

        assert paper.id == orm.id
        assert paper.metadata is None

    @pytest.mark.asyncio
    async def test_json_string_metadata_is_recovered(self):
        paper_id = uuid.uuid4()
        orm = _paper_orm(paper_id=paper_id, metadata_='{"title": "Recovered"}')
        db = _make_db(get_return=orm)

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            paper = await svc.get_paper(paper_id)

        assert paper.metadata is not None
        assert paper.metadata.title == "Recovered"

    @pytest.mark.asyncio
    async def test_not_found_raises_value_error(self):
        db = _make_db(get_return=None)

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            with pytest.raises(ValueError, match="not found"):
                await svc.get_paper(uuid.uuid4())


class TestPaperServiceListPapers:
    @pytest.mark.asyncio
    async def test_returns_list_of_papers(self):
        orm1 = _paper_orm()
        orm2 = _paper_orm()
        papers_result_mock = MagicMock()
        papers_result_mock.scalars.return_value.all.return_value = [orm1, orm2]
        runs_result_mock = MagicMock()
        runs_result_mock.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[papers_result_mock, runs_result_mock])

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            papers = await svc.list_papers()

        assert len(papers) == 2
        assert all(isinstance(p, PaperListItem) for p in papers)
        assert all(isinstance(p.paper, Paper) for p in papers)

    @pytest.mark.asyncio
    async def test_empty_result(self):
        papers_result_mock = MagicMock()
        papers_result_mock.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=papers_result_mock)

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            papers = await svc.list_papers()

        assert papers == []


class TestPaperServiceDeletePaper:
    @pytest.mark.asyncio
    async def test_delete_calls_db_delete(self):
        paper_id = uuid.uuid4()
        orm = _paper_orm(paper_id=paper_id)
        db = _make_db(get_return=orm)

        with (
            patch(
                "src.services.paper_service.get_settings",
                return_value=_fake_settings(),
            ),
            patch("anyio.to_thread.run_sync", new_callable=AsyncMock),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            svc._supabase = MagicMock()  # skip lazy init
            await svc.delete_paper(paper_id)

        db.delete.assert_called_once_with(orm)
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_missing_paper_is_noop(self):
        db = _make_db(get_return=None)

        with patch(
            "src.services.paper_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.paper_service import PaperService  # noqa: PLC0415

            svc = PaperService(db)
            # Should not raise
            await svc.delete_paper(uuid.uuid4())

        db.delete.assert_not_called()


# ===========================================================================
# PipelineService
# ===========================================================================


class TestPipelineServiceTriggerRun:
    @pytest.mark.asyncio
    async def test_trigger_run_returns_pipeline_run(self):
        paper_id = uuid.uuid4()
        paper_orm = _paper_orm(paper_id=paper_id)
        run_orm = _run_orm(paper_id=paper_id)

        db = AsyncMock()
        db.get = AsyncMock(return_value=paper_orm)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        run_result_mock = MagicMock()
        run_result_mock.scalar_one.return_value = run_orm
        db.execute = AsyncMock(return_value=run_result_mock)

        with (
            patch("src.services.pipeline_service.research_pipeline"),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            mock_loop.return_value.create_task = MagicMock()

            from src.services.pipeline_service import PipelineService  # noqa: PLC0415

            svc = PipelineService(db)
            result = await svc.trigger_run(paper_id)

        assert isinstance(result, PipelineRun)
        assert result.paper_id == run_orm.paper_id

    @pytest.mark.asyncio
    async def test_trigger_run_ignores_malformed_metadata(self):
        paper_id = uuid.uuid4()
        paper_orm = _paper_orm(paper_id=paper_id, metadata_=["bad"])
        run_orm = _run_orm(paper_id=paper_id)

        db = AsyncMock()
        db.get = AsyncMock(return_value=paper_orm)
        db.add = MagicMock()
        db.commit = AsyncMock()
        run_result_mock = MagicMock()
        run_result_mock.scalar_one.return_value = run_orm
        db.execute = AsyncMock(return_value=run_result_mock)

        with (
            patch("src.services.pipeline_service.research_pipeline"),
            patch("src.services.pipeline_service.make_initial_state") as mock_state,
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            mock_state.return_value = {"run_id": str(run_orm.id)}
            mock_loop.return_value.create_task = MagicMock()

            from src.services.pipeline_service import PipelineService  # noqa: PLC0415

            svc = PipelineService(db)
            result = await svc.trigger_run(paper_id)

        assert isinstance(result, PipelineRun)
        assert mock_state.call_args.kwargs["paper_metadata"] is None

    @pytest.mark.asyncio
    async def test_trigger_run_paper_not_found_raises(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        from src.services.pipeline_service import PipelineService  # noqa: PLC0415

        svc = PipelineService(db)
        with pytest.raises(ValueError, match="not found"):
            await svc.trigger_run(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_execute_pipeline_run_persists_stage_updates_and_partial_status(self):
        run_id = uuid.uuid4()
        paper_id = uuid.uuid4()
        run_orm = _run_orm(run_id=run_id, paper_id=paper_id, status="pending")
        run_orm.stages = []

        class FakeSession:
            def __init__(self):
                self.run = run_orm

            async def get(self, model, pk, options=None):
                if model.__name__ == "PipelineRunORM" and pk == run_id:
                    return self.run
                return None

            async def execute(self, stmt):
                result = MagicMock()
                result.scalars.return_value.all.return_value = list(self.run.stages)
                return result

            def add(self, stage):
                self.run.stages.append(stage)

            async def commit(self):
                return None

        class FakeContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_astream(_initial_state):
            yield {
                "extract": {
                    "stage_statuses": {
                        "extract": StageStatus.COMPLETED,
                        "diagram": StageStatus.FAILED,
                    },
                    "token_usage": {"extract": 123},
                    "cached_stages": set(),
                    "errors": ["[diagram] renderer failed"],
                }
            }

        fake_session = FakeSession()

        with (
            patch(
                "src.services.pipeline_service.get_db_context",
                side_effect=lambda: FakeContext(fake_session),
            ),
            patch("src.services.pipeline_service.research_pipeline") as mock_pipeline,
        ):
            mock_pipeline.astream = fake_astream

            from src.services.pipeline_service import PipelineService  # noqa: PLC0415

            svc = PipelineService(AsyncMock())
            await svc._execute_pipeline_run(run_id, {"run_id": str(run_id)})

        assert run_orm.status == "partial"
        assert run_orm.total_tokens == 123
        assert run_orm.error == "[diagram] renderer failed"
        assert {stage.stage_name for stage in run_orm.stages} == {"extract", "diagram"}
        extract_stage = next(
            stage for stage in run_orm.stages if stage.stage_name == "extract"
        )
        diagram_stage = next(
            stage for stage in run_orm.stages if stage.stage_name == "diagram"
        )
        assert extract_stage.status == "completed"
        assert extract_stage.token_count == 123
        assert diagram_stage.status == "failed"
        assert diagram_stage.error_message == "[diagram] renderer failed"


class TestPipelineServiceGetRunStatus:
    @pytest.mark.asyncio
    async def test_found_returns_run(self):
        run_id = uuid.uuid4()
        run_orm = _run_orm(run_id=run_id)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = run_orm

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        from src.services.pipeline_service import PipelineService  # noqa: PLC0415

        svc = PipelineService(db)
        run = await svc.get_run_status(run_id)

        assert isinstance(run, PipelineRun)
        assert run.id == run_id

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        from src.services.pipeline_service import PipelineService  # noqa: PLC0415

        svc = PipelineService(db)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_run_status(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_latest_run_for_paper_returns_latest(self):
        paper_id = uuid.uuid4()
        run_orm = _run_orm(paper_id=paper_id, status="completed")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = run_orm
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        from src.services.pipeline_service import PipelineService  # noqa: PLC0415

        svc = PipelineService(db)
        run = await svc.get_latest_run_for_paper(paper_id)

        assert run is not None
        assert run.paper_id == paper_id


class TestPipelineServiceGetStageResult:
    @pytest.mark.asyncio
    async def test_found_returns_stage_result(self):
        run_id = uuid.uuid4()
        stage_orm = MagicMock()
        stage_orm.stage_name = "extract"
        stage_orm.status = "completed"
        stage_orm.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        stage_orm.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        stage_orm.error_message = None
        stage_orm.cached = False
        stage_orm.token_count = 300

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = stage_orm
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        from src.services.pipeline_service import PipelineService  # noqa: PLC0415

        svc = PipelineService(db)
        stage = await svc.get_stage_result(run_id, "extract")

        assert isinstance(stage, StageResult)
        assert stage.stage_name == "extract"
        assert stage.token_count == 300

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        from src.services.pipeline_service import PipelineService  # noqa: PLC0415

        svc = PipelineService(db)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_stage_result(uuid.uuid4(), "nonexistent_stage")


# ===========================================================================
# ExportService
# ===========================================================================


class TestExportServiceGetOutputBundle:
    @pytest.mark.asyncio
    async def test_empty_records_returns_empty_bundle(self):
        paper_id = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        with patch(
            "src.services.export_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.export_service import ExportService  # noqa: PLC0415

            svc = ExportService(db)
            bundle = await svc.get_output_bundle(paper_id)

        assert bundle.paper_id == paper_id
        assert bundle.summaries == []
        assert bundle.diagrams == []
        assert bundle.code is None
        assert bundle.report is None

    @pytest.mark.asyncio
    async def test_report_record_populates_bundle(self):
        paper_id = uuid.uuid4()
        orm = MagicMock()
        orm.paper_id = paper_id
        orm.output_type = "report"
        orm.storage_path = f"outputs/{paper_id}/report.md"

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [orm]
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        with patch(
            "src.services.export_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.export_service import ExportService  # noqa: PLC0415

            svc = ExportService(db)
            bundle = await svc.get_output_bundle(paper_id)

        assert bundle.report is not None
        assert bundle.report.markdown_path == f"outputs/{paper_id}/report.md"

    @pytest.mark.asyncio
    async def test_summary_record_populates_bundle(self):
        paper_id = uuid.uuid4()
        orm = MagicMock()
        orm.paper_id = paper_id
        orm.output_type = "summary_bullets"
        orm.storage_path = "inline:• contribution A\n• contribution B"

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [orm]
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        with patch(
            "src.services.export_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.export_service import ExportService  # noqa: PLC0415

            svc = ExportService(db)
            bundle = await svc.get_output_bundle(paper_id)

        assert len(bundle.summaries) == 1
        assert bundle.summaries[0].level.value == "bullets"

    @pytest.mark.asyncio
    async def test_latest_extraction_populates_bundle(self):
        paper_id = uuid.uuid4()
        outputs_result = MagicMock()
        outputs_result.scalars.return_value.all.return_value = []
        extraction_result = MagicMock()
        extraction_result.scalar_one_or_none.return_value = {
            "task": "classification",
            "problem_statement": "Need better accuracy",
            "key_contributions": [],
            "architecture_components": [],
            "datasets": [],
            "evaluation_metrics": [],
        }
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[outputs_result, extraction_result])

        with patch(
            "src.services.export_service.get_settings",
            return_value=_fake_settings(),
        ):
            from src.services.export_service import ExportService  # noqa: PLC0415

            svc = ExportService(db)
            bundle = await svc.get_output_bundle(paper_id)

        assert bundle.extraction is not None
        assert bundle.extraction.task == "classification"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fake_settings() -> MagicMock:
    settings = MagicMock()
    settings.embedding.model = "llm/text-embedding-004"
    settings.embedding.api_key.get_secret_value.return_value = "test-embedding-key"
    settings.llm.model = "gemini/gemini-2.0-flash"
    settings.llm.api_key.get_secret_value.return_value = "test-key"
    settings.supabase.url = "https://test.supabase.co"
    settings.supabase.papers_bucket = "papers"
    settings.supabase.outputs_bucket = "outputs"
    settings.supabase.service_role_key.get_secret_value.return_value = "svc-key"
    return settings
