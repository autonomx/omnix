"""NPC schedule read model for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any

SEVERE_WEATHER = {"storm", "blizzard", "heavy_rain"}
LOW_LIGHT = {"night", "deep_night", "dark", "dim"}


def build_npc_schedule_environment_context(
    snapshot: dict[str, Any] | None,
    *,
    prefers_indoor: bool = False,
    prefers_daylight: bool = False,
) -> dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    condition = _weather_condition(safe_snapshot)
    light = str(safe_snapshot.get("light_level") or "daylight")
    exposure = _scene_value(safe_snapshot, "exposure", "outdoor")
    notes = _schedule_notes(condition, light, exposure, prefers_indoor, prefers_daylight)
    return {
        "source": "environment_snapshot",
        "weather_condition": condition,
        "light_level": light,
        "exposure": exposure,
        "outdoor_activity": _outdoor_activity(condition, exposure),
        "notes": notes,
    }


def _outdoor_activity(condition: str, exposure: str) -> str:
    if exposure == "indoor":
        return "not_currently_outdoor"
    if condition in SEVERE_WEATHER:
        return "discouraged"
    return "normal"


def _schedule_notes(
    condition: str,
    light: str,
    exposure: str,
    prefers_indoor: bool,
    prefers_daylight: bool,
) -> list[str]:
    notes: list[str] = []
    if condition in SEVERE_WEATHER:
        notes.append("storm_limits_outdoor_activity")
    if light in LOW_LIGHT:
        notes.append("night_context")
    if prefers_indoor and exposure != "indoor":
        notes.append("prefers_indoor_context")
    if prefers_daylight and light in LOW_LIGHT:
        notes.append("prefers_daylight_context")
    return notes


def _weather_condition(snapshot: dict[str, Any]) -> str:
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    return str(weather.get("condition") or "clear")


def _scene_value(snapshot: dict[str, Any], key: str, fallback: str) -> str:
    context = snapshot.get("context") if isinstance(snapshot.get("context"), dict) else {}
    return str(context.get(key) or fallback)
