"""
Helpers for converting stored paper metadata into API models.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from src.models.paper import PaperMetadata


def _metadata_context(paper_id: uuid.UUID | str | None) -> dict[str, str]:
    if paper_id is None:
        return {}
    return {"paper_id": str(paper_id)}


def paper_metadata_dict(
    raw_metadata: Any,
    *,
    paper_id: uuid.UUID | str | None = None,
    log: Any | None = None,
) -> dict[str, Any]:
    """Return object-shaped metadata, or an empty dict for malformed rows."""
    if raw_metadata is None:
        return {}

    if isinstance(raw_metadata, Mapping):
        metadata = dict(raw_metadata)
    elif isinstance(raw_metadata, str):
        try:
            parsed = json.loads(raw_metadata)
        except json.JSONDecodeError:
            if log:
                log.warning(
                    "paper_metadata_invalid_json",
                    metadata_type=type(raw_metadata).__name__,
                    **_metadata_context(paper_id),
                )
            return {}
        if not isinstance(parsed, Mapping):
            if log:
                log.warning(
                    "paper_metadata_not_object",
                    metadata_type=type(parsed).__name__,
                    **_metadata_context(paper_id),
                )
            return {}
        metadata = dict(parsed)
    else:
        if log:
            log.warning(
                "paper_metadata_not_object",
                metadata_type=type(raw_metadata).__name__,
                **_metadata_context(paper_id),
            )
        return {}

    if metadata.get("domain") is None and metadata.get("cls_domain"):
        metadata["domain"] = metadata["cls_domain"]
    if metadata.get("sub_domain") is None and metadata.get("cls_sub_domain"):
        metadata["sub_domain"] = metadata["cls_sub_domain"]

    return metadata


def paper_metadata_model(
    raw_metadata: Any,
    *,
    paper_id: uuid.UUID | str | None = None,
    log: Any | None = None,
) -> PaperMetadata | None:
    """Build ``PaperMetadata`` when stored metadata is complete enough."""
    metadata = paper_metadata_dict(raw_metadata, paper_id=paper_id, log=log)
    if not metadata:
        return None

    try:
        return PaperMetadata(**metadata)
    except (TypeError, ValidationError) as exc:
        if log:
            log.warning(
                "paper_metadata_invalid_shape",
                error=str(exc),
                **_metadata_context(paper_id),
            )
        return None
