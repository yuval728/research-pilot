"""
pipeline/core/retry.py

Tenacity-based retry decorators for LLM and HTTP calls.

All retry logic lives here — stages never implement their own retry logic.

Decorators
----------
@llm_retry
    Retries on LLMRateLimitError and LLMTimeoutError with exponential backoff.
    Max 3 attempts. Logs each retry via structlog.

@http_retry
    Retries on connection errors and HTTP 5xx responses.
    Max 3 attempts with jittered exponential backoff.

@with_validation_retry
    Specific to Instructor calls: retries on pydantic ValidationError,
    feeding the error message back into the prompt automatically.
    Max 3 attempts (Instructor handles the prompt patching internally).

Usage
-----
    from pipeline.core.retry import llm_retry, http_retry

    @llm_retry
    async def call_gemini(...): ...

    @http_retry
    async def fetch_pdf(...): ...
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    wait_random_exponential,
)

from pipeline.core.exceptions import LLMRateLimitError, LLMTimeoutError

_F = TypeVar("_F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_MAX_ATTEMPTS = 3
_MIN_WAIT = 1.0  # seconds
_MAX_WAIT = 60.0  # seconds


# ---------------------------------------------------------------------------
# Structlog-aware retry callback
# ---------------------------------------------------------------------------


def _log_retry(retry_state: RetryCallState) -> None:
    """After-retry callback: log the attempt with structlog."""
    from pipeline.core.logger import get_logger

    log = get_logger(__name__)

    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.warning(
        "retry_attempt",
        attempt=retry_state.attempt_number,
        next_wait_seconds=round(
            retry_state.next_action.sleep if retry_state.next_action else 0, 2
        ),
        error_type=type(exc).__name__ if exc else "unknown",
        error=str(exc) if exc else "",
    )


def _log_final_failure(retry_state: RetryCallState) -> None:
    """Called when all retries are exhausted."""
    from pipeline.core.logger import get_logger

    log = get_logger(__name__)

    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.error(
        "retry_exhausted",
        attempts=retry_state.attempt_number,
        error_type=type(exc).__name__ if exc else "unknown",
        error=str(exc) if exc else "",
    )


# ---------------------------------------------------------------------------
# @llm_retry
# ---------------------------------------------------------------------------


def llm_retry(fn: _F) -> _F:
    """Retry a function on transient LLM errors (rate limit & timeout).

    - Retries: up to 3 attempts total
    - Back-off: random exponential 1s → 60s with full jitter
    - Retries on: LLMRateLimitError, LLMTimeoutError
    - Logs each retry attempt via structlog
    """
    decorated = retry(
        retry=retry_if_exception_type((LLMRateLimitError, LLMTimeoutError)),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_random_exponential(min=_MIN_WAIT, max=_MAX_WAIT),
        after=_log_retry,
        reraise=True,
    )(fn)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return decorated(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# @http_retry
# ---------------------------------------------------------------------------


class _HttpError(Exception):
    """Raised internally when an HTTP response has a 5xx status code."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def http_retry(fn: _F) -> _F:
    """Retry a function on transient HTTP/network errors.

    - Retries: up to 3 attempts total
    - Back-off: exponential with jitter (1s base, 30s cap)
    - Retries on: OSError (connection errors), _HttpError (5xx)

    Callers must raise ``_HttpError(status_code)`` themselves if they want
    status-code-based retries, or use the ``check_http_status`` helper below.
    """
    decorated = retry(
        retry=retry_if_exception_type((OSError, _HttpError)),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=1, max=30, jitter=2),
        after=_log_retry,
        reraise=True,
    )(fn)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return decorated(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def check_http_status(status_code: int) -> None:
    """Raise ``_HttpError`` if *status_code* is a server error (5xx).

    Call this inside an ``@http_retry``-decorated function after receiving
    a response to trigger a retry on server-side failures.

    Example::

        @http_retry
        async def fetch(url: str) -> bytes:
            resp = await client.get(url)
            check_http_status(resp.status_code)
            return resp.content
    """
    if status_code >= 500:
        raise _HttpError(status_code)


# ---------------------------------------------------------------------------
# @with_validation_retry
# ---------------------------------------------------------------------------


def with_validation_retry(fn: _F) -> _F:
    """Retry an Instructor-wrapped LLM call on Pydantic ValidationError.

    Instructor patches the prompt with the validation error on each attempt,
    so this decorator only needs to manage the retry count and logging.

    - Retries: up to 3 attempts total
    - Back-off: exponential 0.5s → 5s (validation failures are usually fast)
    - Retries on: pydantic.ValidationError

    Note: Instructor's ``max_retries`` parameter should be set to match
    ``_MAX_ATTEMPTS`` so the two retry mechanisms stay in sync.
    """
    try:
        from pydantic import ValidationError as PydanticValidationError
    except ImportError as e:  # pragma: no cover
        raise ImportError("pydantic is required for with_validation_retry") from e

    decorated = retry(
        retry=retry_if_exception_type(PydanticValidationError),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=0.5, max=5, jitter=0.5),
        after=_log_retry,
        reraise=True,
    )(fn)

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return decorated(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
