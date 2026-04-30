from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.combat.runtime import (
    advance_combat_turn,
    get_combat_state,
    resolve_combat_attack,
)


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


def _participant(combat_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(combat_state.get("participants")).get(actor_id))


def living_party_targets(combat_state: Dict[str, Any]) -> List[str]:
    targets: List[str] = []
    participants = _safe_dict(combat_state.get("participants"))

    # Deterministic v1 priority: player first, then companions by actor_id.
    player = _safe_dict(participants.get("player"))
    if (
        player
        and _safe_str(player.get("side")) == "party"
        and _safe_str(player.get("status") or "active") == "active"
        and _safe_int(player.get("hp"), 0) > 0
    ):
        targets.append("player")

    companion_ids = []
    for actor_id, participant in participants.items():
        actor_id = _safe_str(actor_id)
        participant = _safe_dict(participant)
        if actor_id == "player":
            continue
        if (
            actor_id.startswith("npc:")
            and _safe_str(participant.get("side")) == "party"
            and _safe_str(participant.get("status") or "active") == "active"
            and _safe_int(participant.get("hp"), 0) > 0
        ):
            companion_ids.append(actor_id)

    targets.extend(sorted(companion_ids))
    return targets


def choose_enemy_target(
    simulation_state: Dict[str, Any],
    *,
    enemy_id: str,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    enemy = _participant(combat_state, enemy_id)

    if not enemy:
        return {
            "resolved": False,
            "reason": "enemy_not_found",
            "enemy_id": enemy_id,
            "source": "deterministic_enemy_combat_runtime",
        }

    if _safe_str(enemy.get("status") or "active") != "active" or _safe_int(enemy.get("hp"), 0) <= 0:
        return {
            "resolved": False,
            "reason": "enemy_not_active",
            "enemy_id": enemy_id,
            "source": "deterministic_enemy_combat_runtime",
        }

    targets = living_party_targets(combat_state)
    if not targets:
        return {
            "resolved": False,
            "reason": "no_living_party_targets",
            "enemy_id": enemy_id,
            "source": "deterministic_enemy_combat_runtime",
        }

    return {
        "resolved": True,
        "reason": "enemy_target_selected",
        "enemy_id": enemy_id,
        "target_id": targets[0],
        "target_candidates": targets,
        "tactic": "attack_first_living_party_target",
        "source": "deterministic_enemy_combat_runtime",
    }


def _party_defeated(combat_state: Dict[str, Any]) -> bool:
    return not living_party_targets(combat_state)


def resolve_enemy_combat_turn(
    simulation_state: Dict[str, Any],
    *,
    enemy_id: str,
    session_id: str = "",
    tick: int = 0,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    if combat_state.get("active") is not True:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_not_active",
            "enemy_id": enemy_id,
            "source": "deterministic_enemy_combat_runtime",
        }

    current_actor = _safe_str(combat_state.get("current_actor_id"))
    if current_actor != enemy_id:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "not_enemy_turn",
            "enemy_id": enemy_id,
            "current_actor_id": current_actor,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_enemy_combat_runtime",
        }

    target = choose_enemy_target(
        simulation_state,
        enemy_id=enemy_id,
    )
    if target.get("resolved") is not True:
        if _safe_str(target.get("reason")) == "no_living_party_targets":
            combat_state["active"] = False
            combat_state["ended_reason"] = "party_side_defeated"
            simulation_state["combat_state"] = combat_state
            return {
                "resolved": True,
                "changed_state": True,
                "reason": "party_defeat_resolved",
                "enemy_id": enemy_id,
                "party_defeated": True,
                "combat_ended": True,
                "target_selection": deepcopy(target),
                "combat_state": deepcopy(combat_state),
                "source": "deterministic_enemy_combat_runtime",
            }

        return {
            "resolved": False,
            "changed_state": False,
            "reason": _safe_str(target.get("reason")),
            "enemy_id": enemy_id,
            "target_selection": deepcopy(target),
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_enemy_combat_runtime",
        }

    attack = resolve_combat_attack(
        simulation_state,
        actor_id=enemy_id,
        target_id=_safe_str(target.get("target_id")),
        session_id=session_id,
        tick=tick,
    )

    combat_state = get_combat_state(simulation_state)
    party_defeated = _party_defeated(combat_state)

    if party_defeated:
        combat_state["active"] = False
        combat_state["ended_reason"] = "party_side_defeated"
        simulation_state["combat_state"] = combat_state

    reason = "enemy_combat_attack_resolved"
    if party_defeated:
        reason = "party_defeat_resolved"
    elif attack.get("resolved") is not True:
        reason = _safe_str(attack.get("reason") or "enemy_combat_attack_failed")

    return {
        "resolved": bool(attack.get("resolved")) or party_defeated,
        "changed_state": bool(attack.get("changed_state")) or party_defeated,
        "reason": reason,
        "enemy_id": enemy_id,
        "actor_id": enemy_id,
        "target_id": _safe_str(target.get("target_id")),
        "tactic": _safe_str(target.get("tactic")),
        "target_selection": deepcopy(target),
        "attack_result": deepcopy(attack),
        "party_defeated": party_defeated,
        "combat_ended": party_defeated,
        "combat_state": deepcopy(simulation_state.get("combat_state") or {}),
        "tick": int(tick or 0),
        "source": "deterministic_enemy_combat_runtime",
    }


def resolve_current_enemy_combat_turn(
    simulation_state: Dict[str, Any],
    *,
    session_id: str = "",
    tick: int = 0,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    if combat_state.get("active") is not True:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_not_active",
            "source": "deterministic_enemy_combat_runtime",
        }

    current_actor = _safe_str(combat_state.get("current_actor_id"))
    if not current_actor.startswith("enemy:"):
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "current_actor_not_enemy",
            "actor_id": current_actor,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_enemy_combat_runtime",
        }

    return resolve_enemy_combat_turn(
        simulation_state,
        enemy_id=current_actor,
        session_id=session_id,
        tick=tick,
    )