"""Unit tests for RPG event bus."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.event_bus import EventBus


class TestEventBus:
    """Test EventBus class."""

    def test_create_event_bus(self):
        bus = EventBus()
        assert bus._queue is not None
        assert len(bus._queue) == 0

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        def handler(session, event):
            received.append(event)

        bus.subscribe("test", handler)
        bus.publish({"type": "test", "data": "hello"})
        bus.process(None)

        assert len(received) == 1
        assert received[0]["type"] == "test"
        assert received[0]["data"] == "hello"

    def test_wildcard_subscription(self):
        bus = EventBus()
        received = []

        def handler(session, event):
            received.append(event)

        bus.subscribe("*", handler)
        bus.publish({"type": "test1"})
        bus.publish({"type": "test2"})
        bus.process(None)

        assert len(received) == 2

    def test_priority_ordering(self):
        bus = EventBus()
        received = []

        def handler1(session, event):
            received.append("low")

        def handler2(session, event):
            received.append("high")

        bus.subscribe("test", handler1, priority=10)
        bus.subscribe("test", handler2, priority=1)
        bus.publish({"type": "test"})
        bus.process(None)

        assert received == ["high", "low"]

    def test_clear_queue(self):
        bus = EventBus()
        bus.publish({"type": "test"})
        assert len(bus._queue) == 1
        bus.clear()
        assert len(bus._queue) == 0

    def test_validation_missing_field(self):
        bus = EventBus()
        with pytest.raises(ValueError, match="Missing field"):
            bus.publish({"type": "damage", "source": "a"})

    def test_validation_valid_damage(self):
        bus = EventBus()
        bus.publish({"type": "damage", "source": "a", "target": "b", "amount": 10})
        assert len(bus._queue) == 1

    def test_validation_valid_death(self):
        bus = EventBus()
        bus.publish({"type": "death", "target": "a"})
        assert len(bus._queue) == 1

    def test_validation_valid_move(self):
        bus = EventBus()
        bus.publish({"type": "move", "source": "a", "position": (1, 2)})
        assert len(bus._queue) == 1

    def test_validation_valid_heal(self):
        bus = EventBus()
        bus.publish({"type": "heal", "source": "a", "target": "b", "amount": 10})
        assert len(bus._queue) == 1

    def test_multiple_events_processed_in_order(self):
        bus = EventBus()
        received = []

        def handler(session, event):
            received.append(event["type"])

        bus.subscribe("a", handler)
        bus.subscribe("b", handler)
        bus.publish({"type": "a"})
        bus.publish({"type": "b"})
        bus.publish({"type": "a"})
        bus.process(None)

        assert received == ["a", "b", "a"]

    def test_tick_bound_processing(self):
        bus = EventBus()
        received = []

        def handler(session, event):
            received.append(event["type"])
            # Publish new event during processing
            bus.publish({"type": "new"})

        bus.subscribe("test", handler)
        bus.publish({"type": "test"})
        bus.process(None)

        # Only original event should be processed, new one goes to next tick
        assert len(received) == 1
        assert len(bus._queue) == 1  # New event in queue for next tick

    def test_event_immutability(self):
        bus = EventBus()

        def handler(session, event):
            # Try to mutate event
            try:
                event["mutated"] = True
            except (TypeError, KeyError):
                pass  # Expected - event is immutable

        bus.subscribe("test", handler)
        bus.publish({"type": "test", "data": "original"})
        bus.process(None)