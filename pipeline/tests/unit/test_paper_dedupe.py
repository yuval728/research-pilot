from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["DEBUG"] = "false"

from src.services.paper_service import PaperService


def _paper_orm_with_identifier(
    *,
    arxiv_id: str | None = None,
    doi: str | None = None,
) -> MagicMock:
    orm = MagicMock()
    orm.id = uuid.uuid4()
    orm.source = "arxiv_url" if arxiv_id else "doi"
    orm.source_url = (
        "https://arxiv.org/abs/1706.03762" if arxiv_id else "https://doi.org/10.1/test"
    )
    orm.pdf_storage_path = None
    orm.metadata_ = {
        "title": "Attention Is All You Need",
        "authors": ["A", "B"],
        "abstract": None,
        "venue": None,
        "year": 2017,
        "arxiv_id": arxiv_id,
        "doi": doi,
        "page_count": None,
        "domain": None,
        "sub_domain": None,
    }
    orm.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    orm.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return orm


@pytest.mark.asyncio
async def test_create_from_arxiv_returns_existing_paper_on_duplicate() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    svc = PaperService(db)
    existing = _paper_orm_with_identifier(arxiv_id="1706.03762")

    with patch.object(
        svc, "_find_existing_by_metadata_identifier", new_callable=AsyncMock
    ) as mock_find:
        mock_find.return_value = existing
        result = await svc.create_from_arxiv("https://arxiv.org/abs/1706.03762")

    assert str(result.id) == str(existing.id)
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_create_from_doi_returns_existing_paper_on_duplicate() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    svc = PaperService(db)
    existing = _paper_orm_with_identifier(doi="10.1145/test.case")

    with patch.object(
        svc, "_find_existing_by_metadata_identifier", new_callable=AsyncMock
    ) as mock_find:
        mock_find.return_value = existing
        result = await svc.create_from_doi("10.1145/TEST.CASE")

    assert str(result.id) == str(existing.id)
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_create_from_arxiv_creates_when_not_duplicate() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    created = _paper_orm_with_identifier(arxiv_id="1706.03762")

    def _fake_results(_search):
        yield SimpleNamespace(
            title="Attention Is All You Need",
            authors=["A", "B"],
            summary="Abstract",
            published=SimpleNamespace(year=2017),
        )

    with (
        patch.object(
            PaperService,
            "_find_existing_by_metadata_identifier",
            new_callable=AsyncMock,
        ) as mock_find,
        patch("src.services.paper_service.arxiv.Client") as mock_client_cls,
        patch("src.services.paper_service.PaperORM", return_value=created),
    ):
        mock_find.return_value = None
        mock_client = MagicMock()
        mock_client.results.side_effect = _fake_results
        mock_client_cls.return_value = mock_client

        svc = PaperService(db)
        result = await svc.create_from_arxiv("https://arxiv.org/abs/1706.03762")

    assert str(result.id) == str(created.id)
    db.add.assert_called_once()
    db.commit.assert_called_once()
