"""
tests/unit/core/test_events.py

Unit tests for pipeline/core/events.py

Tests verify:
- EventBus routes events to correct handlers
- Wildcard handlers receive all events
- Unsubscribe removes handlers correctly
- Failing handlers don't block other handlers
- Event dataclass is immutable and has correct defaults
- default_bus is a shared singleton
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.core.events import Event, EventBus, EventType, default_bus


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


class TestEvent:
    def test_required_fields(self):
        ev = Event(type=EventType.RUN_STARTED, run_id="r1")
        assert ev.type == EventType.RUN_STARTED
        assert ev.run_id == "r1"
        assert ev.stage_name == ""
        assert ev.payload == {}
        assert isinstance(ev.timestamp, datetime)

    def test_timestamp_is_utc(self):
        ev = Event(type=EventType.STAGE_STARTED, run_id="r1", stage_name="ingest")
        assert ev.timestamp.tzinfo is not None

    def test_frozen(self):
        ev = Event(type=EventType.RUN_STARTED, run_id="r1")
        with pytest.raises(
            Exception
        ):  # dataclass frozen=True raises FrozenInstanceError
            ev.run_id = "other"  # type: ignore[misc]

    def test_custom_payload(self):
        ev = Event(
            type=EventType.STAGE_COMPLETED,
            run_id="r2",
            stage_name="extract",
            payload={"tokens": 1234},
        )
        assert ev.payload["tokens"] == 1234


# ---------------------------------------------------------------------------
# EventBus — basic routing
# ---------------------------------------------------------------------------


class TestEventBusRouting:
    def setup_method(self):
        self.bus = EventBus()

    def test_handler_called_on_matching_event(self):
        handler = MagicMock()
        self.bus.subscribe(EventType.STAGE_COMPLETED, handler)

        ev = Event(type=EventType.STAGE_COMPLETED, run_id="r1", stage_name="ingest")
        self.bus.emit(ev)

        handler.assert_called_once_with(ev)

    def test_handler_not_called_on_non_matching_event(self):
        handler = MagicMock()
        self.bus.subscribe(EventType.STAGE_COMPLETED, handler)

        ev = Event(type=EventType.STAGE_FAILED, run_id="r1", stage_name="ingest")
        self.bus.emit(ev)

        handler.assert_not_called()

    def test_multiple_handlers_called_in_order(self):
        calls = []
        self.bus.subscribe(EventType.RUN_STARTED, lambda e: calls.append("a"))
        self.bus.subscribe(EventType.RUN_STARTED, lambda e: calls.append("b"))

        self.bus.emit(Event(type=EventType.RUN_STARTED, run_id="r1"))

        assert calls == ["a", "b"]

    def test_emit_with_no_handlers_does_not_raise(self):
        ev = Event(type=EventType.RUN_COMPLETED, run_id="r1")
        self.bus.emit(ev)  # should not raise


# ---------------------------------------------------------------------------
# Wildcard subscriptions
# ---------------------------------------------------------------------------


class TestWildcardHandlers:
    def setup_method(self):
        self.bus = EventBus()

    def test_wildcard_receives_all_events(self) -> None:
        received: list[EventType] = []
        self.bus.subscribe(None, lambda e: received.append(e.type))

        for et in EventType:
            self.bus.emit(Event(type=et, run_id="r1"))

        assert set(received) == set(EventType)

    def test_wildcard_and_specific_both_called(self):
        wildcard = MagicMock()
        specific = MagicMock()

        self.bus.subscribe(None, wildcard)
        self.bus.subscribe(EventType.STAGE_COMPLETED, specific)

        ev = Event(type=EventType.STAGE_COMPLETED, run_id="r1", stage_name="embed")
        self.bus.emit(ev)

        wildcard.assert_called_once_with(ev)
        specific.assert_called_once_with(ev)


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------


class TestUnsubscribe:
    def setup_method(self):
        self.bus = EventBus()

    def test_unsubscribe_specific_handler(self):
        handler = MagicMock()
        self.bus.subscribe(EventType.STAGE_STARTED, handler)
        self.bus.unsubscribe(EventType.STAGE_STARTED, handler)

        self.bus.emit(Event(type=EventType.STAGE_STARTED, run_id="r1", stage_name="s"))
        handler.assert_not_called()

    def test_unsubscribe_wildcard(self):
        handler = MagicMock()
        self.bus.subscribe(None, handler)
        self.bus.unsubscribe(None, handler)

        self.bus.emit(Event(type=EventType.RUN_STARTED, run_id="r1"))
        handler.assert_not_called()

    def test_unsubscribe_unknown_handler_does_not_raise(self):
        self.bus.unsubscribe(EventType.RUN_STARTED, lambda e: None)  # never subscribed


# ---------------------------------------------------------------------------
# Fault isolation
# ---------------------------------------------------------------------------


class TestFaultIsolation:
    def setup_method(self):
        self.bus = EventBus()

    def test_failing_handler_does_not_block_next(self):
        second = MagicMock()

        def bad_handler(event: Event) -> None:
            raise RuntimeError("handler exploded")

        self.bus.subscribe(EventType.STAGE_COMPLETED, bad_handler)
        self.bus.subscribe(EventType.STAGE_COMPLETED, second)

        ev = Event(type=EventType.STAGE_COMPLETED, run_id="r1", stage_name="s")
        self.bus.emit(ev)  # should not raise

        second.assert_called_once_with(ev)


# ---------------------------------------------------------------------------
# Decorator syntax
# ---------------------------------------------------------------------------


class TestOnDecorator:
    def setup_method(self):
        self.bus = EventBus()

    def test_on_decorator_registers_handler(self):
        received = []

        @self.bus.on(EventType.RUN_FAILED)
        def handler(event: Event) -> None:
            received.append(event.run_id)

        self.bus.emit(Event(type=EventType.RUN_FAILED, run_id="runX"))
        assert received == ["runX"]

    def test_on_decorator_preserves_function(self):
        @self.bus.on(EventType.STAGE_SKIPPED)
        def handler(event: Event) -> None:
            pass

        assert callable(handler)


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_all_handlers(self):
        bus = EventBus()
        bus.subscribe(EventType.RUN_STARTED, MagicMock())
        bus.subscribe(None, MagicMock())

        bus.clear()

        assert bus._handlers == {}
        assert bus._wildcard_handlers == []

    def test_emit_after_clear_does_not_raise(self):
        bus = EventBus()
        bus.subscribe(EventType.RUN_STARTED, MagicMock())
        bus.clear()
        bus.emit(Event(type=EventType.RUN_STARTED, run_id="r1"))


# ---------------------------------------------------------------------------
# Module-level default_bus
# ---------------------------------------------------------------------------


class TestDefaultBus:
    def test_default_bus_is_event_bus(self):
        assert isinstance(default_bus, EventBus)

    def test_default_bus_is_singleton(self):
        from src.core import events as ev_mod

        assert ev_mod.default_bus is default_bus
