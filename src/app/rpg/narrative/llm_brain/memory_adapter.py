"""Memory Adapter - Reduces world state to token-efficient summary. TIER 19."""
from __future__ import annotations

from typing import Any, Dict, List

MAX_EVENTS = 10
class NarrativeMemoryAdapter:
    def compress(self, context: Dict[str, Any]) -> Dict[str, Any]:
        world = context.get("world", {})
        story = context.get("story", {})
        arcs = context.get("arcs", "")
        return {"summary": self._sum(world.get("recent_events", [])), "tension": story.get("tension", 0.3), "phase": story.get("phase", "rising"), "arcs": arcs if isinstance(arcs, str) else str(arcs)}
    def _sum(self, events):
        if not events: return "No recent events."
        return "; ".join(e.get("type", "unknown") for e in events[-MAX_EVENTS:])
