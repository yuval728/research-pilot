"""
pipeline.api.routes.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pipeline run management — trigger runs, poll status, retry stages.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.api.dependencies import CurrentUserDep, PipelineServiceDep
from src.models.run import PipelineRun, StageResult
from fastapi.responses import StreamingResponse
import json
import asyncio

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post(
    "/run/{paper_id}",
    response_model=PipelineRun,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a pipeline run for a paper",
    description=(
        "Enqueues a background pipeline execution for the given paper. "
        "Returns the new PipelineRun (in PENDING state) immediately — poll "
        "GET /pipeline/runs/{run_id} to track progress."
    ),
)
async def trigger_run(
    paper_id: uuid.UUID,
    pipeline_service: PipelineServiceDep,
    _user: CurrentUserDep,
) -> PipelineRun:
    """Start the LangGraph pipeline for *paper_id* in the background."""
    try:
        return await pipeline_service.trigger_run(paper_id, user_id=_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/runs/{run_id}",
    response_model=PipelineRun,
    summary="Get pipeline run status",
    description="Returns the full PipelineRun record including per-stage statuses.",
)
async def get_run_status(
    run_id: uuid.UUID,
    pipeline_service: PipelineServiceDep,
    _user: CurrentUserDep,
) -> PipelineRun:
    """Fetch the current status and all stage results for a run."""
    try:
        return await pipeline_service.get_run_status(run_id, user_id=_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/papers/{paper_id}/latest-run",
    response_model=PipelineRun | None,
    summary="Get the latest pipeline run for a paper",
    description="Returns the newest PipelineRun for the given paper, or null if none exists.",
)
async def get_latest_run_for_paper(
    paper_id: uuid.UUID,
    pipeline_service: PipelineServiceDep,
    _user: CurrentUserDep,
) -> PipelineRun | None:
    return await pipeline_service.get_latest_run_for_paper(paper_id, user_id=_user)


@router.post(
    "/runs/{run_id}/stages/{stage_name}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a single pipeline stage",
    description=(
        "Resets the given stage to PENDING and re-invokes the LangGraph pipeline. "
        "Completed stages are skipped by the graph's caching logic."
    ),
)
async def retry_stage(
    run_id: uuid.UUID,
    stage_name: str,
    pipeline_service: PipelineServiceDep,
    _user: CurrentUserDep,
) -> dict[str, str]:
    """Reset *stage_name* to PENDING and re-trigger pipeline execution."""
    try:
        await pipeline_service.retry_stage(run_id, stage_name, user_id=_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return {"status": "accepted", "run_id": str(run_id), "stage": stage_name}


@router.get(
    "/runs/{run_id}/stages/{stage_name}",
    response_model=StageResult,
    summary="Get individual stage result",
    description="Returns the status and metadata for a single pipeline stage.",
)
async def get_stage_result(
    run_id: uuid.UUID,
    stage_name: str,
    pipeline_service: PipelineServiceDep,
    _user: CurrentUserDep,
) -> StageResult:
    """Fetch the result record for *stage_name* within *run_id*."""
    try:
        return await pipeline_service.get_stage_result(
            run_id, stage_name, user_id=_user
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/runs/{run_id}/stream",
    summary="Stream pipeline run updates (SSE)",
    description="Server-sent events stream emitting run status updates for the given run_id.",
)
async def stream_run_status(
    run_id: uuid.UUID,
    pipeline_service: PipelineServiceDep,
    _user: CurrentUserDep,
) -> StreamingResponse:
    async def event_generator():
        last_payload: dict | None = None
        error_count = 0
        max_errors = 10
        base_delay = 1.0
        try:
            while True:
                try:
                    run = await pipeline_service.get_run_status(run_id, user_id=_user)
                    error_count = 0  # Reset on success
                    payload = {
                        "id": str(run.id),
                        "status": run.status.value,
                        "stages": {
                            k: {"status": v.status.value} for k, v in run.stages.items()
                        },
                        "updated_at": run.created_at.isoformat(),
                    }
                    if payload != last_payload:
                        last_payload = payload
                        yield f"data: {json.dumps(payload)}\n\n"
                    if run.status.value in ("completed", "failed", "partial"):
                        break

                    await asyncio.sleep(1)
                except Exception as exc:
                    error_count += 1
                    if error_count >= max_errors:
                        yield f"data: {json.dumps({'error': 'Stream failed after repeated errors', 'detail': str(exc)})}\n\n"
                        break
                    # Exponential backoff: 1s, 2s, 4s, 8s...
                    delay = base_delay * (2 ** (error_count - 1))
                    await asyncio.sleep(delay)
        finally:
            pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")
