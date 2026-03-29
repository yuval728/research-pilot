"""
tests/unit/core/test_retry.py

Unit tests for pipeline/core/retry.py

Tests verify:
- @llm_retry retries on LLMRateLimitError and LLMTimeoutError
- @llm_retry does NOT retry on other exceptions
- @llm_retry re-raises after max attempts are exhausted
- @http_retry retries on OSError
- check_http_status raises _HttpError for 5xx, not for 2xx/4xx
- @with_validation_retry retries on pydantic.ValidationError
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from pipeline.core.exceptions import LLMRateLimitError, LLMTimeoutError
from pipeline.core.retry import (
    _HttpError,
    check_http_status,
    http_retry,
    llm_retry,
    with_validation_retry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pydantic_validation_error() -> ValidationError:
    from pydantic import BaseModel

    class M(BaseModel):
        x: int

    try:
        M(x="not-an-int")  # type: ignore[arg-type]
    except ValidationError as e:
        return e
    raise AssertionError("expected ValidationError")  # pragma: no cover


# ---------------------------------------------------------------------------
# @llm_retry
# ---------------------------------------------------------------------------


class TestLLMRetry:
    def test_retries_on_rate_limit_error(self):
        call_count = 0

        @llm_retry
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise LLMRateLimitError("rate limit", model="m")
            return "ok"

        with patch(
            "pipeline.core.retry.wait_random_exponential", return_value=iter([0, 0, 0])
        ):
            result = fn()

        assert result == "ok"
        assert call_count == 3

    def test_retries_on_timeout_error(self):
        call_count = 0

        @llm_retry
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise LLMTimeoutError("timeout", model="m", timeout_seconds=10)
            return "ok"

        with patch(
            "pipeline.core.retry.wait_random_exponential", return_value=iter([0, 0])
        ):
            result = fn()

        assert result == "ok"
        assert call_count == 2

    def test_does_not_retry_on_other_exceptions(self):
        call_count = 0

        @llm_retry
        def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retried")

        with pytest.raises(ValueError, match="not retried"):
            fn()

        assert call_count == 1

    def test_reraises_after_max_attempts(self):
        @llm_retry
        def fn():
            raise LLMRateLimitError("rate limit", model="m")

        with patch(
            "pipeline.core.retry.wait_random_exponential", return_value=iter([0, 0, 0])
        ):
            with pytest.raises(LLMRateLimitError):
                fn()

    def test_preserves_return_value(self):
        @llm_retry
        def fn():
            return {"data": 42}

        assert fn() == {"data": 42}


# ---------------------------------------------------------------------------
# @http_retry
# ---------------------------------------------------------------------------


class TestHttpRetry:
    def test_retries_on_os_error(self):
        call_count = 0

        @http_retry
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("connection refused")
            return "ok"

        with patch(
            "pipeline.core.retry.wait_exponential_jitter", return_value=iter([0, 0])
        ):
            result = fn()

        assert result == "ok"
        assert call_count == 2

    def test_does_not_retry_on_4xx(self):
        call_count = 0

        @http_retry
        def fn():
            nonlocal call_count
            call_count += 1
            # 404 → _HttpError is NOT raised; only 5xx triggers retry
            return "not found"

        result = fn()
        assert result == "not found"
        assert call_count == 1

    def test_retries_on_5xx_via_http_error(self):
        call_count = 0

        @http_retry
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _HttpError(503)
            return "ok"

        with patch(
            "pipeline.core.retry.wait_exponential_jitter", return_value=iter([0, 0])
        ):
            result = fn()

        assert result == "ok"
        assert call_count == 2


# ---------------------------------------------------------------------------
# check_http_status
# ---------------------------------------------------------------------------


class TestCheckHttpStatus:
    @pytest.mark.parametrize("code", [200, 201, 301, 400, 404, 422])
    def test_no_raise_for_non_5xx(self, code: int):
        check_http_status(code)  # should not raise

    @pytest.mark.parametrize("code", [500, 502, 503, 504])
    def test_raises_for_5xx(self, code: int):
        with pytest.raises(_HttpError) as exc_info:
            check_http_status(code)
        assert exc_info.value.status_code == code


# ---------------------------------------------------------------------------
# @with_validation_retry
# ---------------------------------------------------------------------------


class TestWithValidationRetry:
    def test_retries_on_pydantic_validation_error(self):
        call_count = 0

        @with_validation_retry
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _make_pydantic_validation_error()
            return "ok"

        with patch(
            "pipeline.core.retry.wait_exponential_jitter", return_value=iter([0, 0])
        ):
            result = fn()

        assert result == "ok"
        assert call_count == 2

    def test_does_not_retry_on_non_validation_error(self):
        call_count = 0

        @with_validation_retry
        def fn():
            nonlocal call_count
            call_count += 1
            raise TypeError("not a validation error")

        with pytest.raises(TypeError):
            fn()

        assert call_count == 1

    def test_reraises_validation_error_after_max_attempts(self):
        @with_validation_retry
        def fn():
            raise _make_pydantic_validation_error()

        with patch(
            "pipeline.core.retry.wait_exponential_jitter", return_value=iter([0, 0, 0])
        ):
            with pytest.raises(ValidationError):
                fn()
