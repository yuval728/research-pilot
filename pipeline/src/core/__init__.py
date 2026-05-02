"""
pipeline/core/__init__.py
Public re-exports for the core module.
"""

from src.core.config import AppSettings, get_settings
from src.core.events import Event, EventBus, EventType
from src.core.exceptions import (
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
from src.core.logger import get_logger
from src.core.telemetry import TelemetryCollector, TelemetryRecord, track_llm_call

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
