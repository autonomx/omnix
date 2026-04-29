from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.interactions.equipment_runtime import (
    consume_equipped_ammo,
    project_equipment_stats,
)
from app.rpg.interactions.loot_runtime import generate_loot_from_table


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _deterministic_roll(seed: str, low: int, high: int) -> int:
    low = int(low)
    high = max(low, int(high))
    span = high - low + 1
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return low + (int(digest[:16], 16) % span)


def _player_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player_state = _safe_dict(simulation_state.get("player_state"))
    simulation_state["player_state"] = player_state
    return player_state


def _party_companions(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    party_state = _safe_dict(_player_state(simulation_state).get("party_state"))
    return [_safe_dict(item) for item in _safe_list(party_state.get("companions"))]


def _default_enemy_bandit() -> Dict[str, Any]:
    return {
        "actor_id": "enemy:bandit_1",
        "side": "enemy",
        "name": "Bandit",
        "hp": 8,
        "max_hp": 8,
        "armor": 0,
        "defense": 10,
        "initiative_bonus": 0,
        "status": "active",
        "loot_table_id": "loot:bandit_common",
        "source": "deterministic_combat_runtime",
    }


def _participant_from_player(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    player_state = _player_state(simulation_state)
    return {
        "actor_id": "player",
        "side": "party",
        "name": "You",
        "hp": _safe_int(player_state.get("hp"), _safe_int(player_state.get("max_hp"), 20)),
        "max_hp": _safe_int(player_state.get("max_hp"), 20),
        "armor": 0,
        "defense": 10,
        "initiative_bonus": 1,
        "status": "active",
        "source": "deterministic_combat_runtime",
    }


def _participant_from_companion(companion: Dict[str, Any]) -> Dict[str, Any]:
    companion = _safe_dict(companion)
    npc_id = _safe_str(companion.get("npc_id"))
    return {
        "actor_id": npc_id,
        "side": "party",
        "name": _safe_str(companion.get("name") or npc_id),
        "hp": _safe_int(companion.get("hp"), _safe_int(companion.get("max_hp"), 16)),
        "max_hp": _safe_int(companion.get("max_hp"), 16),
        "armor": 0,
        "defense": 10,
        "initiative_bonus": 0,
        "status": _safe_str(companion.get("combat_status") or "active"),
        "identity_arc": _safe_str(companion.get("identity_arc")),
        "current_role": _safe_str(companion.get("current_role")),
        "source": "deterministic_combat_runtime",
    }


def _participant_from_enemy(enemy: Dict[str, Any]) -> Dict[str, Any]:
    enemy = _safe_dict(enemy)
    actor_id = _safe_str(enemy.get("actor_id") or enemy.get("enemy_id") or enemy.get("id"))
    return {
        "actor_id": actor_id,
        "side": _safe_str(enemy.get("side") or "enemy"),
        "name": _safe_str(enemy.get("name") or actor_id),
        "hp": _safe_int(enemy.get("hp"), _safe_int(enemy.get("max_hp"), 10)),
        "max_hp": _safe_int(enemy.get("max_hp"), 10),
        "armor": _safe_int(enemy.get("armor"), 0),
        "defense": _safe_int(enemy.get("defense"), 10),
        "initiative_bonus": _safe_int(enemy.get("initiative_bonus"), 0),
        "status": _safe_str(enemy.get("status") or "active"),
        "loot_table_id": _safe_str(enemy.get("loot_table_id")),
        "source": "deterministic_combat_runtime",
    }


def _active_participants(participants: Dict[str, Any]) -> List[Dict[str, Any]]:
    active = []
    for participant in _safe_dict(participants).values():
        participant = _safe_dict(participant)
        if _safe_str(participant.get("status") or "active") == "active":
            active.append(participant)
    return active


def _current_actor_id(combat_state: Dict[str, Any]) -> str:
    order = _safe_list(combat_state.get("initiative_order"))
    if not order:
        return ""
    idx = _safe_int(combat_state.get("turn_index"), 0) % len(order)
    return _safe_str(_safe_dict(order[idx]).get("actor_id"))


def _participant(combat_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(combat_state.get("participants")).get(actor_id))


def _living_enemy_ids(combat_state: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for actor_id, participant in _safe_dict(combat_state.get("participants")).items():
        participant = _safe_dict(participant)
        if (
            _safe_str(participant.get("side")) == "enemy"
            and _safe_str(participant.get("status") or "active") == "active"
            and _safe_int(participant.get("hp"), 0) > 0
        ):
            ids.append(_safe_str(actor_id))
    return ids


def _living_party_ids(combat_state: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for actor_id, participant in _safe_dict(combat_state.get("participants")).items():
        participant = _safe_dict(participant)
        if (
            _safe_str(participant.get("side")) == "party"
            and _safe_str(participant.get("status") or "active") == "active"
            and _safe_int(participant.get("hp"), 0) > 0
        ):
            ids.append(_safe_str(actor_id))
    return ids


def _default_target_for_actor(combat_state: Dict[str, Any], actor_id: str) -> str:
    actor = _participant(combat_state, actor_id)
    side = _safe_str(actor.get("side"))

    if side == "enemy":
        party = _living_party_ids(combat_state)
        return party[0] if party else ""

    enemies = _living_enemy_ids(combat_state)
    return enemies[0] if enemies else ""


def _combat_seed(combat_state: Dict[str, Any], *parts: Any) -> str:
    return "|".join(
        [
            _safe_str(combat_state.get("encounter_id")),
            str(_safe_int(combat_state.get("round"), 1)),
            str(_safe_int(combat_state.get("turn_index"), 0)),
            *[_safe_str(part) for part in parts],
        ]
    )


def _actor_equipment_stats(simulation_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    projected = project_equipment_stats(simulation_state, actor_id=actor_id)
    return _safe_dict(projected.get("stats"))


def _damage_bounds_for_actor(simulation_state: Dict[str, Any], actor_id: str) -> Dict[str, int]:
    stats = _actor_equipment_stats(simulation_state, actor_id)
    return {
        "damage_min": max(1, _safe_int(stats.get("damage_min"), 1)),
        "damage_max": max(1, _safe_int(stats.get("damage_max"), 2)),
        "accuracy_bonus": _safe_int(stats.get("accuracy_bonus"), 0),
        "encumbrance_penalty": _safe_int(stats.get("encumbrance_penalty"), 0),
        "armor": _safe_int(stats.get("armor"), 0),
    }


def _sync_participant_hp_to_actor_state(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str,
    hp: int,
    status: str,
) -> None:
    if actor_id == "player":
        player_state = _player_state(simulation_state)
        player_state["hp"] = max(0, int(hp))
        if status:
            player_state["combat_status"] = status
        simulation_state["player_state"] = player_state
        return

    if actor_id.startswith("npc:"):
        player_state = _player_state(simulation_state)
        party_state = _safe_dict(player_state.get("party_state"))
        companions = _safe_list(party_state.get("companions"))
        for companion in companions:
            companion = _safe_dict(companion)
            if _safe_str(companion.get("npc_id")) == actor_id:
                companion["hp"] = max(0, int(hp))
                if status:
                    companion["combat_status"] = status
                break
        party_state["companions"] = companions
        player_state["party_state"] = party_state
        simulation_state["player_state"] = player_state


def _build_initiative_order(
    *,
    encounter_id: str,
    participants: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows = []

    for actor_id, participant in _safe_dict(participants).items():
        participant = _safe_dict(participant)
        if _safe_str(participant.get("status") or "active") != "active":
            continue

        roll = _deterministic_roll(f"{encounter_id}|initiative|{actor_id}", 1, 20)
        bonus = _safe_int(participant.get("initiative_bonus"), 0)
        initiative = roll + bonus

        rows.append({
            "actor_id": actor_id,
            "initiative": initiative,
            "roll": roll,
            "bonus": bonus,
        })

    rows.sort(key=lambda row: (-_safe_int(row.get("initiative")), _safe_str(row.get("actor_id"))))
    return rows


def start_combat_encounter(
    simulation_state: Dict[str, Any],
    *,
    encounter_id: str = "enc:bandit_ambush",
    enemies: List[Dict[str, Any]] | None = None,
    tick: int = 0,
) -> Dict[str, Any]:
    existing = _safe_dict(simulation_state.get("combat_state"))
    if existing.get("active") is True:
        return {
            "resolved": True,
            "changed_state": False,
            "reason": "combat_already_active",
            "combat_state": deepcopy(existing),
            "current_actor_id": _current_actor_id(existing),
            "source": "deterministic_combat_runtime",
        }

    participants: Dict[str, Dict[str, Any]] = {}

    player = _participant_from_player(simulation_state)
    participants[player["actor_id"]] = player

    for companion in _party_companions(simulation_state):
        participant = _participant_from_companion(companion)
        if participant.get("actor_id"):
            participants[participant["actor_id"]] = participant

    enemy_rows = enemies if enemies is not None else [_default_enemy_bandit()]
    for enemy in enemy_rows:
        participant = _participant_from_enemy(enemy)
        if participant.get("actor_id"):
            participants[participant["actor_id"]] = participant

    initiative_order = _build_initiative_order(
        encounter_id=encounter_id,
        participants=participants,
    )

    combat_state = {
        "active": True,
        "encounter_id": encounter_id,
        "round": 1,
        "turn_index": 0,
        "current_actor_id": _safe_str(_safe_dict(initiative_order[0]).get("actor_id")) if initiative_order else "",
        "initiative_order": initiative_order,
        "participants": participants,
        "combat_log": [],
        "source": "deterministic_combat_runtime",
    }

    simulation_state["combat_state"] = combat_state

    return {
        "resolved": True,
        "changed_state": True,
        "reason": "combat_started",
        "encounter_id": encounter_id,
        "current_actor_id": combat_state["current_actor_id"],
        "combat_state": deepcopy(combat_state),
        "tick": int(tick or 0),
        "source": "deterministic_combat_runtime",
    }


def get_combat_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(simulation_state.get("combat_state"))


def is_combat_active(simulation_state: Dict[str, Any]) -> bool:
    return _safe_dict(simulation_state.get("combat_state")).get("active") is True


def validate_combat_turn(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    if combat_state.get("active") is not True:
        return {
            "allowed": True,
            "reason": "combat_not_active",
            "source": "deterministic_combat_runtime",
        }

    actor_id = _safe_str(actor_id or "player")
    current_actor = _current_actor_id(combat_state)

    if actor_id != current_actor:
        return {
            "allowed": False,
            "reason": "not_actor_turn",
            "requested_actor_id": actor_id,
            "current_actor_id": current_actor,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_combat_runtime",
        }

    return {
        "allowed": True,
        "reason": "actor_turn_allowed",
        "requested_actor_id": actor_id,
        "current_actor_id": current_actor,
        "combat_state": deepcopy(combat_state),
        "source": "deterministic_combat_runtime",
    }


def advance_combat_turn(
    simulation_state: Dict[str, Any],
    *,
    tick: int = 0,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    if combat_state.get("active") is not True:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_not_active",
            "source": "deterministic_combat_runtime",
        }

    order = _safe_list(combat_state.get("initiative_order"))
    if not order:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "initiative_order_missing",
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_combat_runtime",
        }

    previous_actor = _current_actor_id(combat_state)

    next_index = _safe_int(combat_state.get("turn_index"), 0) + 1
    round_num = _safe_int(combat_state.get("round"), 1)

    if next_index >= len(order):
        next_index = 0
        round_num += 1

    combat_state["turn_index"] = next_index
    combat_state["round"] = round_num
    combat_state["current_actor_id"] = _current_actor_id(combat_state)

    combat_state.setdefault("combat_log", []).append({
        "kind": "turn_advanced",
        "previous_actor_id": previous_actor,
        "current_actor_id": combat_state["current_actor_id"],
        "round": round_num,
        "turn_index": next_index,
        "tick": int(tick or 0),
    })

    simulation_state["combat_state"] = combat_state

    return {
        "resolved": True,
        "changed_state": True,
        "reason": "combat_turn_advanced",
        "previous_actor_id": previous_actor,
        "current_actor_id": combat_state["current_actor_id"],
        "round": round_num,
        "turn_index": next_index,
        "combat_state": deepcopy(combat_state),
        "tick": int(tick or 0),
        "source": "deterministic_combat_runtime",
    }


def gate_combat_action(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str,
    action_kind: str,
) -> Dict[str, Any]:
    turn = validate_combat_turn(simulation_state, actor_id=actor_id)
    if turn.get("allowed") is not True:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": _safe_str(turn.get("reason") or "not_actor_turn"),
            "requested_actor_id": _safe_str(actor_id or "player"),
            "current_actor_id": _safe_str(turn.get("current_actor_id")),
            "action_kind": _safe_str(action_kind),
            "combat_state": deepcopy(_safe_dict(turn.get("combat_state"))),
            "source": "deterministic_combat_runtime",
        }

    allowed_actions = {"attack", "defend", "wait", "flee", "use", "consume", "equip"}
    if _safe_str(action_kind) not in allowed_actions:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_action_not_allowed",
            "requested_actor_id": _safe_str(actor_id or "player"),
            "current_actor_id": _safe_str(turn.get("current_actor_id")),
            "action_kind": _safe_str(action_kind),
            "allowed_actions": sorted(allowed_actions),
            "combat_state": deepcopy(_safe_dict(turn.get("combat_state"))),
            "source": "deterministic_combat_runtime",
        }

    return {
        "resolved": True,
        "changed_state": False,
        "reason": "combat_action_allowed",
        "requested_actor_id": _safe_str(actor_id or "player"),
        "current_actor_id": _safe_str(turn.get("current_actor_id")),
        "action_kind": _safe_str(action_kind),
        "combat_state": deepcopy(_safe_dict(turn.get("combat_state"))),
        "source": "deterministic_combat_runtime",
    }


def resolve_combat_attack(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str = "player",
    target_id: str = "",
    session_id: str = "",
    tick: int = 0,
    combat_modifiers: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    if combat_state.get("active") is not True:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_not_active",
            "source": "deterministic_combat_runtime",
        }

    actor_id = _safe_str(actor_id or "player")
    combat_modifiers = _safe_dict(combat_modifiers)
    morale_accuracy_bonus = _safe_int(combat_modifiers.get("accuracy_bonus"), 0)
    morale_damage_bonus = _safe_int(combat_modifiers.get("damage_bonus"), 0)
    gate = gate_combat_action(
        simulation_state,
        actor_id=actor_id,
        action_kind="attack",
    )
    if gate.get("resolved") is not True:
        return gate

    participants = _safe_dict(combat_state.get("participants"))
    actor = _participant(combat_state, actor_id)
    if not actor:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_actor_not_found",
            "actor_id": actor_id,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_combat_runtime",
        }

    target_id = _safe_str(target_id) or _default_target_for_actor(combat_state, actor_id)
    target = _participant(combat_state, target_id)
    if not target:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_target_not_found",
            "actor_id": actor_id,
            "target_id": target_id,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_combat_runtime",
        }

    if _safe_str(target.get("status") or "active") != "active" or _safe_int(target.get("hp"), 0) <= 0:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_target_not_active",
            "actor_id": actor_id,
            "target_id": target_id,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_combat_runtime",
        }

    actor_stats = _damage_bounds_for_actor(simulation_state, actor_id)
    target_defense = _safe_int(target.get("defense"), 10)
    target_armor = _safe_int(target.get("armor"), 0)

    ammo_result = {}
    equipment_stats = project_equipment_stats(simulation_state, actor_id=actor_id)
    equipped_items = _safe_list(equipment_stats.get("equipped_items"))
    requires_ammo = False
    for equipped in equipped_items:
        equipped = _safe_dict(equipped)
        if _safe_str(equipped.get("slot")) == "main_hand":
            # equipment_runtime does not expose requires_ammo_tag directly,
            # so use ammo hook defensively. If no ammo is equipped and weapon
            # does not need ammo, consume_equipped_ammo returns ammo_not_equipped.
            requires_ammo = True if _safe_int(_safe_dict(equipment_stats.get("stats")).get("range"), 1) > 1 else False

    if requires_ammo:
        ammo_result = consume_equipped_ammo(
            simulation_state,
            actor_id=actor_id,
            quantity=1,
            tick=tick,
        )
        # Companions may not have ammo in this phase. Let melee/no-ammo
        # companions still resolve with their projected weapon stats unless
        # the player is explicitly using an ammo weapon.
        if ammo_result.get("consumed") is not True and actor_id == "player":
            return {
                "resolved": False,
                "changed_state": False,
                "reason": "combat_ammo_required",
                "actor_id": actor_id,
                "target_id": target_id,
                "ammo_result": deepcopy(ammo_result),
                "combat_state": deepcopy(combat_state),
                "source": "deterministic_combat_runtime",
            }

    attack_roll = _deterministic_roll(
        _combat_seed(combat_state, "attack", actor_id, target_id),
        1,
        20,
    )
    attack_total = (
        attack_roll
        + actor_stats["accuracy_bonus"]
        + morale_accuracy_bonus
        - actor_stats["encumbrance_penalty"]
    )
    hit = attack_total >= target_defense

    hp_before = _safe_int(target.get("hp"), 0)
    damage_roll = 0
    armor_reduction = 0
    damage_applied = 0
    hp_after = hp_before

    if hit:
        damage_roll = _deterministic_roll(
            _combat_seed(combat_state, "damage", actor_id, target_id),
            actor_stats["damage_min"],
            actor_stats["damage_max"],
        )
        armor_reduction = max(0, target_armor)
        damage_applied = max(1, damage_roll + morale_damage_bonus - armor_reduction)
        hp_after = max(0, hp_before - damage_applied)

    target["hp"] = hp_after
    defeated = hp_after <= 0
    if defeated:
        target["status"] = "defeated"

    participants[target_id] = target
    combat_state["participants"] = participants
    _sync_participant_hp_to_actor_state(
        simulation_state,
        actor_id=target_id,
        hp=hp_after,
        status=_safe_str(target.get("status")),
    )

    combat_log_entry = {
        "kind": "attack",
        "round": _safe_int(combat_state.get("round"), 1),
        "turn_index": _safe_int(combat_state.get("turn_index"), 0),
        "actor_id": actor_id,
        "target_id": target_id,
        "attack_roll": attack_roll,
        "attack_total": attack_total,
        "equipment_accuracy_bonus": actor_stats["accuracy_bonus"],
        "morale_accuracy_bonus": morale_accuracy_bonus,
        "target_defense": target_defense,
        "hit": hit,
        "damage_roll": damage_roll,
        "morale_damage_bonus": morale_damage_bonus,
        "armor_reduction": armor_reduction,
        "damage_applied": damage_applied,
        "target_hp_before": hp_before,
        "target_hp_after": hp_after,
        "defeated": defeated,
        "tick": int(tick or 0),
    }
    combat_state.setdefault("combat_log", []).append(combat_log_entry)

    combat_ended = False
    loot_result = {}

    if defeated and not _living_enemy_ids(combat_state):
        combat_state["active"] = False
        combat_state["ended_reason"] = "enemy_side_defeated"
        combat_ended = True

        loot_table_id = _safe_str(target.get("loot_table_id") or "loot:bandit_common")
        loot_result = generate_loot_from_table(
            simulation_state,
            loot_table_id=loot_table_id,
            source_id=target_id,
            session_id=session_id,
            tick=tick,
            add_to_inventory=True,
        )

    if not combat_ended:
        advance = advance_combat_turn(simulation_state, tick=tick)
        combat_state = _safe_dict(simulation_state.get("combat_state"))
        next_actor_id = _safe_str(advance.get("current_actor_id"))
    else:
        simulation_state["combat_state"] = combat_state
        next_actor_id = ""

    reason = "combat_defeat_resolved" if defeated else "combat_attack_resolved"

    return {
        "resolved": True,
        "changed_state": True,
        "reason": reason,
        "actor_id": actor_id,
        "target_id": target_id,
        "hit": hit,
        "attack_roll": attack_roll,
        "attack_total": attack_total,
        "equipment_accuracy_bonus": actor_stats["accuracy_bonus"],
        "morale_accuracy_bonus": morale_accuracy_bonus,
        "target_defense": target_defense,
        "damage_roll": damage_roll,
        "morale_damage_bonus": morale_damage_bonus,
        "armor_reduction": armor_reduction,
        "damage_applied": damage_applied,
        "target_hp_before": hp_before,
        "target_hp_after": hp_after,
        "defeated": defeated,
        "combat_ended": combat_ended,
        "next_actor_id": next_actor_id,
        "ammo_result": deepcopy(ammo_result),
        "loot_result": deepcopy(loot_result),
        "combat_log_entry": deepcopy(combat_log_entry),
        "combat_state": deepcopy(combat_state),
        "tick": int(tick or 0),
        "source": "deterministic_combat_runtime",
    }
