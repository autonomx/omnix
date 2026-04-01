"""
Event Bus - Core event system for the RPG.

Provides a queue-based event distribution system where:
- Events are published (queued) rather than immediately processed
- Systems subscribe to specific event types or wildcard "*"
- Events are processed in batch at the end of each game tick
- Priority-based handler ordering for deterministic execution

This architecture provides:
- Decoupled systems (no direct dependencies between subsystems)
- Deterministic simulation order (priority-based handler execution)
- Extensibility (add new systems without modifying core)
- Debug/Replay capability via event log
- Safety (immutable events, tick-bound processing, schema validation)
"""

from collections import defaultdict, deque
from types import MappingProxyType
from typing import Callable, Dict, List, Any, Tuple


# Event schema: required fields per event type
REQUIRED_FIELDS = {
    "damage": ["type", "source", "target", "amount"],
    "death": ["type", "target"],
    "move": ["type", "source", "position"],
    "heal": ["type", "source", "target", "amount"],
}


class EventBus:
    def __init__(self):
        # Store (priority, handler) tuples, sorted by priority on insert
        self._subscribers: Dict[str, List[Tuple[int, Callable]]] = defaultdict(list)
        # Use deque for O(1) popleft
        self._queue: deque = deque()

    def subscribe(self, event_type: str, handler: Callable, priority: int = 0):
        """Subscribe a handler to an event type.
        
        Args:
            event_type: The type of event to listen for. Use "*" for wildcard (all events).
            handler: Callback function with signature (session, event).
            priority: Lower priority runs first. Examples:
                combat = -10  (mutates state early)
                emotion = 0
                memory = 10   (records final state)
        """
        self._subscribers[event_type].append((priority, handler))
        # Keep sorted by priority for deterministic ordering
        self._subscribers[event_type].sort(key=lambda x: x[0])

    def publish(self, event: Dict[str, Any]):
        """Publish an event (adds to queue, not immediate execution).
        
        Args:
            event: A dictionary with at least a "type" key.
            
        Raises:
            ValueError: If the event is missing required fields for its type.
        """
        # Validate event schema
        etype = event.get("type")
        if etype in REQUIRED_FIELDS:
            for field in REQUIRED_FIELDS[etype]:
                if field not in event:
                    raise ValueError(f"Missing field '{field}' in event '{etype}'")
        
        # Freeze event to prevent mutation by handlers (immutable)
        self._queue.append(MappingProxyType(dict(event)))

    def process(self, session):
        """Process all queued events by dispatching to subscribed handlers.
        
        This should be called exactly once at the end of each game tick.
        Uses tick-bound processing: new events during processing go to next tick.
        
        Args:
            session: The current game session (passed to handlers).
        """
        # Tick-bound: only process current batch, new events go to next tick
        current_batch = list(self._queue)
        self._queue.clear()

        for event in current_batch:
            # Dispatch to specific event type handlers + wildcard handlers
            handlers = (
                self._subscribers.get(event.get("type", ""), []) +
                self._subscribers.get("*", [])
            )

            # Sort combined handlers by priority to maintain deterministic ordering
            # (specific + wildcard lists are individually sorted but combined list is not)
            handlers = sorted(handlers, key=lambda x: x[0])
            
            for _, handler in handlers:
                handler(session, event)

    def clear(self):
        """Clear all pending events in the queue."""
        self._queue.clear()