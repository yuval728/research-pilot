"""
pipeline.api.main
~~~~~~~~~~~~~~~~~
FastAPI application factory.

Responsibilities
----------------
* Creates the FastAPI app instance with metadata.
* Registers Sentry middleware (ASGI).
* Configures CORS for the Next.js frontend origin.
* Mounts all routers under their prefixes.
* Startup event  — DomainRegistry.auto_discover(), warms DB connection pool.
* Shutdown event — disposes the DB engine.
* Global exception handler — maps ResearchPilotError subclasses to structured
  JSON responses with correct HTTP status codes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import sentry_sdk
import sqlalchemy
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from starlette import status

from src.core.config import get_settings
from src.core.exceptions import (
    DuplicatePaperError,
    EmbeddingError,
    StorageFileNotFoundError,
    FileUploadError,
    IngestionError,
    LLMError,
    LLMRateLimitError,
    LLMValidationError,
    PipelineError,
    ResearchPilotError,
    StageError,
    StorageError,
)
from src.core.logger import get_logger, setup_logging
from src.db.session import engine
from src.domains.registry import registry as domain_registry

from .routes import health_router, papers_router, pipeline_router, search_router

logger = get_logger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Exception → HTTP status mapping
# ---------------------------------------------------------------------------

_STATUS_MAP: dict[type[ResearchPilotError], int] = {
    DuplicatePaperError: status.HTTP_409_CONFLICT,
    StorageFileNotFoundError: status.HTTP_404_NOT_FOUND,
    FileUploadError: status.HTTP_502_BAD_GATEWAY,
    IngestionError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    LLMRateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
    LLMValidationError: status.HTTP_502_BAD_GATEWAY,
    LLMError: status.HTTP_502_BAD_GATEWAY,
    StageError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    PipelineError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    StorageError: status.HTTP_502_BAD_GATEWAY,
    EmbeddingError: status.HTTP_502_BAD_GATEWAY,
}


def _http_status_for(exc: ResearchPilotError) -> int:
    """Walk the MRO to find the most specific status code mapping."""
    for cls in type(exc).__mro__:
        if cls in _STATUS_MAP:
            return _STATUS_MAP[cls]  # type: ignore[index]
    return status.HTTP_500_INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global logger

    setup_logging(
        log_level=settings.log_level,
        pretty=(settings.environment == "development"),
        force=True,
    )
    logger = get_logger(__name__)

    # ---- startup ----
    logger.info("startup", step="discover_plugins")
    domain_registry.auto_discover()

    # Warm the connection pool by making a trivial connection
    logger.info("startup", step="warm_db_pool")
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
    except Exception:  # noqa: BLE001
        logger.warning("startup", step="warm_db_pool_failed")

    logger.info("startup", step="complete", environment=settings.environment)

    yield  # ← application is running

    # ---- shutdown ----
    logger.info("shutdown", step="disposing_engine")
    await engine.dispose()
    logger.info("shutdown", step="complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""

    # Sentry — initialise before creating the app so the ASGI middleware
    # captures errors thrown during startup.
    sentry_dsn = None
    if settings.environment != "development" or settings.sentry_dsn:
        sentry_dsn = (
            settings.sentry_dsn.get_secret_value() if settings.sentry_dsn else None
        )
        if sentry_dsn:
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=settings.environment,
                traces_sample_rate=0.2,
            )

    app = FastAPI(
        title="Research Pilot API",
        description=(
            "AI-powered research paper intelligence pipeline. "
            "Ingest papers, run the LangGraph processing pipeline, "
            "and retrieve structured outputs."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ---- Sentry ASGI middleware ----
    if sentry_dsn:
        app.add_middleware(SentryAsgiMiddleware)  # type: ignore[arg-type]

    # ---- CORS ----
    frontend_origin = getattr(settings, "frontend_origin", "http://localhost:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Routers ----
    app.include_router(health_router)
    app.include_router(papers_router, prefix="/api/v1")
    app.include_router(pipeline_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")

    # ---- Global exception handler ----
    @app.exception_handler(ResearchPilotError)
    async def research_pilot_error_handler(
        request: Request, exc: ResearchPilotError
    ) -> JSONResponse:
        http_status = _http_status_for(exc)

        payload: dict[str, Any] = {
            "error": type(exc).__name__,
            "message": exc.message,
            "context": exc.context,
        }

        # Expose retry-after header for rate limit errors
        headers: dict[str, str] = {}
        if isinstance(exc, LLMRateLimitError) and exc.retry_after is not None:
            headers["Retry-After"] = str(int(exc.retry_after))

        logger.warning(
            "research_pilot_error",
            path=request.url.path,
            error=type(exc).__name__,
            message=exc.message,
        )

        return JSONResponse(
            status_code=http_status,
            content=payload,
            headers=headers,
        )

    # Catch-all for unexpected exceptions
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("unhandled_exception", path=request.url.path, exc=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred.",
            },
        )

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (for uvicorn / gunicorn entry points)
# ---------------------------------------------------------------------------

app = create_app()
