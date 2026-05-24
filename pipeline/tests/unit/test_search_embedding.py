from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["DEBUG"] = "false"

from src.core.exceptions import StageError
from src.core.exceptions import EmbeddingError
from src.graph.state import PipelineState
from src.services.paper_service import PaperService


@pytest.mark.asyncio
async def test_search_papers_requests_fixed_embedding_dimension() -> None:
    db = AsyncMock()
    db_result = MagicMock()
    db_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=db_result)

    svc = PaperService(db)
    with patch(
        "src.services.paper_service.aembedding", new_callable=AsyncMock
    ) as mock_embed:
        mock_embed.return_value = SimpleNamespace(data=[{"embedding": [0.1] * 1536}])
        await svc.search_papers("transformer", limit=3)

    assert mock_embed.await_args is not None
    assert mock_embed.await_args.kwargs["dimensions"] == 1536


@pytest.mark.asyncio
async def test_search_papers_raises_embedding_error_on_dimension_mismatch() -> None:
    db = AsyncMock()
    svc = PaperService(db)

    with patch(
        "src.services.paper_service.aembedding", new_callable=AsyncMock
    ) as mock_embed:
        mock_embed.return_value = SimpleNamespace(data=[{"embedding": [0.1] * 3072}])
        with pytest.raises(
            EmbeddingError, match="Failed to generate a valid query embedding"
        ):
            await svc.search_papers("transformer", limit=3)


@pytest.mark.asyncio
async def test_ingest_existing_paper_missing_source_raises_typed_stage_error() -> None:
    from src.graph.nodes.ingest import ingest_node

    state: PipelineState = {
        "run_id": str(uuid.uuid4()),
        "paper_id": str(uuid.uuid4()),
        "pdf_storage_path": None,
        "paper_metadata": None,
        "pdf_bytes": None,
        "stage_statuses": {},
        "token_usage": {},
        "errors": [],
        "cached_stages": set(),
    }

    with pytest.raises(StageError, match="Failed to fetch PDF for existing paper"):
        await ingest_node(state)
