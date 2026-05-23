"""
tests/integration/test_api_papers.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration tests for the Papers API layer.

These tests use the `test_client` fixture to hit the FastAPI application.
Dependencies like the DB engine and Supabase storage are mocked out,
allowing verifying the routing, status codes, and JSON responses.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.domains.ai_ml.schema import AiMlExtraction
from src.models.output import OutputBundle
from src.models.paper import Paper, PaperListItem, PaperSource


@pytest.fixture
def mock_paper_service():
    with patch("pipeline.api.routes.papers.PaperServiceDep") as MockSvc:
        yield MockSvc


@pytest.fixture
def mock_export_service():
    with patch("pipeline.api.routes.papers.ExportServiceDep") as MockSvc:
        yield MockSvc


def test_list_papers(test_client: TestClient):
    """Test GET /api/v1/papers"""
    paper_id = uuid.uuid4()
    mock_paper = Paper(
        id=paper_id,
        source=PaperSource.ARXIV_URL,
        source_url="https://arxiv.org/abs/1234.56789",  # type: ignore[arg-type]
        pdf_storage_path="mock/path.pdf",
        metadata=None,
        user_id=None,
        is_public=False,
        published_at=None,
        imported_from_paper_id=None,
    )

    with patch(
        "pipeline.services.paper_service.PaperService.list_papers",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = [PaperListItem(paper=mock_paper, latest_run=None)]
        response = test_client.get("/api/v1/papers")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 1
    assert response.json()[0]["paper"]["id"] == str(paper_id)


def test_get_paper_success(test_client: TestClient):
    """Test GET /api/v1/papers/{paper_id} success"""
    paper_id = uuid.uuid4()
    mock_paper = Paper(
        id=paper_id,
        source=PaperSource.DOI,
        source_url="https://doi.org/10.1234/test",  # type: ignore[arg-type]
        pdf_storage_path="mock/path.pdf",
        metadata=None,
        user_id=None,
        is_public=False,
        published_at=None,
        imported_from_paper_id=None,
    )

    with patch(
        "pipeline.services.paper_service.PaperService.get_paper", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_paper
        response = test_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(paper_id)
    assert response.json()["source"] == "doi"


def test_get_paper_not_found(test_client: TestClient):
    """Test GET /api/v1/papers/{paper_id} when not found"""
    paper_id = uuid.uuid4()

    with patch(
        "pipeline.services.paper_service.PaperService.get_paper", new_callable=AsyncMock
    ) as mock_get:
        mock_get.side_effect = ValueError("Paper not found")
        response = test_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_upload_paper_pdf(test_client: TestClient, pdf_bytes: bytes):
    """Test POST /api/v1/papers/upload"""
    paper_id = uuid.uuid4()
    mock_paper = Paper(
        id=paper_id,
        source=PaperSource.PDF_UPLOAD,
        source_url=None,
        pdf_storage_path=f"papers/{paper_id}_test.pdf",
        metadata=None,
        user_id=None,
        is_public=False,
        published_at=None,
        imported_from_paper_id=None,
    )

    with patch(
        "pipeline.services.paper_service.PaperService.create_from_upload",
        new_callable=AsyncMock,
    ) as mock_upload:
        mock_upload.return_value = mock_paper
        response = test_client.post(
            "/api/v1/papers/upload",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["id"] == str(paper_id)
    assert response.json()["source"] == "pdf_upload"


def test_delete_paper(test_client: TestClient):
    """Test DELETE /api/v1/papers/{paper_id}"""
    paper_id = uuid.uuid4()

    with patch(
        "pipeline.services.paper_service.PaperService.delete_paper",
        new_callable=AsyncMock,
    ) as mock_delete:
        response = test_client.delete(f"/api/v1/papers/{paper_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_delete.assert_called_once_with(paper_id)


def test_get_paper_outputs_includes_extraction(test_client: TestClient):
    paper_id = uuid.uuid4()
    bundle = OutputBundle(
        paper_id=paper_id,
        summaries=[],
        diagrams=[],
        code=None,
        report=None,
        extraction=AiMlExtraction(
            task="machine translation",
            problem_statement="Improve sequence transduction quality.",
            key_contributions=["attention-only encoder-decoder"],
            architecture_components=[],
            datasets=[],
            evaluation_metrics=[],
        ),
    )

    with patch(
        "pipeline.services.export_service.ExportService.get_output_bundle",
        new_callable=AsyncMock,
    ) as mock_bundle:
        mock_bundle.return_value = bundle
        response = test_client.get(f"/api/v1/papers/{paper_id}/outputs")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["extraction"]["task"] == "machine translation"


def test_get_code_source_missing_returns_404(test_client: TestClient):
    paper_id = uuid.uuid4()
    with patch(
        "pipeline.services.export_service.ExportService.get_code_file",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = ValueError("No code_python found for paper")
        response = test_client.get(f"/api/v1/papers/{paper_id}/outputs/code.py")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_notebook_missing_returns_404(test_client: TestClient):
    paper_id = uuid.uuid4()
    with patch(
        "pipeline.services.export_service.ExportService.get_notebook",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = ValueError("No code_notebook found for paper")
        response = test_client.get(f"/api/v1/papers/{paper_id}/outputs/notebook.ipynb")
    assert response.status_code == status.HTTP_404_NOT_FOUND
