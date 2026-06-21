"""Scene environment context helpers for RPG Environment 2.0."""
from __future__ import annotations

from typing import Any

DEFAULT_EXPOSURE = "outdoor"
DEFAULT_SHELTER = "exposed"


def normalize_scene_context(
    context: dict[str, Any] | None,
    *,
    location_id: str,
    region_id: str,
    location_label: str | None = None,
) -> dict[str, Any]:
    raw_context = context if isinstance(context, dict) else {}
    return {
        "exposure": str(raw_context.get("exposure") or DEFAULT_EXPOSURE),
        "shelter": str(raw_context.get("shelter") or DEFAULT_SHELTER),
        "light_override": raw_context.get("light_override"),
        "region_id": str(region_id or "starting_region"),
        "location_id": str(location_id or "starting_location"),
        "location_label": str(location_label or location_id or "Starting Location"),
    }
