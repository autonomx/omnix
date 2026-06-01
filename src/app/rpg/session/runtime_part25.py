from __future__ import annotations

# Generated split module for app.rpg.session.runtime.
# PR.1.17: deterministic combat end-state to quest objective sync.
from .runtime_part24 import *
from .runtime_part24 import _apply_turn_authoritative as _base_apply_turn_authoritative


def _combat_quest_sync_result_sources(payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    payload = _safe_dict(payload)
    result = _safe_dict(payload.get("result"))
    resolved_result = _safe_dict(payload.get("resolved_result")) or result
    narration_context = _safe_dict(payload.get("narration_context"))
    combat_result = (
        _safe_dict(payload.get("combat_result"))
        or _safe_dict(result.get("combat_result"))
        or _safe_dict(resolved_result.get("combat_result"))
        or _safe_dict(narration_context.get("combat_result"))
    )
    return result, resolved_result, narration_context, combat_result


def _combat_quest_sync_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    session = _safe_dict(payload.get("session"))
    return (
        _safe_dict(payload.get("simulation_state"))
        or _safe_dict(session.get("simulation_state"))
        or _safe_dict(payload.get("state"))
    )


def _combat_quest_sync_target_ids(combat_result: Dict[str, Any]) -> list[str]:
    combat_result = _safe_dict(combat_result)
    target_ids: list[str] = []
    for key in ("target_id", "defeated_target_id"):
        target_id = _safe_str(combat_result.get(key))
        if target_id and target_id not in target_ids:
            target_ids.append(target_id)
    for value in _safe_list(combat_result.get("defeated_target_ids")):
        target_id = _safe_str(value)
        if target_id and target_id not in target_ids:
            target_ids.append(target_id)
    combat_state = _safe_dict(combat_result.get("combat_state"))
    participants = _safe_dict(combat_state.get("participants"))
    for actor_id, participant in participants.items():
        participant = _safe_dict(participant)
        if _safe_str(participant.get("side")) != "enemy":
            continue
        if _safe_str(participant.get("status")) == "defeated" or _safe_int(participant.get("hp"), 1) <= 0:
            target_id = _safe_str(participant.get("actor_id") or actor_id)
            if target_id and target_id not in target_ids:
                target_ids.append(target_id)
    return target_ids


def _combat_quest_sync_quest_collections(simulation_state: Dict[str, Any]) -> list[Any]:
    simulation_state = _safe_dict(simulation_state)
    quest_roots = [
        _safe_dict(simulation_state.get("quest_state")),
        _safe_dict(simulation_state.get("quest_log")),
        _safe_dict(simulation_state.get("quests")),
    ]
    collections: list[Any] = []
    for root in quest_roots:
        if not root:
            continue
        for key in ("active_quests", "quests", "entries", "active"):
            collection = root.get(key)
            if isinstance(collection, (list, dict)) and collection not in collections:
                collections.append(collection)
        if any(key in root for key in ("quest_id", "id", "objectives")) and root not in collections:
            collections.append([root])
    return collections


def _combat_quest_sync_iter_quests(simulation_state: Dict[str, Any]):
    for collection in _combat_quest_sync_quest_collections(simulation_state):
        if isinstance(collection, dict):
            iterable = collection.values()
        else:
            iterable = collection
        for quest in iterable:
            if isinstance(quest, dict):
                yield quest


def _objective_matches_combat_target(objective: Dict[str, Any], target_ids: list[str]) -> bool:
    objective = _safe_dict(objective)
    objective_kind = _safe_str(objective.get("type") or objective.get("kind") or objective.get("objective_type"))
    if objective_kind and objective_kind not in {"defeat", "kill", "combat", "combat_defeat"}:
        return False
    objective_target = _safe_str(
        objective.get("target_id")
        or objective.get("target")
        or objective.get("enemy_id")
        or objective.get("actor_id")
    )
    if objective_target:
        return objective_target in target_ids
    target_set = {_safe_str(value) for value in _safe_list(objective.get("target_ids")) if _safe_str(value)}
    return bool(target_set.intersection(target_ids))


def _complete_combat_objective(objective: Dict[str, Any], *, tick: int) -> bool:
    objective = _safe_dict(objective)
    if _safe_str(objective.get("status")) in {"completed", "complete"}:
        return False
    required = max(1, _safe_int(objective.get("required") or objective.get("goal") or objective.get("target_count"), 1))
    current = min(required, _safe_int(objective.get("current") or objective.get("count") or objective.get("progress"), 0) + 1)
    objective["current"] = current
    objective["required"] = required
    if current >= required:
        objective["status"] = "completed"
        objective["completed_at_tick"] = tick
    return True


def _sync_combat_end_state_to_quests(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    result, resolved_result, narration_context, combat_result = _combat_quest_sync_result_sources(payload)
    if not combat_result:
        return payload
    if combat_result.get("combat_ended") is not True and _safe_str(combat_result.get("ended_reason")) != "enemy_side_defeated":
        return payload
    ended_reason = _safe_str(combat_result.get("ended_reason") or _safe_dict(combat_result.get("combat_state")).get("ended_reason"))
    if ended_reason and ended_reason != "enemy_side_defeated":
        return payload

    target_ids = _combat_quest_sync_target_ids(combat_result)
    if not target_ids:
        return payload
    simulation_state = _combat_quest_sync_state(payload)
    if not simulation_state:
        return payload

    tick = _safe_int(payload.get("tick") or combat_result.get("tick"), 0)
    updated_objectives: list[Dict[str, Any]] = []
    completed_quests: list[str] = []
    for quest in _combat_quest_sync_iter_quests(simulation_state):
        objectives = _safe_list(quest.get("objectives"))
        quest_id = _safe_str(quest.get("quest_id") or quest.get("id"))
        changed = False
        for objective in objectives:
            if not isinstance(objective, dict):
                continue
            if not _objective_matches_combat_target(objective, target_ids):
                continue
            if _complete_combat_objective(objective, tick=tick):
                changed = True
                updated_objectives.append(
                    {
                        "quest_id": quest_id,
                        "objective_id": _safe_str(objective.get("objective_id") or objective.get("id")),
                        "target_ids": list(target_ids),
                        "status": _safe_str(objective.get("status")),
                    }
                )
        if changed and objectives and all(_safe_str(_safe_dict(item).get("status")) in {"completed", "complete"} for item in objectives if isinstance(item, dict)):
            quest["status"] = "completed"
            quest["completed_at_tick"] = tick
            if quest_id:
                completed_quests.append(quest_id)

    if not updated_objectives:
        return payload

    sync_result = {
        "source": "deterministic_combat_quest_sync",
        "reason": "combat_end_state_enemy_side_defeated",
        "target_ids": target_ids,
        "updated_objectives": updated_objectives,
        "completed_quests": completed_quests,
    }
    result["combat_quest_sync_result"] = sync_result
    resolved_result["combat_quest_sync_result"] = sync_result
    narration_context["combat_quest_sync_result"] = sync_result
    narration_context["quest_progress_lines"] = [
        f"Quest objective completed: {item.get('objective_id') or 'combat objective'}"
        for item in updated_objectives
        if _safe_str(item.get("status")) in {"completed", "complete"}
    ]
    payload["combat_quest_sync_result"] = sync_result
    payload["simulation_state"] = simulation_state
    session = _safe_dict(payload.get("session"))
    if session:
        session["simulation_state"] = simulation_state
        payload["session"] = session
    payload["result"] = result
    payload["resolved_result"] = resolved_result
    payload["narration_context"] = narration_context
    return payload


def _apply_turn_authoritative(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = _base_apply_turn_authoritative(
        session_id,
        player_input,
        action,
        performance_override=performance_override,
    )
    return _sync_combat_end_state_to_quests(payload)


__all__ = [name for name in globals() if not name.startswith("__")]
