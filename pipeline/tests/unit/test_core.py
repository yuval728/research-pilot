"""
tests/unit/test_core.py
~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for pipeline/core/ — config, exceptions, and state helpers.

Covers
------
* core/exceptions.py  — exception hierarchy, attribute storage, context dicts
* core/config.py      — settings defaults and singleton cache behaviour
* graph/state.py      — make_initial_state defaults and ``extra`` merge
"""

from __future__ import annotations

import uuid
from unittest.mock import patch


from pipeline.core.exceptions import (
    DependencyNotMetError,
    DuplicatePaperError,
    EmbeddingError,
    FileNotFoundError,
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
from pipeline.graph.state import make_initial_state


# ===========================================================================
# core/exceptions.py
# ===========================================================================


class TestResearchPilotError:
    """Root exception base class."""

    def test_message_stored(self):
        exc = ResearchPilotError("something went wrong")
        assert exc.message == "something went wrong"
        assert str(exc) == "something went wrong"

    def test_context_stored(self):
        exc = ResearchPilotError("oops", stage="extract", run_id="abc")
        assert exc.context["stage"] == "extract"
        assert exc.context["run_id"] == "abc"

    def test_empty_context_by_default(self):
        exc = ResearchPilotError("msg")
        assert exc.context == {}

    def test_is_exception_subclass(self):
        assert issubclass(ResearchPilotError, Exception)


class TestPipelineErrorHierarchy:
    def test_pipeline_error_is_research_pilot_error(self):
        assert issubclass(PipelineError, ResearchPilotError)

    def test_stage_error_attributes(self):
        inner = ValueError("inner cause")
        exc = StageError(
            "extraction failed",
            stage_name="extract",
            run_id="run-123",
            cause=inner,
        )
        assert exc.stage_name == "extract"
        assert exc.run_id == "run-123"
        assert exc.cause is inner
        assert exc.message == "extraction failed"

    def test_stage_error_cause_optional(self):
        exc = StageError("failed", stage_name="ingest", run_id="run-0")
        assert exc.cause is None

    def test_dependency_not_met_attributes(self):
        exc = DependencyNotMetError(
            "missing upstream",
            stage_name="extract",
            missing_dependency="classify",
        )
        assert exc.stage_name == "extract"
        assert exc.missing_dependency == "classify"

    def test_stage_error_is_pipeline_error(self):
        assert issubclass(StageError, PipelineError)

    def test_dependency_not_met_is_pipeline_error(self):
        assert issubclass(DependencyNotMetError, PipelineError)


class TestIngestionErrors:
    def test_ingestion_error_hierarchy(self):
        assert issubclass(IngestionError, ResearchPilotError)
        assert issubclass(PDFFetchError, IngestionError)
        assert issubclass(DuplicatePaperError, IngestionError)

    def test_pdf_fetch_error_attributes(self):
        exc = PDFFetchError(
            "timeout", source_url="https://arxiv.org/abs/1234", status_code=504
        )
        assert exc.source_url == "https://arxiv.org/abs/1234"
        assert exc.status_code == 504
        assert exc.message == "timeout"

    def test_pdf_fetch_error_status_code_optional(self):
        exc = PDFFetchError("no status", source_url="http://example.com")
        assert exc.status_code is None

    def test_duplicate_paper_error_attributes(self):
        exc = DuplicatePaperError(
            "already ingested",
            identifier="1706.03762",
            identifier_type="arxiv_id",
        )
        assert exc.identifier == "1706.03762"
        assert exc.identifier_type == "arxiv_id"


class TestLLMErrors:
    def test_hierarchy(self):
        assert issubclass(LLMError, ResearchPilotError)
        assert issubclass(LLMRateLimitError, LLMError)
        assert issubclass(LLMValidationError, LLMError)
        assert issubclass(LLMTimeoutError, LLMError)
        assert issubclass(TokenBudgetExceededError, LLMError)

    def test_rate_limit_attributes(self):
        exc = LLMRateLimitError("rate limited", model="gemini/flash", retry_after=30.0)
        assert exc.model == "gemini/flash"
        assert exc.retry_after == 30.0

    def test_rate_limit_retry_after_optional(self):
        exc = LLMRateLimitError("rate limited", model="gemini/flash")
        assert exc.retry_after is None

    def test_validation_error_attributes(self):
        exc = LLMValidationError(
            "parse failed",
            raw_output='{"bad": "json"',
            schema_name="AiMlExtraction",
            attempts=3,
        )
        assert exc.raw_output == '{"bad": "json"'
        assert exc.schema_name == "AiMlExtraction"
        assert exc.attempts == 3

    def test_timeout_error_attributes(self):
        exc = LLMTimeoutError("timed out", model="gemini/flash", timeout_seconds=120.0)
        assert exc.model == "gemini/flash"
        assert exc.timeout_seconds == 120.0

    def test_token_budget_exceeded_attributes(self):
        exc = TokenBudgetExceededError(
            "budget exceeded",
            budget=500_000,
            actual=512_000,
            stage_name="extract",
        )
        assert exc.budget == 500_000
        assert exc.actual == 512_000
        assert exc.stage_name == "extract"


class TestStorageErrors:
    def test_hierarchy(self):
        assert issubclass(StorageError, ResearchPilotError)
        assert issubclass(FileUploadError, StorageError)
        assert issubclass(FileNotFoundError, StorageError)

    def test_file_upload_error_attributes(self):
        inner = ConnectionError("network error")
        exc = FileUploadError(
            "upload failed",
            bucket="papers",
            path="papers/foo.pdf",
            cause=inner,
        )
        assert exc.bucket == "papers"
        assert exc.path == "papers/foo.pdf"
        assert exc.cause is inner

    def test_file_not_found_attributes(self):
        exc = FileNotFoundError("not found", bucket="outputs", path="outputs/report.md")
        assert exc.bucket == "outputs"
        assert exc.path == "outputs/report.md"


class TestEmbeddingError:
    def test_attributes(self):
        inner = RuntimeError("embed failed")
        exc = EmbeddingError("embedding error", model="text-embedding-004", cause=inner)
        assert exc.model == "text-embedding-004"
        assert exc.cause is inner

    def test_cause_optional(self):
        exc = EmbeddingError("error", model="text-embedding-004")
        assert exc.cause is None

    def test_is_research_pilot_error(self):
        assert issubclass(EmbeddingError, ResearchPilotError)


class TestMROLookup:
    """_http_status_for in main.py walks MRO — verify exc hierarchy is correct."""

    def test_stage_error_mro_contains_pipeline_error(self):
        mro = type(StageError("m", stage_name="s", run_id="r")).__mro__
        assert PipelineError in mro
        assert ResearchPilotError in mro

    def test_llm_rate_limit_mro_contains_llm_error(self):
        mro = type(LLMRateLimitError("m", model="g")).__mro__
        assert LLMError in mro
        assert ResearchPilotError in mro


# ===========================================================================
# graph/state.py — make_initial_state
# ===========================================================================


class TestMakeInitialState:
    """Tests for the state factory function."""

    def test_run_id_auto_generated_when_absent(self):
        s = make_initial_state()
        assert isinstance(s["run_id"], str)
        # Must be a valid UUID string
        uuid.UUID(s["run_id"])

    def test_explicit_run_id_preserved(self):
        run_id = "deadbeef-dead-beef-dead-beefdeadbeef"
        s = make_initial_state(run_id=run_id)
        assert s["run_id"] == run_id

    def test_two_calls_produce_different_run_ids(self):
        s1 = make_initial_state()
        s2 = make_initial_state()
        assert s1["run_id"] != s2["run_id"]

    def test_all_required_keys_present(self):
        s = make_initial_state()
        required = {
            "run_id",
            "paper_id",
            "pdf_storage_path",
            "pdf_bytes",
            "paper_metadata",
            "domain",
            "sub_domain",
            "classification_confidence",
            "extraction",
            "summaries",
            "diagrams",
            "code_output",
            "report_path",
            "stage_statuses",
            "errors",
            "token_usage",
            "cached_stages",
        }
        assert required.issubset(set(s.keys()))

    def test_default_numeric_and_collection_values(self):
        s = make_initial_state()
        assert s["classification_confidence"] == 0.0
        assert s["summaries"] == []
        assert s["diagrams"] == []
        assert s["errors"] == []
        assert s["stage_statuses"] == {}
        assert s["token_usage"] == {}
        assert s["cached_stages"] == set()

    def test_default_nullable_fields_are_none(self):
        s = make_initial_state()
        assert s["paper_id"] is None
        assert s["pdf_storage_path"] is None
        assert s["pdf_bytes"] is None
        assert s["paper_metadata"] is None
        assert s["domain"] is None
        assert s["sub_domain"] is None
        assert s["extraction"] is None
        assert s["code_output"] is None
        assert s["report_path"] is None

    def test_pdf_bytes_injected(self):
        data = b"%PDF-test"
        s = make_initial_state(pdf_bytes=data)
        assert s["pdf_bytes"] is data

    def test_extra_values_merged(self):
        s = make_initial_state(extra={"paper_id": "paper-123", "domain": "NLP"})
        assert s["paper_id"] == "paper-123"
        assert s["domain"] == "NLP"

    def test_extra_none_does_not_error(self):
        s = make_initial_state(extra=None)
        assert s["run_id"]  # state is valid

    def test_paper_metadata_passed_through(self):
        from pipeline.models.paper import PaperMetadata  # noqa: PLC0415

        meta = PaperMetadata(title="Test Paper")
        s = make_initial_state(paper_metadata=meta)
        assert s["paper_metadata"] is meta


# ===========================================================================
# core/config.py — basic settings validation
# ===========================================================================


class TestConfigSettings:
    """Verify settings factory and singleton cache work correctly."""

    def test_get_settings_returns_same_object(self):
        from pipeline.core.config import get_settings  # noqa: PLC0415

        get_settings.cache_clear()
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "fake-key",
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_DB_URL": "postgresql+asyncpg://u:p@localhost/db",
                "SUPABASE_ANON_KEY": "anon",
                "SUPABASE_SERVICE_ROLE_KEY": "service",
                "LANGFUSE_PUBLIC_KEY": "lf-pub",
                "LANGFUSE_SECRET_KEY": "lf-sec",
            },
            clear=False,
        ):
            s1 = get_settings()
            s2 = get_settings()
            assert s1 is s2

        get_settings.cache_clear()

    def test_cache_clear_produces_new_object(self):
        from pipeline.core.config import get_settings  # noqa: PLC0415

        get_settings.cache_clear()
        env = {
            "GEMINI_API_KEY": "key1",
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_DB_URL": "postgresql+asyncpg://u:p@localhost/db",
            "SUPABASE_ANON_KEY": "anon",
            "SUPABASE_SERVICE_ROLE_KEY": "service",
            "LANGFUSE_PUBLIC_KEY": "lf-pub",
            "LANGFUSE_SECRET_KEY": "lf-sec",
        }
        with patch.dict("os.environ", env, clear=False):
            s1 = get_settings()
            get_settings.cache_clear()
            s2 = get_settings()
            # Different objects after cache clear
            assert s1 is not s2

        get_settings.cache_clear()

    def test_environment_default_is_development(self):
        from pipeline.core.config import get_settings  # noqa: PLC0415

        get_settings.cache_clear()
        env = {
            "GEMINI_API_KEY": "k",
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_DB_URL": "postgresql+asyncpg://u:p@localhost/db",
            "SUPABASE_ANON_KEY": "anon",
            "SUPABASE_SERVICE_ROLE_KEY": "svc",
            "LANGFUSE_PUBLIC_KEY": "pub",
            "LANGFUSE_SECRET_KEY": "sec",
        }
        with patch.dict("os.environ", env, clear=False):
            s = get_settings()
            assert s.environment in ("development", "staging", "production")

        get_settings.cache_clear()
