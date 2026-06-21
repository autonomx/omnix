"""Tracking and exploration read model for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any


def build_tracking_environment_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    return {
        "source": "environment_snapshot",
        "terrain_condition": str(safe_snapshot.get("terrain_condition") or "firm_ground"),
        "visibility": str(safe_snapshot.get("visibility") or "normal"),
        "light_level": str(safe_snapshot.get("light_level") or "daylight"),
        "footprint_visibility": "normal",
        "evidence_persistence": "normal",
        "long_distance_perception": "normal",
        "notes": [],
    }
