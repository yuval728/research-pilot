"""
tests/integration/test_search.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration tests for the Search API.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from src.core.exceptions import EmbeddingError
from src.models.paper import Paper, PaperSource


def test_search_papers(test_client: TestClient):
    """Test GET /api/v1/search"""
    paper_id = uuid.uuid4()
    mock_paper = Paper(
        id=paper_id,
        source=PaperSource.ARXIV_URL,
        source_url="https://arxiv.org/abs/1234.56789",  # type: ignore[arg-type]
        pdf_storage_path="mock/path.pdf",
        metadata=None,
    )

    with patch(
        "pipeline.services.paper_service.PaperService.search_papers",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = [mock_paper]
        response = test_client.post(
            "/api/v1/search", json={"query": "attention mechanism", "limit": 5}
        )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == str(paper_id)


def test_search_papers_empty(test_client: TestClient):
    """Test GET /api/v1/search with no results"""
    with patch(
        "pipeline.services.paper_service.PaperService.search_papers",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = []
        response = test_client.post("/api/v1/search", json={"query": "nonexistent"})

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 0


def test_search_papers_embedding_error_returns_structured_payload(
    test_client: TestClient,
):
    with patch(
        "src.services.paper_service.PaperService.search_papers",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.side_effect = EmbeddingError(
            "Failed to generate a valid query embedding.",
            model="gemini/text-embedding-004",
        )
        response = test_client.post("/api/v1/search", json={"query": "transformer"})

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    payload = response.json()
    assert payload["error"] == "EmbeddingError"
    assert payload["message"] == "Failed to generate a valid query embedding."
