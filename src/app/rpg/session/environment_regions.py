"""Region-level environment helpers for RPG Environment 2.0."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.rpg.session.environment_snapshot import derive_environment_snapshot
from app.rpg.session.environment_time import advance_environment_time

DEFAULT_ACTIVE_REGION_ID = "active"


def get_active_region_environment(world_state: dict[str, Any]) -> dict[str, Any]:
    world = world_state if isinstance(world_state, dict) else {}
    active_region_id = get_active_region_id(world)
    region_environment = _region_environment(world, active_region_id)
    if region_environment is not None:
        return region_environment
    environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
    return deepcopy(environment)


def derive_active_region_snapshot(
    world_state: dict[str, Any],
    scene_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    environment = get_active_region_environment(world_state)
    return derive_environment_snapshot(environment, scene_context)


def switch_active_region(world_state: dict[str, Any], region_id: str) -> dict[str, Any]:
    world = deepcopy(world_state) if isinstance(world_state, dict) else {}
    environment = dict(world.get("environment")) if isinstance(world.get("environment"), dict) else {}
    environment["active_region_id"] = str(region_id or DEFAULT_ACTIVE_REGION_ID)
    world["environment"] = environment
    return world


def advance_region_environments(
    world_state: dict[str, Any],
    *,
    active_elapsed_minutes: int,
    offscreen_elapsed_minutes: int | None = None,
) -> dict[str, Any]:
    world = deepcopy(world_state) if isinstance(world_state, dict) else {}
    regions = world.get("regions") if isinstance(world.get("regions"), dict) else None
    if not regions:
        environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
        world["environment"] = advance_environment_time(environment, elapsed_minutes=active_elapsed_minutes)
        return world

    active_region_id = get_active_region_id(world)
    offscreen_elapsed = active_elapsed_minutes if offscreen_elapsed_minutes is None else offscreen_elapsed_minutes
    next_regions: dict[str, dict[str, Any]] = {}
    for region_id, region_payload in regions.items():
        if not isinstance(region_payload, dict):
            continue
        region = deepcopy(region_payload)
        region_environment = region.get("environment") if isinstance(region.get("environment"), dict) else None
        if region_environment is not None:
            elapsed = active_elapsed_minutes if region_id == active_region_id else offscreen_elapsed
            region["environment"] = advance_environment_time(region_environment, elapsed_minutes=elapsed)
        next_regions[str(region_id)] = region
    world["regions"] = next_regions
    return world


def get_active_region_id(world_state: dict[str, Any]) -> str:
    world = world_state if isinstance(world_state, dict) else {}
    environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
    active_region_id = environment.get("active_region_id") or environment.get("region_id")
    return str(active_region_id or DEFAULT_ACTIVE_REGION_ID)


def _region_environment(world_state: dict[str, Any], region_id: str) -> dict[str, Any] | None:
    regions = world_state.get("regions") if isinstance(world_state.get("regions"), dict) else {}
    region = regions.get(region_id) if isinstance(regions.get(region_id), dict) else None
    if not region:
        return None
    environment = region.get("environment") if isinstance(region.get("environment"), dict) else None
    return deepcopy(environment) if environment is not None else None
