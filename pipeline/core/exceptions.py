"""
pipeline/core/exceptions.py

Full custom exception hierarchy for Research Pilot.

Every exception carries structured context so that error handling and Sentry
reports are self-contained — no need to dig through raw log strings.

Hierarchy
---------
ResearchPilotError
├── PipelineError
│   ├── StageError(stage_name, run_id, cause)
│   └── DependencyNotMetError(stage_name, missing_dependency)
├── IngestionError
│   ├── PDFFetchError(source_url, status_code)
│   └── DuplicatePaperError(identifier, identifier_type)
├── LLMError
│   ├── LLMRateLimitError(model, retry_after)
│   ├── LLMValidationError(raw_output, schema_name, attempts)
│   ├── LLMTimeoutError(model, timeout_seconds)
│   └── TokenBudgetExceededError(budget, actual, stage_name)
├── StorageError
│   ├── FileUploadError(bucket, path, cause)
│   └── FileNotFoundError(bucket, path)
└── EmbeddingError(model, cause)
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class ResearchPilotError(Exception):
    """Root exception for all Research Pilot errors."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context

    def __repr__(self) -> str:  # pragma: no cover
        ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{self.__class__.__name__}({self.message!r}, {ctx})"


# ---------------------------------------------------------------------------
# Pipeline errors
# ---------------------------------------------------------------------------


class PipelineError(ResearchPilotError):
    """Errors originating from the pipeline orchestration layer."""


class StageError(PipelineError):
    """A specific pipeline stage failed.

    Parameters
    ----------
    stage_name:
        Name of the stage that raised the error (e.g. ``"extract"``).
    run_id:
        UUID of the pipeline run.
    cause:
        The underlying exception that triggered this error.
    """

    def __init__(
        self,
        message: str,
        *,
        stage_name: str,
        run_id: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, stage_name=stage_name, run_id=run_id)
        self.stage_name = stage_name
        self.run_id = run_id
        self.cause = cause

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"StageError({self.message!r}, stage={self.stage_name!r},"
            f" run_id={self.run_id!r}, cause={self.cause!r})"
        )


class DependencyNotMetError(PipelineError):
    """A stage cannot run because a required upstream stage hasn't completed.

    Parameters
    ----------
    stage_name:
        The stage that is blocked.
    missing_dependency:
        The upstream stage whose output is missing.
    """

    def __init__(
        self,
        message: str,
        *,
        stage_name: str,
        missing_dependency: str,
    ) -> None:
        super().__init__(
            message,
            stage_name=stage_name,
            missing_dependency=missing_dependency,
        )
        self.stage_name = stage_name
        self.missing_dependency = missing_dependency


# ---------------------------------------------------------------------------
# Ingestion errors
# ---------------------------------------------------------------------------


class IngestionError(ResearchPilotError):
    """Errors during the paper ingestion (fetch / dedup) stage."""


class PDFFetchError(IngestionError):
    """Failed to fetch a PDF from a remote URL.

    Parameters
    ----------
    source_url:
        The URL that was attempted.
    status_code:
        HTTP status code returned by the remote server (if available).
    """

    def __init__(
        self,
        message: str,
        *,
        source_url: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, source_url=source_url, status_code=status_code)
        self.source_url = source_url
        self.status_code = status_code


class DuplicatePaperError(IngestionError):
    """Paper already exists in the library.

    Parameters
    ----------
    identifier:
        The arXiv ID, DOI, or content hash that matched an existing paper.
    identifier_type:
        One of ``"arxiv_id"``, ``"doi"``, or ``"content_hash"``.
    """

    def __init__(
        self,
        message: str,
        *,
        identifier: str,
        identifier_type: str,
    ) -> None:
        super().__init__(
            message,
            identifier=identifier,
            identifier_type=identifier_type,
        )
        self.identifier = identifier
        self.identifier_type = identifier_type


# ---------------------------------------------------------------------------
# LLM errors
# ---------------------------------------------------------------------------


class LLMError(ResearchPilotError):
    """Base class for all errors originating from LLM calls."""


class LLMRateLimitError(LLMError):
    """The LLM provider returned a rate-limit response.

    Parameters
    ----------
    model:
        The model string (e.g. ``"gemini/gemini-2.0-flash"``).
    retry_after:
        Seconds to wait before retrying (if provided by the API).
    """

    def __init__(
        self,
        message: str,
        *,
        model: str,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, model=model, retry_after=retry_after)
        self.model = model
        self.retry_after = retry_after


class LLMValidationError(LLMError):
    """Instructor failed to parse/validate the LLM response after all retries.

    Parameters
    ----------
    raw_output:
        The raw text returned by the LLM on the last attempt.
    schema_name:
        The Pydantic model class name that validation was run against.
    attempts:
        Total number of attempts made before giving up.
    """

    def __init__(
        self,
        message: str,
        *,
        raw_output: str,
        schema_name: str,
        attempts: int,
    ) -> None:
        super().__init__(
            message,
            schema_name=schema_name,
            attempts=attempts,
        )
        self.raw_output = raw_output
        self.schema_name = schema_name
        self.attempts = attempts


class LLMTimeoutError(LLMError):
    """An LLM call exceeded the configured timeout.

    Parameters
    ----------
    model:
        The model string.
    timeout_seconds:
        The timeout limit that was exceeded.
    """

    def __init__(
        self,
        message: str,
        *,
        model: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(message, model=model, timeout_seconds=timeout_seconds)
        self.model = model
        self.timeout_seconds = timeout_seconds


class TokenBudgetExceededError(LLMError):
    """A paper exceeded the configured per-stage token budget.

    Parameters
    ----------
    budget:
        Maximum tokens allowed for this stage.
    actual:
        Actual token count encountered.
    stage_name:
        Stage where the budget was exceeded.
    """

    def __init__(
        self,
        message: str,
        *,
        budget: int,
        actual: int,
        stage_name: str,
    ) -> None:
        super().__init__(
            message,
            budget=budget,
            actual=actual,
            stage_name=stage_name,
        )
        self.budget = budget
        self.actual = actual
        self.stage_name = stage_name


# ---------------------------------------------------------------------------
# Storage errors
# ---------------------------------------------------------------------------


class StorageError(ResearchPilotError):
    """Errors related to Supabase Storage operations."""


class FileUploadError(StorageError):
    """Failed to upload a file to Supabase Storage.

    Parameters
    ----------
    bucket:
        Storage bucket name (e.g. ``"papers"``).
    path:
        Target path within the bucket.
    cause:
        The underlying exception.
    """

    def __init__(
        self,
        message: str,
        *,
        bucket: str,
        path: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, bucket=bucket, path=path)
        self.bucket = bucket
        self.path = path
        self.cause = cause


class FileNotFoundError(StorageError):  # noqa: A001 — intentional shadow
    """A requested file does not exist in Supabase Storage.

    Parameters
    ----------
    bucket:
        Storage bucket name.
    path:
        Expected path within the bucket.
    """

    def __init__(self, message: str, *, bucket: str, path: str) -> None:
        super().__init__(message, bucket=bucket, path=path)
        self.bucket = bucket
        self.path = path


# ---------------------------------------------------------------------------
# Embedding errors
# ---------------------------------------------------------------------------


class EmbeddingError(ResearchPilotError):
    """Failed to generate or store an embedding.

    Parameters
    ----------
    model:
        The embedding model used (e.g. ``"gemini/text-embedding-004"``).
    cause:
        The underlying exception.
    """

    def __init__(
        self,
        message: str,
        *,
        model: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, model=model)
        self.model = model
        self.cause = cause
