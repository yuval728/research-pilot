"""
tests/conftest.py
~~~~~~~~~~~~~~~~~
Shared pytest fixtures for the full test suite.

Fixtures
--------
mock_llm_response   — patches LiteLLM completion so no API calls are made.
test_db             — in-memory SQLite async session (unit tests only).
test_client         — FastAPI TestClient with all heavy dependencies overridden.
sample_paper        — a ready-to-use Paper Pydantic instance.
sample_extraction   — a valid AiMlExtraction instance.
pdf_bytes           — minimal valid PDF bytes (no fixture file needed for unit tests).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set required env vars so module-level get_settings() calls don't fail during imports
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_DB_URL"] = "postgresql+psycopg://u:p@localhost/db"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-svc-key"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["LANGFUSE_PUBLIC_KEY"] = "test-lf-pub"
os.environ["LANGFUSE_SECRET_KEY"] = "test-lf-sec"

from pipeline.domains.ai_ml.schema import (
    AiMlExtraction,
    ArchitectureComponent,
    DatasetInfo,
    MetricResult,
)
from pipeline.models.extraction import ExtractionResult
from pipeline.models.paper import Paper, PaperMetadata, PaperSource

# ---------------------------------------------------------------------------
# pytest-asyncio mode
# ---------------------------------------------------------------------------

pytest_plugins = ["pytest_asyncio"]


# ---------------------------------------------------------------------------
# In-memory SQLite DB (unit tests — no Postgres needed)
# ---------------------------------------------------------------------------

_SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Async SQLite session backed by an in-memory database.

    Tables are created afresh for each test function and dropped on teardown.
    Heavy Postgres-specific types (pgvector) are not tested here.
    """
    engine = create_async_engine(_SQLITE_URL, echo=False)

    # Import ORM Base only inside fixture to avoid top-level DB connection
    from pipeline.db.models import Base  # noqa: PLC0415

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# FastAPI TestClient with all external dependencies stubbed out
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_client() -> Generator[TestClient, None, None]:
    """Return a synchronous FastAPI TestClient with external services mocked.

    Overrides
    ---------
    * ``get_settings`` — returns a minimal AppSettings with fake secrets.
    * ``engine`` (DB)  — replaced so no real DB connection is attempted.
    * ``domain_registry`` — auto_discover is a no-op.
    * Sentry SDK init   — no-op.
    """
    from pipeline.api.main import create_app  # noqa: PLC0415

    fake_settings = _make_fake_settings()

    with (
        patch("pipeline.api.main.get_settings", return_value=fake_settings),
        patch("pipeline.api.routes.health.get_settings", return_value=fake_settings),
        patch("pipeline.core.config.get_settings", return_value=fake_settings),
        patch("pipeline.api.main.engine") as mock_engine,
        patch("pipeline.api.main.domain_registry") as mock_registry,
        patch("sentry_sdk.init"),
    ):
        # Make the engine's async context manager work
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_engine.dispose = AsyncMock()
        mock_registry.auto_discover = MagicMock()

        app = create_app()
        from pipeline.api.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: "test-user-id"

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_llm_response():
    """Patch litellm.acompletion to return a controlled, deterministic response.

    Usage::

        def test_something(mock_llm_response):
            mock_llm_response.return_value = _build_llm_response("my text")
    """
    mock_response = _build_mock_completion_response(
        content='{"task": "image classification", "key_contributions": ["novel architecture"]}'
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as mocked:
        mocked.return_value = mock_response
        yield mocked


# ---------------------------------------------------------------------------
# Domain model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_paper() -> Paper:
    """A fully-populated Paper Pydantic instance suitable for most tests."""
    return Paper(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        source=PaperSource.ARXIV_URL,
        source_url="https://arxiv.org/abs/1706.03762",  # type: ignore[arg-type]
        pdf_storage_path="papers/attention_is_all_you_need.pdf",
        metadata=PaperMetadata(
            title="Attention Is All You Need",
            authors=["Vaswani", "Shazeer", "Parmar"],
            abstract="We propose a new architecture, the Transformer...",
            venue="NeurIPS",
            year=2017,
            arxiv_id="1706.03762",
            doi=None,
            page_count=15,
            domain="NLP",
            sub_domain="Machine Translation",
        ),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture()
def sample_extraction() -> AiMlExtraction:
    """A valid, populated AiMlExtraction instance."""
    return AiMlExtraction(
        task="Neural Machine Translation",
        problem_statement="RNN sequential processing prevents parallelisation.",
        key_contributions=[
            "Self-attention mechanism",
            "Multi-head attention",
            "Positional encoding",
        ],
        proposed_method_summary="A purely attention-based encoder-decoder.",
        architecture_components=[
            ArchitectureComponent(
                name="Encoder",
                type="transformer",
                description="Stack of 6 identical self-attention layers.",
                inputs=["token_embeddings"],
                outputs=["context_vectors"],
            ),
            ArchitectureComponent(
                name="Decoder",
                type="transformer",
                description="Stack of 6 layers with cross-attention to encoder.",
                inputs=["context_vectors", "target_embeddings"],
                outputs=["logits"],
            ),
        ],
        training_procedure="Adam optimiser, warmup schedule, dropout=0.1.",
        loss_functions=["Cross-entropy loss"],
        datasets=[
            DatasetInfo(
                name="WMT 2014 EN-DE",
                size="4.5M sentence pairs",
                modality="text",
                split_info="Standard WMT splits",
            )
        ],
        evaluation_metrics=[
            MetricResult(
                metric_name="BLEU",
                value="28.4",
                baseline_comparison="+2.0 vs previous best",
            )
        ],
        baseline_comparisons="Outperforms all prior single-model results.",
        main_results="28.4 BLEU on EN-DE, 41.0 on EN-FR.",
        limitations="Quadratic attention complexity w.r.t. sequence length.",
        future_work="Extension to images and video.",
    )


@pytest.fixture()
def sample_extraction_result(sample_extraction: AiMlExtraction) -> ExtractionResult:
    """A valid ExtractionResult wrapping sample_extraction."""
    return ExtractionResult(
        paper_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        domain="NLP",
        extraction=sample_extraction.model_dump(),
        confidence_score=0.92,
    )


@pytest.fixture()
def pdf_bytes() -> bytes:
    """Minimal valid PDF byte string (12 bytes PDF header + EOF marker).

    Large enough to pass ``if not file_bytes`` guards without being a real PDF.
    """
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"xref\n0 1\n0000000000 65535 f \n"
        b"trailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_fake_settings():
    """Build an AppSettings-like object with fake credentials for testing."""
    from unittest.mock import MagicMock  # noqa: PLC0415

    settings = MagicMock()
    settings.environment = "development"
    settings.debug = True
    settings.log_level = "DEBUG"
    # Gemini
    settings.gemini.default_model = "gemini/gemini-2.0-flash"
    settings.gemini.embedding_model = "gemini/text-embedding-004"
    settings.gemini.api_key.get_secret_value.return_value = "test-gemini-key"
    settings.gemini.temperature = 0.2
    settings.gemini.max_retries = 3
    settings.gemini.timeout_seconds = 120.0
    # Supabase
    settings.supabase.url = "https://test.supabase.co"
    settings.supabase.papers_bucket = "papers"
    settings.supabase.outputs_bucket = "outputs"
    settings.supabase.service_role_key.get_secret_value.return_value = "test-svc-key"
    settings.supabase.anon_key.get_secret_value.return_value = "test-anon-key"
    # Langfuse
    settings.langfuse.enabled = False
    settings.langfuse.public_key.get_secret_value.return_value = "test-lf-pub"
    settings.langfuse.secret_key.get_secret_value.return_value = "test-lf-sec"
    settings.langfuse.host = "https://cloud.langfuse.com"
    # Pipeline
    settings.pipeline.cache_enabled = True
    settings.pipeline.max_pages = 60
    settings.pipeline.token_budget_per_paper = 500_000
    settings.pipeline.enabled_stages = []
    return settings


def _build_mock_completion_response(content: str) -> MagicMock:
    """Build a MagicMock that looks like a litellm ModelResponse."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.usage.total_tokens = 500
    response.usage.prompt_tokens = 350
    response.usage.completion_tokens = 150
    return response
