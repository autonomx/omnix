"""Core Event Bus — Central event communication for the RPG system.

PHASE 1 — STABILIZE:
This module implements the EventBus as specified in rpg-design.txt Step 2.
It provides a simple, decoupled event system where all cross-system
communication flows through events rather than direct method calls.

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.

Usage:
    bus = EventBus()
    bus.emit(Event("relationship_changed", {"npc_id": 1, "target_id": 2, "delta": 0.1}))
    events = bus.collect()  # Returns and clears all pending events
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import inspect


@dataclass
class Event:
    """A single game event with a type and payload.

    Attributes:
        type: The event type/name (e.g., "relationship_changed", "combat_started").
        payload: Dictionary containing event-specific data.
    """
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Event(type={self.type!r}, payload={self.payload!r})"


class EventBus:
    """Central event bus for decoupled system communication.

    This implements the EventBus pattern from rpg-design.txt:
    - Systems emit events instead of directly calling other systems
    - Events are collected and processed in batch per game tick
    - Provides a clean separation of concerns between subsystems

    Attributes:
        _events: Internal list of pending events.
        _log: Optional log of all events ever emitted (for debugging).
        _enforce: If True, development-time enforcement checks are active.
    """

    def __init__(self, debug: bool = False, enforce: bool = False):
        """Initialize the EventBus.

        Args:
            debug: If True, log all events for debugging purposes.
            enforce: If True, enable development-time enforcement to detect misuse.
        """
        self._events: List[Event] = []
        self._log: Optional[List[Event]] = [] if debug else None
        self._debug = debug
        self._enforce = enforce

    def emit(self, event: Event) -> None:
        """Emit an event (adds to the internal queue).

        This is the ONLY way systems should communicate across boundaries.
        Instead of: world.update_relationship(npc_id, target_id, delta)
        Use: bus.emit(Event("relationship_changed", {...}))

        Args:
            event: The event to emit.
        """
        self.assert_event_usage()

        if self._debug:
            print(f"[EVENT] {event.type} -> {event.payload}")

        if self._log is not None:
            self._log.append(event)

        self._events.append(event)

    def collect(self) -> List[Event]:
        """Collect and clear all pending events.

        This should be called once per game tick by the GameLoop.
        Returns a snapshot of events, then clears the internal queue.

        Returns:
            List of all events emitted since last collect() call.
        """
        events = self._events[:]
        self._events.clear()
        return events

    def peek(self) -> List[Event]:
        """Peek at pending events without clearing them.

        Returns:
            List of all pending events (does not modify internal state).
        """
        return self._events[:]

    def clear(self) -> None:
        """Clear all pending events without processing them."""
        self._events.clear()

    @property
    def pending_count(self) -> int:
        """Number of events currently in the queue."""
        return len(self._events)

    @property
    def log(self) -> Optional[List[Event]]:
        """Access the event log (if debug mode is enabled).

        Returns:
            List of all events ever emitted, or None if not in debug mode.
        """
        return self._log

    def reset(self) -> None:
        """Reset the bus state (clears queue and log)."""
        self._events.clear()
        if self._log is not None:
            self._log.clear()

    def assert_event_usage(self):
        """Development-time enforcement to detect misuse."""
        if not self._enforce:
            return

        stack = inspect.stack()
        for frame in stack:
            module = inspect.getmodule(frame[0])
            if not module:
                continue

            name = module.__name__

            # Allow core + event_bus
            if "core.event_bus" in name:
                continue

            # Detect suspicious direct calls (future extension point)
            # For now, this is a placeholder hook