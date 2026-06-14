"""
tests/unit/core/test_exceptions.py

Unit tests for pipeline/core/exceptions.py

Tests verify:
- Every exception can be instantiated with required params
- Exception context dict is populated correctly
- Inheritance chain is correct
- __repr__ and message are accessible
"""

import pytest

from src.core.exceptions import (
    DependencyNotMetError,
    DuplicatePaperError,
    EmbeddingError,
    StorageFileNotFoundError,
    FileUploadError,
    IngestionError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMValidationError,
    PDFFetchError,
    PipelineError,
    ResearchPilotError,
    StageError,
    StorageError,
    TokenBudgetExceededError,
)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class TestResearchPilotError:
    def test_message_stored(self):
        err = ResearchPilotError("boom", foo="bar")
        assert err.message == "boom"
        assert err.context == {"foo": "bar"}

    def test_is_exception(self):
        err = ResearchPilotError("x")
        assert isinstance(err, Exception)

    def test_str(self):
        err = ResearchPilotError("hello")
        assert str(err) == "hello"


# ---------------------------------------------------------------------------
# PipelineError hierarchy
# ---------------------------------------------------------------------------


class TestStageError:
    def test_fields(self):
        cause = ValueError("inner")
        err = StageError(
            "stage blew up",
            stage_name="extract",
            run_id="run-001",
            cause=cause,
        )
        assert err.stage_name == "extract"
        assert err.run_id == "run-001"
        assert err.cause is cause

    def test_inheritance(self):
        err = StageError("msg", stage_name="ingest", run_id="r1")
        assert isinstance(err, PipelineError)
        assert isinstance(err, ResearchPilotError)

    def test_no_cause_defaults_none(self):
        err = StageError("msg", stage_name="embed", run_id="r2")
        assert err.cause is None


class TestDependencyNotMetError:
    def test_fields(self):
        err = DependencyNotMetError(
            "missing dep",
            stage_name="summarise",
            missing_dependency="extract",
        )
        assert err.stage_name == "summarise"
        assert err.missing_dependency == "extract"

    def test_inheritance(self):
        err = DependencyNotMetError("m", stage_name="s", missing_dependency="d")
        assert isinstance(err, PipelineError)


# ---------------------------------------------------------------------------
# Ingestion errors
# ---------------------------------------------------------------------------


class TestPDFFetchError:
    def test_fields_with_status_code(self):
        err = PDFFetchError(
            "fetch failed", source_url="https://arxiv.org/pdf/x", status_code=404
        )
        assert err.source_url == "https://arxiv.org/pdf/x"
        assert err.status_code == 404

    def test_status_code_optional(self):
        err = PDFFetchError("timeout", source_url="https://example.com/paper.pdf")
        assert err.status_code is None

    def test_inheritance(self):
        err = PDFFetchError("m", source_url="url")
        assert isinstance(err, IngestionError)
        assert isinstance(err, ResearchPilotError)


class TestDuplicatePaperError:
    def test_fields(self):
        err = DuplicatePaperError(
            "dup", identifier="2301.00001", identifier_type="arxiv_id"
        )
        assert err.identifier == "2301.00001"
        assert err.identifier_type == "arxiv_id"

    def test_inheritance(self):
        err = DuplicatePaperError("m", identifier="x", identifier_type="doi")
        assert isinstance(err, IngestionError)


# ---------------------------------------------------------------------------
# LLM errors
# ---------------------------------------------------------------------------


class TestLLMRateLimitError:
    def test_fields(self):
        err = LLMRateLimitError("rate limit", model="llm/flash", retry_after=5.0)
        assert err.model == "llm/flash"
        assert err.retry_after == 5.0

    def test_retry_after_optional(self):
        err = LLMRateLimitError("rate limit", model="llm/flash")
        assert err.retry_after is None

    def test_inheritance(self):
        err = LLMRateLimitError("m", model="m")
        assert isinstance(err, LLMError)
        assert isinstance(err, ResearchPilotError)


class TestLLMValidationError:
    def test_fields(self):
        err = LLMValidationError(
            "invalid output",
            raw_output='{"bad": "json"}',
            schema_name="ExtractionResult",
            attempts=3,
        )
        assert err.raw_output == '{"bad": "json"}'
        assert err.schema_name == "ExtractionResult"
        assert err.attempts == 3

    def test_inheritance(self):
        err = LLMValidationError("m", raw_output="x", schema_name="S", attempts=1)
        assert isinstance(err, LLMError)


class TestLLMTimeoutError:
    def test_fields(self):
        err = LLMTimeoutError("timeout", model="llm/pro", timeout_seconds=120.0)
        assert err.model == "llm/pro"
        assert err.timeout_seconds == 120.0

    def test_inheritance(self):
        err = LLMTimeoutError("m", model="m", timeout_seconds=10)
        assert isinstance(err, LLMError)


class TestTokenBudgetExceededError:
    def test_fields(self):
        err = TokenBudgetExceededError(
            "over budget",
            budget=500_000,
            actual=600_000,
            stage_name="extract",
        )
        assert err.budget == 500_000
        assert err.actual == 600_000
        assert err.stage_name == "extract"

    def test_inheritance(self):
        err = TokenBudgetExceededError("m", budget=1, actual=2, stage_name="s")
        assert isinstance(err, LLMError)


# ---------------------------------------------------------------------------
# Storage errors
# ---------------------------------------------------------------------------


class TestFileUploadError:
    def test_fields(self):
        cause = IOError("disk full")
        err = FileUploadError(
            "upload failed", bucket="papers", path="a/b.pdf", cause=cause
        )
        assert err.bucket == "papers"
        assert err.path == "a/b.pdf"
        assert err.cause is cause

    def test_inheritance(self):
        err = FileUploadError("m", bucket="b", path="p")
        assert isinstance(err, StorageError)
        assert isinstance(err, ResearchPilotError)


class TestStorageFileNotFoundError:
    def test_fields(self):
        err = StorageFileNotFoundError("not found", bucket="outputs", path="x/y.svg")
        assert err.bucket == "outputs"
        assert err.path == "x/y.svg"

    def test_inheritance(self):
        err = StorageFileNotFoundError("m", bucket="b", path="p")
        assert isinstance(err, StorageError)


# ---------------------------------------------------------------------------
# Embedding errors
# ---------------------------------------------------------------------------


class TestEmbeddingError:
    def test_fields(self):
        cause = RuntimeError("api error")
        err = EmbeddingError("embed failed", model="text-embedding-004", cause=cause)
        assert err.model == "text-embedding-004"
        assert err.cause is cause

    def test_cause_optional(self):
        err = EmbeddingError("embed failed", model="m")
        assert err.cause is None

    def test_inheritance(self):
        err = EmbeddingError("m", model="m")
        assert isinstance(err, ResearchPilotError)


# ---------------------------------------------------------------------------
# catch-by-base-class
# ---------------------------------------------------------------------------


class TestExceptionHierarchyCatchability:
    """Verify exception propagation works as expected with try/except."""

    def test_stage_error_caught_as_pipeline_error(self):
        with pytest.raises(PipelineError):
            raise StageError("msg", stage_name="s", run_id="r")

    def test_pdf_fetch_error_caught_as_research_pilot_error(self):
        with pytest.raises(ResearchPilotError):
            raise PDFFetchError("msg", source_url="url")

    def test_llm_rate_limit_caught_as_llm_error(self):
        with pytest.raises(LLMError):
            raise LLMRateLimitError("msg", model="m")
