"""The fight's turn order: whose turn comes next, and what the start of a turn does (conditions tick; a stunned actor
loses the turn). Pure: the combat section in, the advanced copy out."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from app.apps.rpg.rules.combat.conditions import (
    actor_has_condition,
    remove_status_effects_from_participant,
    tick_start_of_turn_status_effects,
)
from app.apps.rpg.rules.combat.runtime_core import current_actor_id, safe_dict, safe_int, safe_list, safe_str


def next_turn(combat: Mapping[str, Any], *, tick: int = 0) -> Dict[str, Any]:
    """The combat section with the turn passed to the next in the initiative order (a new round after the last), the
    start of that actor's turn applied, and the passing logged; unchanged (a copy) when no fight or order is on."""
    advanced = deepcopy(dict(combat))
    order = safe_list(advanced.get("initiative_order"))
    if advanced.get("active") is not True or not order:
        return advanced
    previous_actor = current_actor_id(advanced)
    next_index = safe_int(advanced.get("turn_index"), 0) + 1
    round_num = safe_int(advanced.get("round"), 1)
    if next_index >= len(order):
        next_index = 0
        round_num += 1
    advanced["turn_index"] = next_index
    advanced["round"] = round_num
    advanced["current_actor_id"] = current_actor_id(advanced)
    _start_turn(advanced)
    advanced.setdefault("combat_log", []).append({
        "kind": "turn_advanced",
        "previous_actor_id": previous_actor,
        "current_actor_id": advanced["current_actor_id"],
        "round": round_num,
        "turn_index": next_index,
        "tick": int(tick or 0),
    })
    return advanced


def _start_turn(advanced: Dict[str, Any]) -> None:
    """The start of the current actor's turn, on the copy ``next_turn`` advances: conditions tick, and a stunned actor
    is freed of it and skips the turn."""
    participants = safe_dict(advanced.get("participants"))
    current_actor = safe_str(advanced.get("current_actor_id")).strip()
    current_participant = safe_dict(participants.get(current_actor))
    if not current_participant:
        return

    was_stunned = actor_has_condition(current_participant, "stunned")
    current_participant, tick_result = tick_start_of_turn_status_effects(current_participant)
    participants[current_actor] = current_participant
    advanced["participants"] = participants
    if tick_result.get("ticked"):
        advanced["last_condition_tick_result"] = {"actor_id": current_actor, **tick_result}
        recent = list(advanced.get("recent_events") or [])
        recent.append({"type": "condition_tick", "actor_id": current_actor, "tick_result": tick_result})
        advanced["recent_events"] = recent[-24:]

    if not was_stunned:
        return

    current_participant, removed = remove_status_effects_from_participant(current_participant, ["stunned"])
    participants[current_actor] = current_participant
    advanced["participants"] = participants
    advanced["last_condition_result"] = {
        "applied": True,
        "source": "combat",
        "target_actor_id": current_actor,
        "effects_added": [],
        "effects_updated": [],
        "effects_removed": removed,
        "reason": "stunned_skip_turn",
    }
    advanced["pending_skip_turn_actor_id"] = current_actor


__all__ = ["next_turn"]
