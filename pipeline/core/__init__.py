"""
pipeline/core/__init__.py
Public re-exports for the core module.
"""

from pipeline.core.config import AppSettings, get_settings
from pipeline.core.events import Event, EventBus, EventType
from pipeline.core.exceptions import (
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
from pipeline.core.logger import get_logger
from pipeline.core.telemetry import TelemetryCollector, TelemetryRecord, track_llm_call

__all__ = [
    # config
    "AppSettings",
    "get_settings",
    # events
    "Event",
    "EventBus",
    "EventType",
    # exceptions
    "ResearchPilotError",
    "PipelineError",
    "StageError",
    "DuplicatePaperError",
    "EmbeddingError",
    "FileNotFoundError",
    "FileUploadError",
    "IngestionError",
    "LLMError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMValidationError",
    "PDFFetchError",
    "StorageError",
    "TokenBudgetExceededError",
    # logger
    "get_logger",
    # telemetry
    "TelemetryCollector",
    "TelemetryRecord",
    "track_llm_call",
]
