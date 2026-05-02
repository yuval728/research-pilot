"""
pipeline.api.dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~
FastAPI dependency injection functions.

All route dependencies come from here — never instantiate services inside
route handlers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import SessionLocal
from src.services import ExportService, PaperService, PipelineService

settings = get_settings()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=True)


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


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> str:
    """Validate a Supabase JWT and return the authenticated user_id.

    Raises HTTP 401 if the token is missing, malformed, or expired.
    """
    token = credentials.credentials
    try:
        import jwt  # PyJWT — supabase-py bundles it

        decoded = jwt.decode(
            token,
            settings.supabase.anon_key.get_secret_value(),
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
        user_id: str = decoded["sub"]
        return user_id
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUserDep = Annotated[str, Depends(get_current_user)]
