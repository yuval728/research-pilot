"""
tests/unit/core/test_config.py

Unit tests for pipeline/core/config.py

Tests verify:
- get_settings() returns an AppSettings singleton
- cache_clear() forces a fresh load
- YAML overrides are applied
- Env-var overrides take effect
- Nested settings classes have correct defaults
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.core.config import (
    AppSettings,
    _build_settings,
    get_settings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_ENV = {
    "GEMINI_API_KEY": "test-key",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_DB_URL": "postgresql://test:test@localhost/test",
    "SUPABASE_ANON_KEY": "anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
    "LANGFUSE_SECRET_KEY": "sk-lf-test",
    # Pin to the documented default so a developer's .env (which may set a
    # different temperature) does not break the test_gemini_defaults assertion.
    "GEMINI_TEMPERATURE": "0.2",
}


def _settings_with_env(**extra: str) -> AppSettings:
    """Build settings with the minimal required env vars + extras."""
    env = {**_REQUIRED_ENV, **extra}
    sandbox_cwd = Path("C:/__researchpilot_test_sandbox__")
    with (
        patch.dict(os.environ, env, clear=True),
        patch("os.getcwd", return_value=str(sandbox_cwd)),
        patch("pathlib.Path.cwd", return_value=sandbox_cwd),
    ):
        get_settings.cache_clear()
        return get_settings()


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------


class TestGetSettingsSingleton:
    def teardown_method(self):
        get_settings.cache_clear()

    def test_same_object_returned_twice(self):
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s1 = _settings_with_env()
            s2 = get_settings()
        assert s1 is s2

    def test_cache_clear_returns_new_object(self):
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s1 = _settings_with_env()
            get_settings.cache_clear()
            s2 = _settings_with_env()
        assert s1 is not s2


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestDefaults:
    def teardown_method(self):
        get_settings.cache_clear()

    def test_environment_default(self):
        s = _settings_with_env()
        assert s.environment == "development"

    def test_debug_default_false(self):
        s = _settings_with_env()
        assert s.debug is False

    def test_log_level_default(self):
        s = _settings_with_env()
        assert s.log_level == "INFO"

    def test_gemini_defaults(self):
        s = _settings_with_env()
        assert "gemini" in s.gemini.default_model
        assert s.gemini.temperature == 0.2
        assert s.gemini.max_retries == 3

    def test_pipeline_defaults(self):
        s = _settings_with_env()
        assert s.pipeline.cache_enabled is True
        assert s.pipeline.max_pages == 60
        assert s.pipeline.token_budget_per_paper == 500_000
        assert s.pipeline.enabled_stages == []

    def test_langfuse_enabled_by_default(self):
        s = _settings_with_env()
        assert s.langfuse.enabled is True

    def test_supabase_bucket_names(self):
        s = _settings_with_env()
        assert s.supabase.papers_bucket == "papers"
        assert s.supabase.outputs_bucket == "outputs"


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvVarOverrides:
    def teardown_method(self):
        get_settings.cache_clear()

    def test_override_environment(self):
        s = _settings_with_env(ENVIRONMENT="production")
        assert s.environment == "production"

    def test_override_log_level(self):
        s = _settings_with_env(LOG_LEVEL="DEBUG")
        assert s.log_level == "DEBUG"

    def test_override_gemini_temperature(self):
        s = _settings_with_env(GEMINI_TEMPERATURE="0.7")
        assert s.gemini.temperature == pytest.approx(0.7)

    def test_override_pipeline_cache(self):
        s = _settings_with_env(PIPELINE_CACHE_ENABLED="false")
        assert s.pipeline.cache_enabled is False

    def test_override_langfuse_disabled(self):
        s = _settings_with_env(LANGFUSE_ENABLED="false")
        assert s.langfuse.enabled is False


# ---------------------------------------------------------------------------
# Secret values
# ---------------------------------------------------------------------------


class TestSecretValues:
    def teardown_method(self):
        get_settings.cache_clear()

    def test_gemini_api_key_is_secret(self):
        s = _settings_with_env()
        # SecretStr should not expose value via str()
        assert "test-key" not in str(s.gemini.api_key)
        assert s.gemini.api_key.get_secret_value() == "test-key"

    def test_supabase_keys_are_secret(self):
        s = _settings_with_env()
        assert s.supabase.anon_key.get_secret_value() == "anon-key"
        assert s.supabase.service_role_key.get_secret_value() == "service-key"


# ---------------------------------------------------------------------------
# YAML overrides
# ---------------------------------------------------------------------------


class TestYamlOverrides:
    def teardown_method(self):
        get_settings.cache_clear()

    def test_yaml_override_applied(self, tmp_path: Path):
        config_data = {
            "environment": "staging",
            "gemini": {"temperature": 0.9, "max_output_tokens": 4096},
            "pipeline": {"max_pages": 30},
        }
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml.dump(config_data))

        sandbox_cwd = Path("C:/__researchpilot_test_sandbox__")
        with (
            patch.dict(os.environ, _REQUIRED_ENV, clear=True),
            patch("os.getcwd", return_value=str(sandbox_cwd)),
            patch("pathlib.Path.cwd", return_value=sandbox_cwd),
        ):
            settings = _build_settings(yaml_path=yaml_file)

        assert settings.environment == "staging"
        assert settings.gemini.temperature == pytest.approx(0.9)
        assert settings.gemini.max_output_tokens == 4096
        assert settings.pipeline.max_pages == 30

    def test_missing_yaml_uses_defaults(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.yaml"
        sandbox_cwd = Path("C:/__researchpilot_test_sandbox__")
        with (
            patch.dict(os.environ, _REQUIRED_ENV, clear=True),
            patch("os.getcwd", return_value=str(sandbox_cwd)),
            patch("pathlib.Path.cwd", return_value=sandbox_cwd),
        ):
            settings = _build_settings(yaml_path=missing)
        assert settings.environment == "development"
