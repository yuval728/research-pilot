"""
pipeline.api.routes.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pipeline run management — trigger runs, poll status, retry stages.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from pipeline.api.dependencies import CurrentUserDep, PipelineServiceDep
from pipeline.models.run import PipelineRun, StageResult

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
        return await pipeline_service.trigger_run(paper_id)
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
        return await pipeline_service.get_run_status(run_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


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
        await pipeline_service.retry_stage(run_id, stage_name)
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
        return await pipeline_service.get_stage_result(run_id, stage_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
