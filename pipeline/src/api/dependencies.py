"""
pipeline.api.dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI dependency injection functions.

All route dependencies come from here — never instantiate services inside
route handlers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logger import get_logger
from src.db.session import SessionLocal
from src.services import ExportService, PaperService, PipelineService

settings = get_settings()
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a SQLAlchemy async session per request, closed on teardown."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


DbDep = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def get_paper_service(db: DbDep) -> PaperService:
    """Return a PaperService bound to the current request session."""
    return PaperService(db)


def get_pipeline_service(db: DbDep) -> PipelineService:
    """Return a PipelineService bound to the current request session."""
    return PipelineService(db)


def get_export_service(db: DbDep) -> ExportService:
    """Return an ExportService bound to the current request session."""
    return ExportService(db)


PaperServiceDep = Annotated[PaperService, Depends(get_paper_service)]
PipelineServiceDep = Annotated[PipelineService, Depends(get_pipeline_service)]
ExportServiceDep = Annotated[ExportService, Depends(get_export_service)]

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_auth_client():
    from supabase import create_client

    return create_client(
        settings.supabase.url,
        settings.supabase.anon_key.get_secret_value(),
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Validate a Supabase JWT and return the authenticated user_id.

    Raises HTTP 401 if the token is missing, malformed, or expired.
    """
    token = None
    if credentials:
        token = credentials.credentials
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        supabase = get_auth_client()
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise ValueError("No user found in token")
        return user_response.user.id
    except Exception as exc:
        logger.warning(
            "auth_failed",
            error=type(exc).__name__,
            message=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUserDep = Annotated[str, Depends(get_current_user)]
