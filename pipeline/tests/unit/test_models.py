"""
tests/unit/test_models.py

Unit tests for pipeline/models/

Tests verify:
- Enum members have correct string values
- Default factories produce unique / sensible values
- Field-level validators reject bad input
- Cross-field validators in PaperCreate enforce mutual exclusion
- Computed properties (duration_seconds, is_complete) behave correctly
- Helper methods (add_stage, update_total_tokens, get_summary, get_diagram)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from pipeline.models.extraction import (
    AiMlExtraction,
    ArchitectureComponent,
    DatasetInfo,
    ExtractionResult,
    MetricResult,
)
from pipeline.models.output import (
    CodeOutput,
    DiagramOutput,
    DiagramType,
    OutputBundle,
    ReportOutput,
    SummaryLevel,
    SummaryOutput,
)
from pipeline.models.paper import (
    Paper,
    PaperCreate,
    PaperMetadata,
    PaperSource,
)
from pipeline.models.run import (
    PipelineRun,
    RunStatus,
    StageResult,
    StageStatus,
)


# ===========================================================================
# paper.py
# ===========================================================================


class TestPaperSourceEnum:
    def test_values(self):
        assert PaperSource.PDF_UPLOAD == "pdf_upload"
        assert PaperSource.ARXIV_URL == "arxiv_url"
        assert PaperSource.DOI == "doi"

    def test_is_str_subclass(self):
        assert isinstance(PaperSource.PDF_UPLOAD, str)


class TestPaperMetadata:
    def test_minimal_valid(self):
        m = PaperMetadata(title="Attention Is All You Need")
        assert m.title == "Attention Is All You Need"
        assert m.authors == []
        assert m.year is None

    def test_full_fields(self):
        m = PaperMetadata(
            title="BERT",
            authors=["Devlin", "Chang"],
            abstract="We introduce BERT.",
            venue="NAACL",
            year=2019,
            arxiv_id="1810.04805",
            doi="10.18653/v1/N19-1423",
            page_count=16,
            domain="NLP",
            sub_domain="Language Modelling",
        )
        assert m.year == 2019
        assert len(m.authors) == 2

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError, match="title"):
            PaperMetadata(title="")

    def test_invalid_arxiv_id(self):
        with pytest.raises(ValidationError, match="arxiv_id"):
            PaperMetadata(title="T", arxiv_id="not-an-id")

    def test_valid_arxiv_id_with_version(self):
        m = PaperMetadata(title="T", arxiv_id="2301.00001v3")
        assert m.arxiv_id == "2301.00001v3"

    def test_year_bounds(self):
        with pytest.raises(ValidationError):
            PaperMetadata(title="T", year=1800)
        with pytest.raises(ValidationError):
            PaperMetadata(title="T", year=2200)

    def test_page_count_must_be_positive(self):
        with pytest.raises(ValidationError):
            PaperMetadata(title="T", page_count=0)


class TestPaper:
    def test_default_id_is_uuid(self):
        p = Paper(source=PaperSource.PDF_UPLOAD, pdf_storage_path="papers/foo.pdf")
        assert isinstance(p.id, uuid.UUID)

    def test_two_papers_have_different_ids(self):
        p1 = Paper(source=PaperSource.PDF_UPLOAD)
        p2 = Paper(source=PaperSource.PDF_UPLOAD)
        assert p1.id != p2.id

    def test_created_at_is_utc(self):
        p = Paper(source=PaperSource.PDF_UPLOAD)
        assert p.created_at.tzinfo is not None

    def test_custom_id_accepted(self):
        fixed = uuid.UUID("12345678-1234-5678-1234-567812345678")
        p = Paper(id=fixed, source=PaperSource.PDF_UPLOAD)
        assert p.id == fixed

    def test_metadata_optional(self):
        p = Paper(source=PaperSource.PDF_UPLOAD)
        assert p.metadata is None


class TestPaperCreate:
    def test_arxiv_requires_url(self):
        with pytest.raises(ValidationError, match="source_url"):
            PaperCreate(source=PaperSource.ARXIV_URL)

    def test_doi_requires_url(self):
        with pytest.raises(ValidationError, match="source_url"):
            PaperCreate(source=PaperSource.DOI)

    def test_pdf_upload_requires_path(self):
        with pytest.raises(ValidationError, match="pdf_file_path"):
            PaperCreate(source=PaperSource.PDF_UPLOAD)

    def test_arxiv_with_url_valid(self):
        pc = PaperCreate(
            source=PaperSource.ARXIV_URL,
            source_url="https://arxiv.org/abs/2301.00001",
        )
        assert pc.source == PaperSource.ARXIV_URL

    def test_pdf_with_path_valid(self):
        pc = PaperCreate(
            source=PaperSource.PDF_UPLOAD,
            pdf_file_path="/tmp/paper.pdf",
        )
        assert pc.pdf_file_path == "/tmp/paper.pdf"

    def test_title_hint_optional(self):
        pc = PaperCreate(
            source=PaperSource.ARXIV_URL,
            source_url="https://arxiv.org/abs/2301.00001",
            title_hint="My Paper",
        )
        assert pc.title_hint == "My Paper"


# ===========================================================================
# run.py
# ===========================================================================


class TestRunStatusEnum:
    def test_values(self):
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.PARTIAL == "partial"


class TestStageStatusEnum:
    def test_values(self):
        assert StageStatus.PENDING == "pending"
        assert StageStatus.RUNNING == "running"
        assert StageStatus.COMPLETED == "completed"
        assert StageStatus.FAILED == "failed"
        assert StageStatus.SKIPPED == "skipped"
        assert StageStatus.CACHED == "cached"


class TestStageResult:
    def test_defaults(self):
        sr = StageResult(stage_name="ingestion")
        assert sr.status == StageStatus.PENDING
        assert sr.cached is False
        assert sr.token_count is None
        assert sr.error_message is None

    def test_duration_none_without_timestamps(self):
        sr = StageResult(stage_name="ingestion")
        assert sr.duration_seconds is None

    def test_duration_none_if_only_started(self):
        sr = StageResult(
            stage_name="ingestion",
            started_at=datetime.now(timezone.utc),
        )
        assert sr.duration_seconds is None

    def test_duration_computed_correctly(self):
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=42)
        sr = StageResult(
            stage_name="extraction",
            started_at=start,
            completed_at=end,
        )
        assert sr.duration_seconds == pytest.approx(42.0)

    def test_token_count_non_negative(self):
        with pytest.raises(ValidationError):
            StageResult(stage_name="x", token_count=-1)


class TestPipelineRun:
    def _make_run(self) -> PipelineRun:
        return PipelineRun(paper_id=uuid.uuid4())

    def test_default_status_is_pending(self):
        run = self._make_run()
        assert run.status == RunStatus.PENDING

    def test_stages_empty_by_default(self):
        run = self._make_run()
        assert run.stages == {}

    def test_total_tokens_zero_by_default(self):
        run = self._make_run()
        assert run.total_tokens == 0

    def test_add_stage_stores_result(self):
        run = self._make_run()
        sr = run.add_stage("ingestion")
        assert "ingestion" in run.stages
        assert run.stages["ingestion"] is sr
        assert sr.status == StageStatus.PENDING

    def test_add_stage_returns_stage_result(self):
        run = self._make_run()
        result = run.add_stage("extraction")
        assert isinstance(result, StageResult)

    def test_update_total_tokens_sums_all_stages(self):
        run = self._make_run()
        run.add_stage("a").token_count = 100
        run.add_stage("b").token_count = 250
        run.add_stage("c")  # no token count
        run.update_total_tokens()
        assert run.total_tokens == 350

    def test_update_total_tokens_ignores_none(self):
        run = self._make_run()
        run.add_stage("only")  # token_count stays None
        run.update_total_tokens()
        assert run.total_tokens == 0

    def test_unique_ids_per_run(self):
        r1 = self._make_run()
        r2 = self._make_run()
        assert r1.id != r2.id


# ===========================================================================
# extraction.py
# ===========================================================================


class TestArchitectureComponent:
    def test_minimal_valid(self):
        ac = ArchitectureComponent(
            name="Encoder",
            type="transformer",
            description="Encodes input tokens.",
        )
        assert ac.inputs == []
        assert ac.outputs == []

    def test_inputs_outputs_stored(self):
        ac = ArchitectureComponent(
            name="Decoder",
            type="transformer",
            description="Generates output.",
            inputs=["encoder_output", "target_embeddings"],
            outputs=["logits"],
        )
        assert "logits" in ac.outputs


class TestDatasetInfo:
    def test_minimal(self):
        d = DatasetInfo(name="ImageNet")
        assert d.size is None
        assert d.modality is None
        assert d.split_info is None

    def test_full(self):
        d = DatasetInfo(
            name="COCO",
            size="330k images",
            modality="image",
            split_info="118k train / 5k val / 41k test",
        )
        assert d.name == "COCO"


class TestMetricResult:
    def test_valid(self):
        m = MetricResult(
            metric_name="Top-1 Accuracy",
            value="84.2%",
            baseline_comparison="+ 1.3% vs ResNet-50",
        )
        assert m.metric_name == "Top-1 Accuracy"

    def test_value_is_string(self):
        # value must remain a string, not be coerced to float
        m = MetricResult(metric_name="FID", value="2.93")
        assert isinstance(m.value, str)

    def test_baseline_comparison_optional(self):
        m = MetricResult(metric_name="BLEU", value="32.4")
        assert m.baseline_comparison is None


class TestAiMlExtraction:
    def test_all_fields_optional(self):
        # An empty extraction must be valid
        ex = AiMlExtraction()
        assert ex.task is None
        assert ex.key_contributions == []
        assert ex.architecture_components == []
        assert ex.datasets == []
        assert ex.evaluation_metrics == []

    def test_stores_components(self):
        ex = AiMlExtraction(
            task="image classification",
            architecture_components=[
                ArchitectureComponent(
                    name="Patch Embedder",
                    type="linear",
                    description="Splits image into patches.",
                )
            ],
        )
        assert len(ex.architecture_components) == 1
        assert ex.architecture_components[0].name == "Patch Embedder"


class TestExtractionResult:
    def _make(self) -> ExtractionResult:
        return ExtractionResult(
            paper_id=uuid.uuid4(),
            extraction=AiMlExtraction(task="NMT"),
        )

    def test_schema_version_default(self):
        er = self._make()
        assert er.schema_version == "1.0"

    def test_confidence_score_default_zero(self):
        er = self._make()
        assert er.confidence_score == 0.0

    def test_confidence_score_bounds(self):
        with pytest.raises(ValidationError):
            ExtractionResult(
                paper_id=uuid.uuid4(),
                extraction=AiMlExtraction(),
                confidence_score=1.5,
            )
        with pytest.raises(ValidationError):
            ExtractionResult(
                paper_id=uuid.uuid4(),
                extraction=AiMlExtraction(),
                confidence_score=-0.1,
            )

    def test_extracted_at_is_utc(self):
        er = self._make()
        assert er.extracted_at.tzinfo is not None


# ===========================================================================
# output.py
# ===========================================================================


class TestSummaryLevelEnum:
    def test_values(self):
        assert SummaryLevel.PARAGRAPH == "paragraph"
        assert SummaryLevel.SECTION_BY_SECTION == "section_by_section"
        assert SummaryLevel.BULLETS == "bullets"
        assert SummaryLevel.ELI5 == "eli5"


class TestDiagramTypeEnum:
    def test_values(self):
        assert DiagramType.ARCHITECTURE == "architecture"
        assert DiagramType.TRAINING_FLOW == "training_flow"
        assert DiagramType.INFERENCE_FLOW == "inference_flow"


class TestSummaryOutput:
    def test_valid(self):
        pid = uuid.uuid4()
        s = SummaryOutput(
            paper_id=pid,
            level=SummaryLevel.BULLETS,
            content="- Contribution A\n- Contribution B",
        )
        assert s.paper_id == pid
        assert s.level == SummaryLevel.BULLETS

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            SummaryOutput(
                paper_id=uuid.uuid4(),
                level=SummaryLevel.ELI5,
                content="",
            )

    def test_created_at_utc(self):
        s = SummaryOutput(
            paper_id=uuid.uuid4(),
            level=SummaryLevel.PARAGRAPH,
            content="Summary text.",
        )
        assert s.created_at.tzinfo is not None


class TestDiagramOutput:
    def test_valid_mermaid(self):
        d = DiagramOutput(
            paper_id=uuid.uuid4(),
            diagram_type=DiagramType.ARCHITECTURE,
            dsl_code="graph TD\n  A --> B",
        )
        assert d.dsl_language == "mermaid"
        assert d.svg_path is None

    def test_d2_language_accepted(self):
        d = DiagramOutput(
            paper_id=uuid.uuid4(),
            diagram_type=DiagramType.TRAINING_FLOW,
            dsl_code="direction: right\nA -> B",
            dsl_language="d2",
        )
        assert d.dsl_language == "d2"

    def test_invalid_language_rejected(self):
        with pytest.raises(ValidationError):
            DiagramOutput(
                paper_id=uuid.uuid4(),
                diagram_type=DiagramType.INFERENCE_FLOW,
                dsl_code="...",
                dsl_language="plantuml",
            )

    def test_empty_dsl_rejected(self):
        with pytest.raises(ValidationError):
            DiagramOutput(
                paper_id=uuid.uuid4(),
                diagram_type=DiagramType.ARCHITECTURE,
                dsl_code="",
            )


class TestCodeOutput:
    def test_all_paths_optional(self):
        c = CodeOutput(paper_id=uuid.uuid4())
        assert c.python_path is None
        assert c.notebook_path is None
        assert c.synthetic_data_description is None


class TestReportOutput:
    def test_valid(self):
        r = ReportOutput(
            paper_id=uuid.uuid4(),
            markdown_path="outputs/report.md",
        )
        assert r.markdown_path == "outputs/report.md"

    def test_empty_path_rejected(self):
        with pytest.raises(ValidationError):
            ReportOutput(paper_id=uuid.uuid4(), markdown_path="")


class TestOutputBundle:
    def _pid(self) -> uuid.UUID:
        return uuid.uuid4()

    def test_empty_bundle_is_incomplete(self):
        b = OutputBundle(paper_id=self._pid())
        assert b.is_complete is False

    def test_is_complete_requires_all_parts(self):
        pid = self._pid()
        b = OutputBundle(
            paper_id=pid,
            summaries=[
                SummaryOutput(
                    paper_id=pid,
                    level=SummaryLevel.BULLETS,
                    content="bullets",
                )
            ],
            diagrams=[
                DiagramOutput(
                    paper_id=pid,
                    diagram_type=DiagramType.ARCHITECTURE,
                    dsl_code="graph TD\n A-->B",
                )
            ],
            code=CodeOutput(paper_id=pid),
            report=ReportOutput(paper_id=pid, markdown_path="out/report.md"),
        )
        assert b.is_complete is True

    def test_get_summary_returns_matching_level(self):
        pid = self._pid()
        bullets = SummaryOutput(
            paper_id=pid,
            level=SummaryLevel.BULLETS,
            content="one\ntwo",
        )
        eli5 = SummaryOutput(
            paper_id=pid,
            level=SummaryLevel.ELI5,
            content="like five",
        )
        b = OutputBundle(paper_id=pid, summaries=[bullets, eli5])
        assert b.get_summary(SummaryLevel.BULLETS) is bullets
        assert b.get_summary(SummaryLevel.ELI5) is eli5

    def test_get_summary_returns_none_for_missing_level(self):
        pid = self._pid()
        b = OutputBundle(paper_id=pid)
        assert b.get_summary(SummaryLevel.PARAGRAPH) is None

    def test_get_diagram_returns_matching_type(self):
        pid = self._pid()
        arch = DiagramOutput(
            paper_id=pid,
            diagram_type=DiagramType.ARCHITECTURE,
            dsl_code="graph TD\n A-->B",
        )
        b = OutputBundle(paper_id=pid, diagrams=[arch])
        assert b.get_diagram(DiagramType.ARCHITECTURE) is arch
        assert b.get_diagram(DiagramType.TRAINING_FLOW) is None

    def test_summaries_and_diagrams_default_empty(self):
        b = OutputBundle(paper_id=self._pid())
        assert b.summaries == []
        assert b.diagrams == []
