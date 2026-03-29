"""
pipeline/core/logger.py

Configures structlog with:
- JSON rendering in production/staging
- Pretty console rendering in development
- Consistent processors: timestamp, log level, caller, exception info

Usage
-----
    from pipeline.core.logger import get_logger

    log = get_logger(__name__)
    log.info("stage_started", stage="ingest", run_id="abc-123")

Every log call should pass structured key-value pairs, never format strings.
The ``name`` key is automatically added by get_logger().
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from structlog.types import FilteringBoundLogger

_configured = False


def _configure_structlog(log_level: str = "INFO", *, pretty: bool = False) -> None:
    """Configure structlog processors and stdlib integration.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
        structlog.processors.StackInfoRenderer(),
    ]

    if pretty:
        # Development — coloured, human-readable
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Production — JSON
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.ExceptionRenderer(),
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level.upper())

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "litellm", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def setup_logging(log_level: str = "INFO", *, pretty: bool | None = None) -> None:
    """Initialise structlog.

    Called once at application startup (e.g. from FastAPI lifespan or pipeline
    entry point). Subsequent calls are safe but do nothing.

    Parameters
    ----------
    log_level:
        Minimum log level (DEBUG / INFO / WARNING / ERROR / CRITICAL).
    pretty:
        Force console rendering. If ``None``, auto-detects: pretty when
        ``sys.stdout.isatty()`` is True, JSON otherwise.
    """
    if pretty is None:
        pretty = sys.stdout.isatty()
    _configure_structlog(log_level=log_level, pretty=pretty)


def get_logger(name: str) -> FilteringBoundLogger:
    """Return a named structlog logger.

    If logging has not been configured yet, a sensible default is applied
    automatically so modules imported early (e.g. during testing) still work.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.
    """
    if not _configured:
        setup_logging()
    return structlog.get_logger(name)
