"""Bridge legacy/public player projections into the authoritative simulation.

Older and presentation-first sessions may keep the player wallet and inventory
under ``session.state.player`` while mechanics read ``simulation_state``.  The
bridge copies only missing bootstrap fields into the simulation and projects
authoritative mechanic-owned fields back to the public state after a mutation.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict
from app.apps.rpg.foundation.safe_values import copy_state


def hydrate_simulation_player(session: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``session`` with missing mechanic-owned player fields hydrated."""

    session = session if isinstance(session, dict) else {}
    public_state = _dict(session.get("state"))
    public_player = _dict(public_state.get("player"))
    public_world = _dict(public_state.get("world"))
    simulation = _dict(session.get("simulation_state"))
    player_state = _dict(simulation.get("player_state"))

    if public_player:
        for key in ("currency", "resources", "stats", "skills", "location_id"):
            if key not in player_state and public_player.get(key) is not None:
                player_state[key] = deepcopy(public_player[key])

        public_inventory = public_player.get("inventory")
        inventory_state = _dict(player_state.get("inventory_state"))
        if isinstance(public_inventory, list) and not inventory_state.get("items"):
            inventory_state["items"] = [_normalize_public_item(item) for item in public_inventory if isinstance(item, dict)]
        if player_state.get("currency") is not None and inventory_state.get("currency") is None:
            inventory_state["currency"] = deepcopy(player_state["currency"])
        if inventory_state:
            player_state["inventory_state"] = inventory_state

    if player_state:
        simulation["player_state"] = player_state
    if not isinstance(simulation.get("environment"), dict) and isinstance(public_world.get("environment"), dict):
        simulation["environment"] = deepcopy(public_world["environment"])
    if not isinstance(simulation.get("quest_state"), dict) and isinstance(public_state.get("quests"), list):
        simulation["quest_state"] = {"quests": deepcopy(public_state["quests"])}
    session["simulation_state"] = simulation
    return session


def project_authoritative_player(session: Dict[str, Any]) -> Dict[str, Any]:
    """Project authoritative wallet, resources, and inventory into public state."""

    session = session if isinstance(session, dict) else {}
    simulation = _dict(session.get("simulation_state"))
    player_state = _dict(simulation.get("player_state"))
    public_state = _dict(session.get("state"))
    public_player = _dict(public_state.get("player"))
    public_world = _dict(public_state.get("world"))

    inventory_state = _dict(player_state.get("inventory_state"))
    currency = player_state.get("currency") or inventory_state.get("currency")
    if isinstance(currency, dict):
        public_player["currency"] = deepcopy(currency)
    for key in ("resources", "stats", "skills", "location_id"):
        if player_state.get(key) is not None:
            public_player[key] = deepcopy(player_state[key])
    if isinstance(inventory_state.get("items"), list):
        public_player["inventory"] = [_public_item(item) for item in inventory_state["items"] if isinstance(item, dict)]

    if public_player:
        public_state["player"] = public_player
    environment = simulation.get("environment")
    if isinstance(environment, dict):
        public_world["environment"] = deepcopy(environment)
        public_world["time"] = _format_environment_time(environment)
        public_state["world"] = public_world
    quest_state = _dict(simulation.get("quest_state"))
    if isinstance(quest_state.get("quests"), list):
        public_state["quests"] = deepcopy(quest_state["quests"])
    _project_world_location(public_state, simulation)
    _project_world_presence(session, simulation)
    session["state"] = public_state
    return session


