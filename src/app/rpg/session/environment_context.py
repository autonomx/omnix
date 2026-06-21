"""Scene environment context helpers for RPG Environment 2.0."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_EXPOSURE = "outdoor"
DEFAULT_SHELTER = "exposed"
VALID_EXPOSURES = {"indoor", "outdoor", "sheltered", "underground"}

STARTING_LOCATION_CONTEXTS: dict[str, dict[str, Any]] = {
    "rusty_flagon_tavern": {"exposure": "indoor", "shelter": "sheltered", "light_override": "tavern_lit"},
    "market_district": {"exposure": "outdoor", "shelter": "partly_sheltered"},
    "northern_road": {"exposure": "outdoor", "shelter": "exposed"},
    "glimmerdeep_pass": {"exposure": "outdoor", "shelter": "exposed"},
    "old_quarry": {"exposure": "outdoor", "shelter": "exposed"},
}


def scene_context_for_location(
    location_id: str,
    *,
    region_id: str,
    location_label: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_location_id = _normalize_identifier(location_id, "starting_location")
    merged_context = dict(STARTING_LOCATION_CONTEXTS.get(normalized_location_id, {}))
    if isinstance(context, dict):
        merged_context.update(context)
    return normalize_scene_context(
        merged_context,
        location_id=normalized_location_id,
        region_id=region_id,
        location_label=location_label or normalized_location_id,
    )


def normalize_scene_context(
    context: dict[str, Any] | None,
    *,
    location_id: str,
    region_id: str,
    location_label: str | None = None,
) -> dict[str, Any]:
    raw_context = context if isinstance(context, dict) else {}
    exposure = _normalize_exposure(raw_context.get("exposure"))
    shelter = _normalize_identifier(raw_context.get("shelter"), DEFAULT_SHELTER)
    light_override = raw_context.get("light_override")
    return {
        "exposure": exposure,
        "shelter": shelter,
        "light_override": str(light_override) if light_override else None,
        "region_id": str(region_id or "starting_region"),
        "location_id": _normalize_identifier(location_id, "starting_location"),
        "location_label": str(location_label or location_id or "Starting Location"),
    }


def transition_scene_context(
    state: dict[str, Any],
    *,
    location_id: str,
    region_id: str | None = None,
    location_label: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    next_state = deepcopy(state) if isinstance(state, dict) else {}
    world = next_state.get("world") if isinstance(next_state.get("world"), dict) else {}
    scene = dict(next_state.get("scene")) if isinstance(next_state.get("scene"), dict) else {}
    environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
    previous = scene.get("environment_context") if isinstance(scene.get("environment_context"), dict) else {}
    next_region_id = region_id or previous.get("region_id") or environment.get("region_id") or "starting_region"
    next_location_label = location_label or location_id
    scene["environment_context"] = scene_context_for_location(
        location_id,
        region_id=str(next_region_id),
        location_label=str(next_location_label),
        context=context,
    )
    next_state["scene"] = scene
    return next_state


def _normalize_exposure(value: Any) -> str:
    exposure = _normalize_identifier(value, DEFAULT_EXPOSURE)
    return exposure if exposure in VALID_EXPOSURES else DEFAULT_EXPOSURE


def _normalize_identifier(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = "_".join(part for part in text.split("_") if part)
    return text or fallback
