from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from src.models.run import PipelineRun, RunStatus


def test_get_latest_run_for_paper_returns_latest_run(test_client: TestClient):
    paper_id = uuid.uuid4()
    run = PipelineRun(
        id=uuid.uuid4(),
        paper_id=paper_id,
        status=RunStatus.COMPLETED,
        stages={},
    )

    with patch(
        "pipeline.services.pipeline_service.PipelineService.get_latest_run_for_paper",
        new_callable=AsyncMock,
    ) as mock_latest:
        mock_latest.return_value = run
        response = test_client.get(f"/api/v1/pipeline/papers/{paper_id}/latest-run")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(run.id)
    assert response.json()["paper_id"] == str(paper_id)


def test_get_latest_run_for_paper_returns_null_when_absent(test_client: TestClient):
    paper_id = uuid.uuid4()

    with patch(
        "pipeline.services.pipeline_service.PipelineService.get_latest_run_for_paper",
        new_callable=AsyncMock,
    ) as mock_latest:
        mock_latest.return_value = None
        response = test_client.get(f"/api/v1/pipeline/papers/{paper_id}/latest-run")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None
