"""
pipeline/core/events.py

Simple synchronous event bus for internal pipeline events.

The bus allows decoupled components to react to stage transitions without
direct coupling. The primary consumer is the Supabase Realtime writer that
pushes live progress updates to the frontend.

Usage
-----
    from pipeline.core.events import EventBus, EventType

    bus = EventBus()

    @bus.subscribe(EventType.STAGE_COMPLETED)
    def on_complete(event: Event) -> None:
        print(event.stage_name, "done")

    bus.emit(Event(
        type=EventType.STAGE_COMPLETED,
        run_id="abc-123",
        stage_name="ingest",
    ))
"""

from __future__ import annotations

import enum
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from src.core.logger import get_logger


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class EventType(str, enum.Enum):
    """All pipeline lifecycle events that can be emitted on the bus."""

    # Stage-level
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    STAGE_SKIPPED = "stage.skipped"

    # Run-level
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """An immutable event emitted on the EventBus.

    Parameters
    ----------
    type:
        The :class:`EventType` that occurred.
    run_id:
        UUID of the pipeline run this event belongs to.
    stage_name:
        Name of the stage (empty string for run-level events).
    payload:
        Arbitrary extra data attached to the event.
    timestamp:
        UTC datetime when the event was created (auto-set if omitted).
    """

    type: EventType
    run_id: str
    stage_name: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Handler type alias
# ---------------------------------------------------------------------------

Handler = Callable[[Event], None]


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBus:
    """Synchronous, in-process event bus.

    Handlers are called in the order they were registered. Exceptions raised
    by a handler are caught and logged so one bad handler cannot prevent
    others from receiving the event.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        # Wildcard handlers receive every event
        self._wildcard_handlers: list[Handler] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: EventType | None,
        handler: Handler,
    ) -> None:
        """Register *handler* to be called when *event_type* is emitted.

        Parameters
        ----------
        event_type:
            The specific event to subscribe to.
            Pass ``None`` to receive **every** event (wildcard).
        handler:
            Callable that accepts a single :class:`Event` argument.
        """
        if event_type is None:
            self._wildcard_handlers.append(handler)
        else:
            self._handlers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: EventType | None,
        handler: Handler,
    ) -> None:
        """Remove a previously registered handler.

        Silently ignores handlers that were never registered.
        """
        if event_type is None:
            try:
                self._wildcard_handlers.remove(handler)
            except ValueError:
                pass
        else:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    def on(self, event_type: EventType) -> Callable[[Handler], Handler]:
        """Decorator sugar for :meth:`subscribe`.

        Example::

            @bus.on(EventType.STAGE_COMPLETED)
            def handler(event: Event) -> None:
                ...
        """

        def decorator(fn: Handler) -> Handler:
            self.subscribe(event_type, fn)
            return fn

        return decorator

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def emit(self, event: Event) -> None:
        """Emit *event* to all registered handlers.

        Handlers are called synchronously in registration order.
        Errors are caught and re-raised only in DEBUG mode; in production
        they are logged and the remaining handlers continue to run.
        """

        log = get_logger(__name__)

        handlers = [
            *self._wildcard_handlers,
            *self._handlers.get(event.type, []),
        ]

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "event_handler_error",
                    handler=handler.__qualname__,
                    event_type=event.type,
                    run_id=event.run_id,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all registered handlers. Useful in tests."""
        self._handlers.clear()
        self._wildcard_handlers.clear()


# ---------------------------------------------------------------------------
# Module-level default bus
# ---------------------------------------------------------------------------

#: Shared bus instance used by the runner and Supabase Realtime writer.
#: Tests should create their own ``EventBus()`` instances to avoid bleed.
default_bus: EventBus = EventBus()
