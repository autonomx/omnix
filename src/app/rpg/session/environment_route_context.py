"""Route-facing read model for RPG Environment 2.0."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.rpg.session.environment_time import advance_environment_time

DIFFICULT_TERRAIN = {"muddy", "deep_snow", "slush", "dusty"}
LOW_VISIBILITY = {"poor", "low", "reduced", "obscured", "dark"}
LOW_LIGHT = {"night", "deep_night", "dark", "dim", "tavern_lit"}


def build_route_environment_context(snapshot: dict[str, Any] | None, *, base_minutes: int) -> dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    terrain = str(safe_snapshot.get("terrain_condition") or "firm_ground")
    visibility = str(safe_snapshot.get("visibility") or "normal")
    wind = str(safe_snapshot.get("wind") or "calm")
    light = str(safe_snapshot.get("light_level") or "daylight")
    hazards = _hazards(safe_snapshot)
    base = max(0, int(base_minutes))
    estimated = max(0, int(round(base * _route_multiplier(terrain=terrain, hazards=hazards))))
    return {
        "source": "environment_snapshot",
        "terrain_condition": terrain,
        "visibility": visibility,
        "wind": wind,
        "light_level": light,
        "hazards": hazards,
        "base_minutes": base,
        "estimated_minutes": estimated,
        "notes": _route_notes(terrain=terrain, visibility=visibility, light=light, hazards=hazards),
    }


def advance_environment_for_route(environment: dict[str, Any], *, elapsed_minutes: int) -> dict[str, Any]:
    """Pass explicit route elapsed time back to Environment Domain helpers."""

    env = deepcopy(environment) if isinstance(environment, dict) else {}
    return advance_environment_time(env, elapsed_minutes=elapsed_minutes)


def _route_multiplier(*, terrain: str, hazards: list[str]) -> float:
    multiplier = 1.0
    if terrain in DIFFICULT_TERRAIN:
        multiplier += 0.25
    if terrain == "deep_snow":
        multiplier += 0.25
    if hazards:
        multiplier += 0.15
    return multiplier


def _route_notes(*, terrain: str, visibility: str, light: str, hazards: list[str]) -> list[str]:
    notes: list[str] = []
    if terrain in {"muddy", "slush"}:
        notes.append("soft_ground_slows_route")
    if terrain == "deep_snow":
        notes.append("deep_snow_slows_route")
    if visibility in LOW_VISIBILITY:
        notes.append("low_visibility_risk")
    if light in LOW_LIGHT:
        notes.append("low_light_risk")
    for hazard in hazards:
        notes.append(f"hazard:{hazard}")
    return notes


def _hazards(snapshot: dict[str, Any]) -> list[str]:
    raw_hazards = snapshot.get("hazards")
    if not isinstance(raw_hazards, list):
        return []
    return [str(hazard) for hazard in raw_hazards if str(hazard or "").strip()]
