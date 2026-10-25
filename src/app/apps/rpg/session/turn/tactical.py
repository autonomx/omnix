"""Grid moves and attacks in a fight, as structured-action turns (RQ-2.6; docs/rpg/design/combat.md).

The tactical grid is the fight seen on the map, not a second fight: a move spends the hero's movement for their turn
and is the map's change, committed with the turn; an attack is the fight rule's blow (``rules/combat/fight.py``),
with the reach and the target's cover read off the grid. What the grid refuses (a blocked path, a target out of
reach, not the hero's turn) refuses the request; no turn is taken.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state.changes import CombatAdvanced
from app.apps.rpg.rules.combat.fight import fight
from app.apps.rpg.rules.combat.runtime_core import current_actor_id, participant
from app.apps.rpg.rules.interactions.equipment_runtime import project_equipment_stats
from app.apps.rpg.world.map_grid_contracts import GridMapDefinition
from app.apps.rpg.world.map_instance_runtime import (
    CampaignMapInstanceSnapshot,
    MoveActorCommand,
    reduce_map_event,
    resolve_move_command,
)
from app.apps.rpg.world.tactical_spatial import (
    TacticalSpatialError,
    evaluate_cover,
    foes_on_grid,
    footprint_distance,
    hero_on_map,
    movement_left,
)
from app.apps.rpg.foundation.state import access as _sections


@dataclass(frozen=True)
class GridTurn:
    changes: list[Any]
    lines: list[str]
    minutes: int
    map_event: dict[str, Any] | None = None  # the map's change, committed in the turn's unit of work
    action_result: dict[str, Any] = field(default_factory=dict)  # what the tactical route answers with


def map_for_turn(map_instance_id: str, *, campaign_id: str) -> tuple[GridMapDefinition, CampaignMapInstanceSnapshot]:
    """The map instance the command names, and its definition, as they stand (the campaign's own maps only)."""
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    context = current_tenant()
    with unit_of_work() as work:
        instance = work.map_instances.get_instance(context, map_instance_id)
        if instance is None:
            raise KeyError(f"map_instance_not_found:{map_instance_id}")
        if str(instance["campaign_id"]) != campaign_id:
            raise TacticalSpatialError("tactical_map_campaign_mismatch")
        stored = work.map_instances.get_definition(context, instance["map_id"], instance["definition_revision"])
        work.rollback()
    if stored is None:
        raise KeyError(f"map_definition_not_found:{instance['map_id']}:{instance['definition_revision']}")
    return (GridMapDefinition.model_validate(stored["document"]),
            CampaignMapInstanceSnapshot.model_validate(instance["snapshot"]))


def _the_heros_turn(simulation: Mapping[str, Any]) -> dict[str, Any]:
    combat = _d(_sections.combat_state_of(simulation))
    if combat.get("active") is not True:
        raise TacticalSpatialError("tactical_combat_not_active")
    if current_actor_id(combat) != "player":
        raise TacticalSpatialError("tactical_actor_not_current", f"expected={current_actor_id(combat)}:received=player")
    return combat


def grid_move(session_id: str, simulation: Mapping[str, Any], definition: GridMapDefinition,
              snapshot: CampaignMapInstanceSnapshot, *, destination: tuple[int, int], command_id: str) -> GridTurn:
    combat = dict(_the_heros_turn(simulation))
    tactical, left = movement_left(combat)
    actor_id = hero_on_map(session_id)
    try:  # the fight's foes stand in the way; the map keeps only its own actors
        event, _ = resolve_move_command(definition, foes_on_grid(snapshot, combat), MoveActorCommand(
            command_id=command_id, actor_id=actor_id, destination=destination,
            expected_map_state_revision=snapshot.map_state_revision))
        moved = reduce_map_event(snapshot, event)
    except ValueError as exc:  # a blocked or unknown path, a cell off the map
        raise TacticalSpatialError(str(exc)) from exc
    if event.movement_cost > left:
        raise TacticalSpatialError("tactical_movement_budget_exceeded", f"required={event.movement_cost}:remaining={left}")
    tactical = {**tactical, "movement_remaining": left - event.movement_cost}
    combat["tactical_state"] = tactical
    summary = {"movement_cost": event.movement_cost, "movement_remaining": tactical["movement_remaining"],
               "path": [list(cell) for cell in event.path]}
    return GridTurn(
        changes=[CombatAdvanced(combat_state=combat)],
        lines=[f"You move {len(event.path) - 1 if event.path else 0} squares."],
        minutes=0,
        map_event={"map_instance_id": snapshot.map_instance_id, "command_id": command_id, "event_id": event.event_id,
                   "event_type": event.event_type, "event_sequence": event.event_sequence,
                   "revision_before": event.map_state_revision_before, "revision_after": event.map_state_revision_after,
                   "event": event.model_dump(mode="json"), "snapshot": moved.model_dump(mode="json")},
        action_result={"kind": "tactical_move", "map_instance_id": snapshot.map_instance_id, "actor_id": actor_id,
                       "actor_cell": list(moved.actor(actor_id).cell), "map_state_revision": moved.map_state_revision,
                       "map_event_id": event.event_id, "tactical": summary},
    )


def grid_attack(session_id: str, simulation: Mapping[str, Any], definition: GridMapDefinition,
                snapshot: CampaignMapInstanceSnapshot, *, target_id: str, attack: str, turn_key: str) -> GridTurn:
    combat = _the_heros_turn(simulation)
    if _s(participant(dict(combat), target_id).get("side")) != "enemy":
        raise TacticalSpatialError("tactical_target_not_hostile", target_id)
    hero = hero_on_map(session_id)
    snapshot = foes_on_grid(snapshot, combat)  # the fight's foes, where it put them
    on_map = {actor.actor_id for actor in snapshot.actors}
    cover = 0
    reach = {"ranged_attack": int(_d(project_equipment_stats(dict(simulation), actor_id="player").get("stats")).get("range")
                                  or 1)}.get(attack, 1)
    if hero in on_map and target_id in on_map:  # a foe placed on the grid: its reach and cover count
        assessment = evaluate_cover(definition, snapshot, attacker_id=hero, target_id=target_id)
        if assessment.level == "blocked":
            raise TacticalSpatialError("tactical_target_not_visible", target_id)
        if footprint_distance(snapshot.actor(hero), snapshot.actor(target_id)) > max(1, reach):
            raise TacticalSpatialError("tactical_target_out_of_reach", target_id)
        cover = int(assessment.defense_bonus)
    turn = fight(simulation, action="attack", target_ref=target_id, turn_key=turn_key, cover=cover)
    if turn is None:
        raise TacticalSpatialError("tactical_target_not_in_fight", target_id)
    return GridTurn(
        changes=turn.changes, lines=turn.lines, minutes=turn.minutes,
        action_result={"kind": "tactical_attack", "map_instance_id": snapshot.map_instance_id, "actor_id": hero,
                       "target_id": target_id, "map_state_revision": snapshot.map_state_revision,
                       "tactical": {"cover": cover, "ended": turn.ended,
                                    "hit": bool(turn.report.get("hit")),
                                    "damage": int(turn.report.get("damage_applied") or 0)}},
    )


__all__ = ["GridTurn", "grid_attack", "grid_move", "hero_on_map", "map_for_turn"]
