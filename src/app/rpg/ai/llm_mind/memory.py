"""NPC Memory with Salience-Based Importance and Decay.

Patch 1: Memory Salience + Decay
- Events are scored by importance type (betrayal > gift > idle)
- Old memories decay over time (0.97 multiplier per tick)
- Memory is pruned to max_size, keeping highest-salience events
- Summarize returns structured top-10 memories
"""

from __future__ import annotations

from typing import Any, Dict, List


class NPCMemory:
    """Manages an NPC's event memory with salience-based scoring and decay."""

    # Max events to keep after pruning
    max_size: int = 50

    def __init__(self, max_size: int = 50):
        """Initialize memory.

        Args:
            max_size: Maximum number of events to retain.
        """
        self.events: List[Dict[str, Any]] = []  # [{event, importance, age}]
        self.max_size = max_size

    def remember(self, event: Dict[str, Any]) -> None:
        """Add an event to memory with importance scoring and decay.

        Args:
            event: Event dict with at least a 'type' key.
        """
        importance = self._score(event)
        self.events.append({
            "event": event,
            "importance": importance,
            "age": 0,
        })

        # Apply age increment and decay to all events
        for e in self.events:
            e["age"] += 1
            e["importance"] *= 0.97

        # Sort by importance (descending) and prune
        self.events = sorted(
            self.events,
            key=lambda e: e["importance"],
            reverse=True,
        )[: self.max_size]

    def _score(self, event: Dict[str, Any]) -> float:
        """Compute the salience/importance of an event.

        High-impact events (betrayal, attack) score 1.0
        Medium events (help, gift) score 0.7
        Low events (idle, observe) score 0.3

        Args:
            event: Event dict.

        Returns:
            Importance score between 0.0 and 1.0.
        """
        t = event.get("type", "")
        if t in ("betrayal", "attack", "death", "combat", "damage"):
            return 1.0
        if t in ("help", "gift", "trade", "alliance", "heal"):
            return 0.7
        return 0.3

    def summarize(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return top memories as a structured summary.

        Args:
            limit: Maximum number of memories to return.

        Returns:
            List of dicts with type, actor, target keys.
        """
        return [
            {
                "type": e["event"].get("type"),
                "actor": e["event"].get("actor"),
                "target": e["event"].get("target"),
            }
            for e in self.events[:limit]
        ]

    def get_raw_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return raw event dicts for the top memories.

        Args:
            limit: Maximum events to return.

        Returns:
            List of raw event dicts.
        """
        return [e["event"] for e in self.events[:limit]]

    def clear(self) -> None:
        """Clear all memories."""
        self.events.clear()

    def __len__(self) -> int:
        """Return number of stored events."""
        return len(self.events)

    def __repr__(self) -> str:
        return f"NPCMemory(events={len(self.events)}, max={self.max_size})"