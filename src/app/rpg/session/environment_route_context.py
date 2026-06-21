"""Route-facing read model for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any


def build_route_environment_context(snapshot: dict[str, Any] | None, *, base_minutes: int) -> dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    return {
        "source": "environment_snapshot",
        "terrain_condition": str(safe_snapshot.get("terrain_condition") or "firm_ground"),
        "visibility": str(safe_snapshot.get("visibility") or "normal"),
        "base_minutes": max(0, int(base_minutes)),
        "estimated_minutes": max(0, int(base_minutes)),
        "notes": [],
    }
