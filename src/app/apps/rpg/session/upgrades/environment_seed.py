"""Version 9's environment seed: an older document that has no environment state (E2.0.1) is given one, seeded from
the campaign and where the hero stands; a document that has it keeps it."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.world.environment import _normalize_identifier, _stable_int, build_initial_environment_seed_state


def ensure_session_environment_seed_state(session: dict[str, Any]) -> dict[str, Any]:
    """Attach E2.0.1 environment seed state to session payloads when absent.

    This is intentionally migration-safe: existing environment payloads are left
    untouched, and compatibility fields such as `world.time`, `world.weather`,
    and `world.temperature` remain in place as read-only projections until later
    Environment 2.0 slices replace their consumers.
    """

    state = raw_state if isinstance(raw_state := session.get("state"), dict) else None
    if state is None:
        return session

    world = dict(raw_world) if isinstance(raw_world := state.get("world"), dict) else {}
    scene = dict(raw_scene) if isinstance(raw_scene := state.get("scene"), dict) else {}
    has_environment = isinstance(world.get("environment"), dict)
    has_scene_context = isinstance(scene.get("environment_context"), dict)
    if has_environment and has_scene_context:
        return session

    seed = _session_seed(session, state)
    location_id = _session_location_id(state)
    location = {
        "time_label": world.get("time") or state.get("time") or "Day 1 • 08:00",
        "weather": world.get("weather"),
        "temperature": world.get("temperature"),
        "location": state.get("current_location") or state.get("location") or location_id,
    }
    seeded = build_initial_environment_seed_state(
        campaign_seed=seed,
        campaign_contract=_session_contract(session, state),
        location_id=location_id,
        location=location,
    )
    if not has_environment:
        world["environment"] = seeded["environment"]
    if not has_scene_context:
        scene["environment_context"] = seeded["scene_environment_context"]

    state["world"] = world
    state["scene"] = scene
    session["state"] = state
    return session

def _session_seed(session: dict[str, Any], state: dict[str, Any]) -> int:
    metadata = raw_metadata if isinstance(raw_metadata := state.get("metadata"), dict) else {}
    simulation_state = raw_simulation_state if isinstance(raw_simulation_state := _sections.simulation_state_of(session), dict) else {}
    for value in (metadata.get("seed"), simulation_state.get("seed"), state.get("seed")):
        coerced = _coerce_int(value)
        if coerced is not None:
            return coerced
    session_id = str(session.get("session_id") or session.get("id") or metadata.get("session_id") or "session")
    return _stable_int("session_environment_seed", session_id)

def _session_contract(session: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    setup_payload = raw_setup_payload if isinstance(raw_setup_payload := session.get("setup_payload"), dict) else {}
    metadata = raw_metadata if isinstance(raw_metadata := state.get("metadata"), dict) else {}
    contract = dict(setup_payload)
    if isinstance(setup_payload.get("request"), dict):
        contract.update(setup_payload["request"])
    if isinstance(setup_payload.get("genesis"), dict):
        contract.update(setup_payload["genesis"])
    contract.update({f"metadata_{key}": value for key, value in metadata.items()})
    return contract

def _session_location_id(state: dict[str, Any]) -> str:
    metadata = raw_metadata if isinstance(raw_metadata := state.get("metadata"), dict) else {}
    candidates = (
        state.get("starting_location"),
        metadata.get("starting_location"),
        state.get("current_location"),
        state.get("location"),
    )
    for candidate in candidates:
        normalized = _normalize_identifier(candidate, "")
        if normalized:
            return normalized
    return "starting_location"

def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None
