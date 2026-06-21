"""NPC schedule read model for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any


def build_npc_schedule_environment_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    return {
        "source": "environment_snapshot",
        "weather_condition": _weather_condition(safe_snapshot),
        "light_level": str(safe_snapshot.get("light_level") or "daylight"),
        "exposure": "outdoor",
        "outdoor_activity": "normal",
        "notes": [],
    }


def _weather_condition(snapshot: dict[str, Any]) -> str:
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    return str(weather.get("condition") or "clear")