def _project_world_presence(session: Dict[str, Any], simulation: Dict[str, Any]) -> None:
    """Who is here, for a session with its own world: when the player reaches another place, the people who live
    there (and the player's companions) are present, not the people of the place they left."""

    locations = _dict(_dict(simulation.get("world_model")).get("locations"))
    player_state = _dict(simulation.get("player_state"))
    location_id = str(player_state.get("location_id") or "")
    location = _dict(locations.get(location_id))
    present_state = _dict(simulation.get("present_npc_state"))
    if not location or present_state.get("location_id") == location_id:
        return
    companions = [
        str(_dict(companion).get("npc_id") or "")
        for companion in _dict(player_state.get("party_state")).get("companions") or ()
    ]
    present_ids = [str(_dict(npc).get("id") or "") for npc in location.get("present_npcs") or ()]
    present_ids = [npc_id for npc_id in dict.fromkeys(present_ids + companions) if npc_id]
    simulation["present_npc_state"] = {**present_state, "location_id": location_id, "present_npc_ids": present_ids}
    session["simulation_state"] = simulation
    runtime = _dict(session.get("runtime_state"))
    name = str(location.get("name") or location_id)
    runtime["current_scene"] = {
        **_dict(runtime.get("current_scene")),
        "scene_id": f"scene:{location_id}",
        "location_id": location_id,
        "location_name": name,
        "title": name,
        "summary": str(location.get("description") or name),
        "present_npc_ids": present_ids,
        "actors": [str(_dict(npc).get("name") or "") for npc in location.get("present_npcs") or ()],
    }
    session["runtime_state"] = runtime


def _project_world_location(public_state: Dict[str, Any], simulation: Dict[str, Any]) -> None:
    """Where the player is, by name, for a session with its own world (a published one): travel moves the
    simulation's player, and the place, title, scene and region the player sees follow it."""

    locations = _dict(_dict(simulation.get("world_model")).get("locations"))
    location_id = str(_dict(simulation.get("player_state")).get("location_id") or "")
    location = _dict(locations.get(location_id))
    if not location or public_state.get("current_location_id") == location_id:
        return
    name = str(location.get("name") or location_id)
    previous = str(public_state.get("current_location_name") or public_state.get("location") or "")
    public_state.update({"location": name, "current_location": name, "current_location_id": location_id,
                         "current_location_name": name})
    title = str(public_state.get("title") or "")
    if previous and title.endswith(previous):
        public_state["title"] = title[: len(title) - len(previous)] + name
    world = _dict(public_state.get("world"))
    world.update({"current_location_id": location_id, "current_location_name": name})
    environment = _dict(world.get("environment"))
    if environment and location.get("region_id"):
        environment.update({"region_id": location["region_id"], "region_name": location.get("region_name") or ""})
        world["environment"] = environment
        world["region"] = location.get("region_name") or world.get("region")
    public_state["world"] = world
    scene = _dict(public_state.get("scene"))
    context = _dict(scene.get("environment_context"))
    if context:
        context.update({"location_id": location_id, "location_label": name,
                        "region_id": location.get("region_id") or context.get("region_id")})
        scene["environment_context"] = context
        public_state["scene"] = scene


def synchronize_player_projections(session: Dict[str, Any]) -> Dict[str, Any]:
    """Hydrate missing simulation fields, then expose authoritative values."""

    return project_authoritative_player(hydrate_simulation_player(session))


def merge_authoritative_session_state(
    base_session: Dict[str, Any],
    authoritative_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Carry mechanic-owned state through presentation wrappers without stale overwrite."""

    base = copy_state(_dict(base_session))
    payload = _dict(authoritative_payload)
    nested = _dict(payload.get("result"))
    authoritative_session = _dict(payload.get("session") or nested.get("session"))
    if authoritative_session:
        base = copy_state(authoritative_session)
    authoritative_simulation = _dict(
        payload.get("simulation_state")
        or nested.get("simulation_state")
        or authoritative_session.get("simulation_state")
    )
    if authoritative_simulation:
        base["simulation_state"] = copy_state(authoritative_simulation)
    return project_authoritative_player(hydrate_simulation_player(base))


def _normalize_public_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(item)
    if "item_id" not in normalized and normalized.get("id") is not None:
        normalized["item_id"] = normalized["id"]
    return normalized


def _public_item(item: Dict[str, Any]) -> Dict[str, Any]:
    projected = deepcopy(item)
    if "id" not in projected and projected.get("item_id") is not None:
        projected["id"] = projected["item_id"]
    return projected


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _format_environment_time(environment: Dict[str, Any]) -> str:
    absolute = max(0, int(environment.get("absolute_minutes") or 0))
    day = absolute // (24 * 60) + 1
    minute = absolute % (24 * 60)
    return f"Day {day} • {minute // 60:02d}:{minute % 60:02d}"


__all__ = [
    "hydrate_simulation_player",
    "project_authoritative_player",
    "merge_authoritative_session_state",
    "synchronize_player_projections",
]
