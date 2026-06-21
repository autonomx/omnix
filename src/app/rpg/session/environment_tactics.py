"""Combat and stealth read models for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any

RANGED_WIND = {"strong", "severe", "extreme", "gusting"}
LOW_VISIBILITY = {"poor", "low", "reduced", "obscured", "interior"}
LOW_LIGHT = {"night", "deep_night", "dark", "dim"}
NOISY_WEATHER = {"rain", "storm", "snow", "blizzard", "windy"}
DIFFICULT_TERRAIN = {"muddy", "deep_snow", "slush", "dusty"}


def build_tactical_environment_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Return deterministic tactical annotations from an environment snapshot."""

    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    terrain = str(safe_snapshot.get("terrain_condition") or "firm_ground")
    visibility = str(safe_snapshot.get("visibility") or "normal")
    light = str(safe_snapshot.get("light_level") or "daylight")
    wind = str(safe_snapshot.get("wind") or "calm")
    exposure = _scene_value(safe_snapshot, "exposure", "outdoor")
    condition = _weather_condition(safe_snapshot)
    return {
        "source": "environment_snapshot",
        "combat": _combat_context(
            terrain=terrain,
            visibility=visibility,
            light=light,
            wind=wind,
            exposure=exposure,
            condition=condition,
        ),
        "stealth": _stealth_context(
            terrain=terrain,
            visibility=visibility,
            light=light,
            condition=condition,
        ),
    }


def _combat_context(*, terrain: str, visibility: str, light: str, wind: str, exposure: str, condition: str) -> dict[str, Any]:
    notes: list[str] = []
    if wind in RANGED_WIND and exposure != "indoor":
        notes.append("ranged_wind_context")
    if visibility in LOW_VISIBILITY:
        notes.append("limited_visibility_context")
    if terrain in DIFFICULT_TERRAIN:
        notes.append("difficult_terrain_context")
    if exposure == "indoor" and condition in NOISY_WEATHER:
        notes.append("outdoor_weather_indirect_only")
    if light in LOW_LIGHT:
        notes.append("low_light_context")
    return {"wind": wind, "visibility": visibility, "terrain_condition": terrain, "exposure": exposure, "notes": notes}


def _stealth_context(*, terrain: str, visibility: str, light: str, condition: str) -> dict[str, Any]:
    notes: list[str] = []
    if light in LOW_LIGHT:
        notes.append("darkness_aids_stealth")
    if condition in NOISY_WEATHER:
        notes.append("weather_noise_context")
    if terrain in {"muddy", "deep_snow", "slush"}:
        notes.append("terrain_leaves_tracks")
    if visibility in LOW_VISIBILITY:
        notes.append("visibility_cover_context")
    return {"light_level": light, "weather_condition": condition, "terrain_condition": terrain, "notes": notes}


def _weather_condition(snapshot: dict[str, Any]) -> str:
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    return str(weather.get("condition") or "clear")


def _scene_value(snapshot: dict[str, Any], key: str, fallback: str) -> str:
    context = snapshot.get("context") if isinstance(snapshot.get("context"), dict) else {}
    return str(context.get(key) or fallback)
