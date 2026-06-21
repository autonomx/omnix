"""Tracking and exploration read model for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any

TRACK_FRIENDLY_TERRAIN = {"muddy", "slush", "deep_snow", "snowpack"}
LOW_VISIBILITY = {"poor", "low", "reduced", "obscured", "interior"}
LOW_LIGHT = {"night", "deep_night", "dark", "dim", "tavern_lit"}


def build_tracking_environment_context(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
    terrain = str(safe_snapshot.get("terrain_condition") or "firm_ground")
    visibility = str(safe_snapshot.get("visibility") or "normal")
    light = str(safe_snapshot.get("light_level") or "daylight")
    condition = _weather_condition(safe_snapshot)
    footprint_visibility = _footprint_visibility(terrain=terrain, condition=condition)
    evidence_persistence = _evidence_persistence(terrain=terrain, condition=condition)
    perception = "reduced" if visibility in LOW_VISIBILITY or light in LOW_LIGHT else "normal"
    return {
        "source": "environment_snapshot",
        "terrain_condition": terrain,
        "weather_condition": condition,
        "visibility": visibility,
        "light_level": light,
        "footprint_visibility": footprint_visibility,
        "evidence_persistence": evidence_persistence,
        "long_distance_perception": perception,
        "notes": _tracking_notes(
            terrain=terrain,
            condition=condition,
            visibility=visibility,
            light=light,
            footprint_visibility=footprint_visibility,
            evidence_persistence=evidence_persistence,
        ),
    }


def _footprint_visibility(*, terrain: str, condition: str) -> str:
    if terrain in TRACK_FRIENDLY_TERRAIN:
        return "strong"
    if condition in {"rain", "snow"}:
        return "moderate"
    return "normal"


def _evidence_persistence(*, terrain: str, condition: str) -> str:
    if condition == "rain":
        return "short"
    if terrain in {"deep_snow", "snowpack"}:
        return "long"
    if condition in {"storm", "snow", "blizzard"}:
        return "reduced"
    return "normal"


def _tracking_notes(
    *,
    terrain: str,
    condition: str,
    visibility: str,
    light: str,
    footprint_visibility: str,
    evidence_persistence: str,
) -> list[str]:
    notes: list[str] = []
    if footprint_visibility == "strong":
        notes.append("terrain_preserves_tracks")
    if evidence_persistence in {"short", "reduced"}:
        notes.append("weather_reduces_evidence")
    if visibility in LOW_VISIBILITY:
        notes.append("low_visibility_limits_perception")
    if light in LOW_LIGHT:
        notes.append("low_light_limits_perception")
    notes.append(f"context:{terrain}:{condition}")
    return notes


def _weather_condition(snapshot: dict[str, Any]) -> str:
    weather = snapshot.get("weather") if isinstance(snapshot.get("weather"), dict) else {}
    return str(weather.get("condition") or "clear")
