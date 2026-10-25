"""The local map a turn leaves the hero on, and where a fight's foes stand on it (RQ-7.7; docs/rpg/design/combat.md).

A place the world draws a grid for has one map instance per campaign, made the first time the hero arrives (the hero
at the map's arrival square) and kept after: the play screen's grid follows the hero there. A fight on that map puts
its foes on it: a foe new to the fight takes the free square nearest the hero, and after the foes act, a foe not
beside the hero closes in. Where the foes stand is the fight's own (``tactical_spatial.foes_take_the_field``); a new
map instance is written in the turn's transaction, with the turn.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state.changes import CombatAdvanced, LocalMapEntered, StateChange
from app.apps.rpg.rules import routines


def _location_map_id(simulation: Mapping[str, Any], location_id: str) -> str:
    locations = _d(simulation.get("world_model")).get("locations")
    if isinstance(locations, Mapping):
        return _s(_d(locations.get(location_id)).get("map_id"))
    if isinstance(locations, list):
        return next((_s(_d(row).get("map_id")) for row in locations if _s(_d(row).get("location_id")) == location_id), "")
    return ""


def map_instance_id_for(session_id: str, map_id: str) -> str:
    """A campaign's one instance of a map (the opening's is made the same way, ``published_launch``)."""
    return f"{session_id}:map:{map_id}:1"


def _new_instance(session_id: str, location_id: str, map_id: str) -> tuple[Any, Any] | None:
    """The map's definition and a first visit's snapshot of it (the hero at its arrival square), or ``None`` when the
    world draws no grid for the place yet."""
    from app.apps.rpg.world.map_grid_contracts import GridActorPlacement, GridMapDefinition
    from app.apps.rpg.world.map_instance_runtime import MapMovementError, arrival_cell, create_map_instance_snapshot
    from app.apps.rpg.world.tactical_spatial import hero_on_map
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    with unit_of_work() as work:
        stored = work.map_instances.latest_definition(current_tenant(), map_id)
        work.rollback()
    if stored is None:
        return None
    definition = GridMapDefinition.model_validate(stored["document"])
    try:
        arrival = arrival_cell(definition)
    except MapMovementError:  # a map with no square to arrive on is no map to stand on
        return None
    snapshot = create_map_instance_snapshot(
        map_instance_id=map_instance_id_for(session_id, map_id), campaign_id=session_id, location_id=location_id,
        definition=definition, actors=(GridActorPlacement(actor_id=hero_on_map(session_id), cell=arrival),))
    return definition, snapshot


def _existing(session_id: str, map_instance_id: str) -> tuple[Any, Any] | None:
    from app.apps.rpg.session.turn.tactical import map_for_turn

    try:
        return map_for_turn(map_instance_id, campaign_id=session_id)
    except KeyError:
        return None


def on_the_local_map(
    session_id: str,
    document: Mapping[str, Any],
    *,
    moved: bool,
    pending_map_event: Mapping[str, Any] | None = None,
    foes_act: bool = True,
) -> tuple[list[StateChange], list[dict[str, Any]]]:
    """The changes that put the campaign on the hero's local map and its foes on the grid, and the map instances the
    turn makes (to write with it). ``moved``: the hero changed place this turn; ``pending_map_event``: this turn's grid
    move, not yet written; ``foes_act``: the foes had their turns (all but the hero's grid move)."""
    from app.apps.rpg.world.map_grid_contracts import GridMapDefinition
    from app.apps.rpg.world.map_instance_runtime import CampaignMapInstanceSnapshot
    from app.apps.rpg.world.tactical_spatial import foes_take_the_field, hero_on_map

    simulation = _d(document.get("simulation_state"))
    if not _d(simulation.get("world_model")).get("locations"):
        return [], []  # a campaign of no published world has no local maps
    here = routines.hero_location(simulation)
    current = _s(_d(document.get("state")).get("current_map_instance_id"))
    map_id = _location_map_id(simulation, here)
    target = map_instance_id_for(session_id, map_id) if map_id else ""
    changes: list[StateChange] = []
    created: list[dict[str, Any]] = []
    loaded: tuple[Any, Any] | None = None
    if target and target != current:
        loaded = _existing(session_id, target)
        if loaded is None and (made := _new_instance(session_id, here, map_id)) is not None:
            loaded = made
            snapshot = made[1]
            created.append({"map_instance_id": snapshot.map_instance_id, "campaign_id": snapshot.campaign_id,
                            "location_id": snapshot.location_id, "map_id": snapshot.map_id,
                            "definition_revision": snapshot.definition_revision,
                            "definition_hash": snapshot.definition_hash, "snapshot": snapshot.model_dump(mode="json")})
        if loaded is not None:
            changes.append(LocalMapEntered(map_instance_id=target))
            current = target
    elif not target and current and moved:
        changes.append(LocalMapEntered(map_instance_id=""))  # a place with no grid: no other place's grid either
        current = ""

    combat = _d(simulation.get("combat_state"))
    if current and combat.get("active") is True:
        if pending_map_event and _s(pending_map_event.get("map_instance_id")) == current:
            definition = (loaded or _existing(session_id, current) or (None, None))[0]
            snapshot = CampaignMapInstanceSnapshot.model_validate(pending_map_event["snapshot"])
            loaded = (definition, snapshot) if definition is not None else None
        elif loaded is None:
            loaded = _existing(session_id, current)
        if loaded is not None and isinstance(loaded[0], GridMapDefinition):
            placed = foes_take_the_field(loaded[0], loaded[1], combat, hero_id=hero_on_map(session_id),
                                         foes_act=foes_act)
            if placed is not None:
                changes.append(CombatAdvanced(combat_state=placed))
    return changes, created


__all__ = ["map_instance_id_for", "on_the_local_map"]
