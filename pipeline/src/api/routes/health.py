"""
pipeline.api.routes.health
~~~~~~~~~~~~~~~~~~~~~~~~~~
Liveness and readiness endpoints consumed by Better Uptime and ops tooling.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from src.core.config import get_settings
from src.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])

settings = get_settings()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    environment: str


class DependencyStatus(BaseModel):
    healthy: bool
    detail: str | None = None


class DetailedHealthResponse(BaseModel):
    status: str
    environment: str
    dependencies: dict[str, DependencyStatus]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Returns 200 OK when the process is alive. Used by uptime monitors.",
)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
    )


@router.get(
    "/detailed",
    response_model=DetailedHealthResponse,
    summary="Readiness / dependency check",
    description=(
        "Probes each external dependency and returns per-component status. "
        "Useful for debugging production incidents."
    ),
)
async def health_detailed() -> DetailedHealthResponse:
    deps: dict[str, DependencyStatus] = {}

    # --- Database ---
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        deps["database"] = DependencyStatus(healthy=True)
    except Exception as exc:  # noqa: BLE001
        deps["database"] = DependencyStatus(healthy=False, detail=str(exc))

    # --- Supabase Storage ---
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            _svc_key = settings.supabase.service_role_key.get_secret_value()
            resp = await client.get(
                f"{settings.supabase.url}/storage/v1/bucket",
                headers={
                    "apikey": _svc_key,
                    "Authorization": f"Bearer {_svc_key}",
                },
            )
        deps["supabase_storage"] = DependencyStatus(
            healthy=resp.status_code < 500,
            detail=None if resp.status_code < 500 else f"HTTP {resp.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        deps["supabase_storage"] = DependencyStatus(healthy=False, detail=str(exc))

    # --- Gemini API (LiteLLM reachability) ---
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": settings.gemini.api_key.get_secret_value()},
            )
        deps["gemini_api"] = DependencyStatus(
            healthy=resp.status_code < 500,
            detail=None if resp.status_code < 500 else f"HTTP {resp.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        deps["gemini_api"] = DependencyStatus(healthy=False, detail=str(exc))

    overall = "ok" if all(d.healthy for d in deps.values()) else "degraded"

    return DetailedHealthResponse(
        status=overall,
        environment=settings.environment,
        dependencies=deps,
    )
