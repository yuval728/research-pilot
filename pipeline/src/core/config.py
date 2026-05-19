"""
pipeline/core/config.py

Pydantic-settings based configuration for the Research Pilot pipeline.

Loading order (later sources override earlier ones):
  1. Default values defined on each settings class
  2. config.yaml (if present at RESEARCH_PILOT_CONFIG_PATH or ./config.yaml)
  3. Environment variables  (case-insensitive, prefixed per nested class)
  4. .env file (pipeline/.env — for local dev)

Usage
-----
    from pipeline.core.config import get_settings

    settings = get_settings()
    model = settings.gemini.default_model

Nothing outside this module should read ``os.environ`` directly.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Literal, TypeVar

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILES = (".env", "../.env", "../../.env")


# ---------------------------------------------------------------------------
# Nested settings groups
# ---------------------------------------------------------------------------


class GeminiSettings(BaseSettings):
    """Settings for Gemini model access via LiteLLM."""

    model_config = SettingsConfigDict(
        env_prefix="GEMINI_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    # Model names used by each stage (override in config.yaml or env)
    default_model: str = Field(
        default="gemini/gemini-2.0-flash",
        description="Model used for most stages.",
    )
    vision_model: str = Field(
        default="gemini/gemini-2.0-flash",
        description="Model used for stages that require native PDF vision.",
    )
    embedding_model: str = Field(
        default="gemini/text-embedding-004",
        description="Model used for embedding generation.",
    )

    # Generation parameters
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=8192, ge=1)

    # Reliability
    max_retries: int = Field(default=3, ge=1, le=10)
    timeout_seconds: float = Field(default=120.0, ge=5.0)

    # Auth — read from GEMINI_API_KEY env var
    api_key: SecretStr = Field(default=..., description="Gemini API key.")


class SupabaseSettings(BaseSettings):
    """Settings for Supabase (database + storage + auth)."""

    model_config = SettingsConfigDict(
        env_prefix="SUPABASE_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    url: str = Field(default=..., description="Supabase project URL.")
    db_url: SecretStr = Field(default=..., description="PostgreSQL connection string.")
    anon_key: SecretStr = Field(default=..., description="Supabase anon/public key.")
    service_role_key: SecretStr = Field(
        default=..., description="Supabase service-role key (backend only)."
    )

    # Storage bucket names
    papers_bucket: str = Field(default="papers")
    outputs_bucket: str = Field(default="outputs")


class LangfuseSettings(BaseSettings):
    """Settings for Langfuse LLM observability."""

    model_config = SettingsConfigDict(
        env_prefix="LANGFUSE_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    public_key: SecretStr = Field(default=..., description="Langfuse public key.")
    secret_key: SecretStr = Field(default=..., description="Langfuse secret key.")
    host: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse host URL.",
    )
    enabled: bool = Field(
        default=True,
        description="Set to False to disable Langfuse tracing (e.g. in unit tests).",
    )


class PipelineSettings(BaseSettings):
    """Settings that control pipeline execution behaviour."""

    model_config = SettingsConfigDict(
        env_prefix="PIPELINE_",
        env_file=_ENV_FILES,
        extra="ignore",
    )

    # Stages to run — empty list means all stages
    enabled_stages: list[str] = Field(
        default_factory=list,
        description="Whitelist of stage names. Empty = run all.",
    )

    cache_enabled: bool = Field(
        default=True,
        description="When True, completed stages are skipped on re-runs.",
    )

    # Per-paper limits
    max_pages: int = Field(
        default=60,
        ge=1,
        description="Max pages to process per paper. Longer PDFs are truncated.",
    )
    token_budget_per_paper: int = Field(
        default=500_000,
        ge=1,
        description="Total token budget across all LLM calls for a single paper.",
    )


class AppSettings(BaseSettings):
    """Top-level application settings that compose all nested groups."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    debug: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    sentry_dsn: SecretStr | None = Field(default=None)

    # Nested settings — each resolved independently from env
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)


# ---------------------------------------------------------------------------
# YAML overlay
# ---------------------------------------------------------------------------


def _load_yaml_overrides(path: Path) -> dict:  # type: ignore[type-arg]
    """Read a YAML config file and return its contents as a plain dict."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data  # type: ignore[return-value]


def _build_settings(yaml_path: Path | None = None) -> AppSettings:
    """Construct AppSettings, applying YAML overrides before env vars.

    The YAML file is read first and its keys are injected into the nested
    settings objects, then pydantic-settings applies env-var overrides on top.
    """
    yaml_path = yaml_path or Path(
        os.getenv("RESEARCH_PILOT_CONFIG_PATH", "config.yaml")
    )
    overrides = _load_yaml_overrides(yaml_path)

    # Flatten YAML overrides into env-var format so pydantic-settings picks
    # them up with lower priority than real env vars.
    # We do this by constructing nested objects explicitly.
    TSettings = TypeVar("TSettings", bound=BaseSettings)

    def _section(cls: type[TSettings], key: str) -> TSettings:
        section_data = overrides.get(key, {})
        return cls(**section_data)

    return AppSettings(
        **{
            k: v
            for k, v in overrides.items()
            if k not in ("gemini", "supabase", "langfuse", "pipeline")
        },
        gemini=_section(GeminiSettings, "gemini"),
        supabase=_section(SupabaseSettings, "supabase"),
        langfuse=_section(LangfuseSettings, "langfuse"),
        pipeline=_section(PipelineSettings, "pipeline"),
    )


# ---------------------------------------------------------------------------
# Cached singleton
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the cached AppSettings singleton.

    Call ``get_settings.cache_clear()`` in tests to reset between cases.
    """
    return _build_settings()
