"""
pipeline.graph.nodes._base
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared utilities for pipeline graph nodes.

Eliminates boilerplate duplication across all 8 node files by providing:
- Cached Jinja2 environment singleton
- Prompt template caching (avoids disk I/O on every LLM call)
- Common state unpacking helper
- Standardised error handling and event emission
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from jinja2 import Environment

from src.core.config import get_settings
from src.core.events import Event, EventType, default_bus
from src.core.logger import get_logger
from src.graph.state import PipelineState
from src.models.run import StageStatus

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Jinja2 Environment singleton (Issue #13)
# ---------------------------------------------------------------------------

_JINJA_ENV = Environment(autoescape=False)


def get_jinja_env() -> Environment:
    """Return the shared Jinja2 Environment singleton."""
    return _JINJA_ENV


# ---------------------------------------------------------------------------
# Prompt template cache (Issue #11)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=16)
def load_prompt_template(path: Path) -> str:
    """Load and cache a prompt template from disk.

    Templates are static files that never change during a process's lifetime,
    so reading them once and caching is safe.
    """
    return path.read_text(encoding="utf-8")


def render_prompt(template_path: Path, **context: Any) -> str:
    """Load a cached template and render it with the given context."""
    raw = load_prompt_template(template_path)
    template = _JINJA_ENV.from_string(raw)
    return template.render(**context)


# ---------------------------------------------------------------------------
# Common state unpacking (Issue #15)
# ---------------------------------------------------------------------------


class NodeContext:
    """Unpacks common fields from PipelineState to reduce boilerplate.

    Every node file was duplicating the same ~10 lines of state unpacking.
    """

    def __init__(self, state: PipelineState, stage_name: str) -> None:
        self.stage_name = stage_name
        self.run_id: str = state["run_id"]
        self.paper_id: str | None = state.get("paper_id")
        self.errors: list[str] = list(state.get("errors", []))
        self.stage_statuses: dict[str, StageStatus] = dict(
            state.get("stage_statuses", {})
        )
        self.token_usage: dict[str, int] = dict(state.get("token_usage", {}))
        self.cached_stages: set[str] = set(state.get("cached_stages", set()))
        self._settings = None

    @property
    def settings(self):
        """Lazy-loaded settings to avoid redundant get_settings() calls (Issue #22)."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    def mark_running(self) -> None:
        """Set stage status to RUNNING and log start."""
        self.stage_statuses[self.stage_name] = StageStatus.RUNNING
        log.info(
            f"{self.stage_name}_node.started",
            run_id=self.run_id,
            paper_id=self.paper_id,
        )

    def mark_completed(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Set stage status to COMPLETED and emit event."""
        self.stage_statuses[self.stage_name] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=self.run_id,
                stage_name=self.stage_name,
                payload=payload or {},
            )
        )
        return self._base_return()

    def mark_cached(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Set stage status to CACHED and emit event."""
        self.stage_statuses[self.stage_name] = StageStatus.CACHED
        self.cached_stages.add(self.stage_name)
        log.info(f"{self.stage_name}_node.cache_hit", run_id=self.run_id)
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=self.run_id,
                stage_name=self.stage_name,
                payload=payload or {"cached": True},
            )
        )
        return self._base_return()

    def mark_skipped(self, reason: str) -> dict[str, Any]:
        """Set stage status to SKIPPED with a reason."""
        msg = f"[{self.stage_name}] {reason}"
        self.errors.append(msg)
        self.stage_statuses[self.stage_name] = StageStatus.SKIPPED
        log.warning(
            f"{self.stage_name}_node.skipped", run_id=self.run_id, reason=reason
        )
        return self._base_return()

    def mark_failed(self, exc: Exception) -> dict[str, Any]:
        """Set stage status to FAILED, log, and emit event."""
        msg = f"[{self.stage_name}] {exc}"
        self.errors.append(msg)
        self.stage_statuses[self.stage_name] = StageStatus.FAILED
        log.exception(
            f"{self.stage_name}_node.failed", run_id=self.run_id, error=str(exc)
        )
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=self.run_id,
                stage_name=self.stage_name,
                payload={"error": str(exc)},
            )
        )
        return self._base_return()

    def _base_return(self) -> dict[str, Any]:
        """Return the common state fields that every node must include."""
        return {
            "stage_statuses": self.stage_statuses,
            "token_usage": self.token_usage,
            "cached_stages": self.cached_stages,
            "errors": self.errors,
        }
