from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.combat.enemy_runtime import resolve_current_enemy_combat_turn
from app.rpg.combat.runtime import (
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


def _player_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(simulation_state.get("player_state"))


def _party_companions(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    party_state = _safe_dict(_player_state(simulation_state).get("party_state"))
    return [_safe_dict(item) for item in _safe_list(party_state.get("companions"))]


def _companion_by_id(simulation_state: Dict[str, Any], npc_id: str) -> Dict[str, Any]:
    for companion in _party_companions(simulation_state):
        if _safe_str(companion.get("npc_id")) == npc_id:
            return companion
    return {}


def _living_enemy_ids(combat_state: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    participants = _safe_dict(combat_state.get("participants"))
    for actor_id, participant in participants.items():
        participant = _safe_dict(participant)
        if (
            _safe_str(participant.get("side")) == "enemy"
            and _safe_str(participant.get("status") or "active") == "active"
            and _safe_int(participant.get("hp"), 0) > 0
        ):
            ids.append(_safe_str(actor_id))
    return ids


def companion_morale_state(companion: Dict[str, Any]) -> Dict[str, Any]:
    companion = _safe_dict(companion)

    loyalty = _safe_int(
        companion.get("loyalty"),
        _safe_int(_safe_dict(companion.get("relationship")).get("loyalty"), 0),
    )
    identity_arc = _safe_str(companion.get("identity_arc"))
    current_role = _safe_str(companion.get("current_role"))
    motivations = " ".join(_safe_str(item) for item in _safe_list(companion.get("active_motivations")))

    text = f"{identity_arc} {current_role} {motivations}".lower()

    if "revenge" in text or "bandit" in text:
        return {
            "morale_state": "motivated",
            "reason": "revenge_arc_motivated_against_bandits",
            "accuracy_bonus": 1,
            "damage_bonus": 1,
            "loyalty": loyalty,
            "source": "deterministic_companion_combat_runtime",
        }

    if loyalty < -25:
        return {
            "morale_state": "reluctant",
            "reason": "low_loyalty_reluctant",
            "accuracy_bonus": -1,
            "damage_bonus": 0,
            "loyalty": loyalty,
            "source": "deterministic_companion_combat_runtime",
        }

    return {
        "morale_state": "steady",
        "reason": "neutral_morale",
        "accuracy_bonus": 0,
        "damage_bonus": 0,
        "loyalty": loyalty,
        "source": "deterministic_companion_combat_runtime",
    }


def choose_companion_combat_tactic(
    simulation_state: Dict[str, Any],
    *,
    npc_id: str,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    companion = _companion_by_id(simulation_state, npc_id)
    morale = companion_morale_state(companion)
    enemies = _living_enemy_ids(combat_state)

    if not companion:
        return {
            "resolved": False,
            "reason": "companion_not_found",
            "npc_id": npc_id,
            "source": "deterministic_companion_combat_runtime",
        }

    if not enemies:
        return {
            "resolved": False,
            "reason": "no_living_enemy_targets",
            "npc_id": npc_id,
            "morale": morale,
            "source": "deterministic_companion_combat_runtime",
        }

    tactic = "revenge_attack" if morale.get("morale_state") == "motivated" else "attack_nearest_enemy"

    return {
        "resolved": True,
        "reason": "companion_tactic_selected",
        "npc_id": npc_id,
        "tactic": tactic,
        "target_id": enemies[0],
        "morale": morale,
        "source": "deterministic_companion_combat_runtime",
    }


def resolve_companion_combat_turn(
    simulation_state: Dict[str, Any],
    *,
    npc_id: str,
    session_id: str = "",
    tick: int = 0,
) -> Dict[str, Any]:
    combat_state = get_combat_state(simulation_state)
    if combat_state.get("active") is not True:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "combat_not_active",
            "npc_id": npc_id,
            "source": "deterministic_companion_combat_runtime",
        }

    current_actor = _safe_str(combat_state.get("current_actor_id"))
    if current_actor != npc_id:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": "not_companion_turn",
            "npc_id": npc_id,
            "current_actor_id": current_actor,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_companion_combat_runtime",
        }

    tactic = choose_companion_combat_tactic(
        simulation_state,
        npc_id=npc_id,
    )
    if tactic.get("resolved") is not True:
        return {
            "resolved": False,
            "changed_state": False,
            "reason": _safe_str(tactic.get("reason")),
            "npc_id": npc_id,
            "tactic": tactic,
            "combat_state": deepcopy(combat_state),
            "source": "deterministic_companion_combat_runtime",
        }

    attack = resolve_combat_attack(
        simulation_state,
        actor_id=npc_id,
        target_id=_safe_str(tactic.get("target_id")),
        session_id=session_id,
        tick=tick,
        combat_modifiers=_safe_dict(tactic.get("morale")),
    )

    reason = "companion_combat_attack_resolved"
    if attack.get("reason") == "combat_defeat_resolved":
        reason = "companion_combat_defeat_resolved"
    elif attack.get("resolved") is not True:
        reason = _safe_str(attack.get("reason") or "companion_combat_attack_failed")

    return {
        "resolved": bool(attack.get("resolved")),
        "changed_state": bool(attack.get("changed_state")),
        "reason": reason,
        "npc_id": npc_id,
        "actor_id": npc_id,
        "target_id": _safe_str(tactic.get("target_id")),
        "tactic": _safe_str(tactic.get("tactic")),
        "morale": deepcopy(tactic.get("morale")),
        "morale_accuracy_bonus": _safe_int(_safe_dict(tactic.get("morale")).get("accuracy_bonus"), 0),
        "morale_damage_bonus": _safe_int(_safe_dict(tactic.get("morale")).get("damage_bonus"), 0),
        "attack_result": deepcopy(attack),
        "combat_state": deepcopy(attack.get("combat_state") or simulation_state.get("combat_state") or {}),
        "tick": int(tick or 0),
        "source": "deterministic_companion_combat_runtime",
    }


def resolve_current_companion_combat_turn(
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
            "source": "deterministic_companion_combat_runtime",
        }

    current_actor = _safe_str(combat_state.get("current_actor_id"))

    if current_actor.startswith("npc:"):
        return resolve_companion_combat_turn(
            simulation_state,
            npc_id=current_actor,
            session_id=session_id,
            tick=tick,
        )

    if current_actor.startswith("enemy:"):
        enemy_result = resolve_current_enemy_combat_turn(
            simulation_state,
            session_id=session_id,
            tick=tick,
        )
        return {
            "resolved": bool(enemy_result.get("resolved")),
            "changed_state": bool(enemy_result.get("changed_state")),
            "reason": _safe_str(enemy_result.get("reason")),
            "actor_id": current_actor,
            "enemy_combat_result": deepcopy(enemy_result),
            "combat_state": deepcopy(simulation_state.get("combat_state") or {}),
            "source": "deterministic_companion_combat_runtime",
        }

    return {
        "resolved": False,
        "changed_state": False,
        "reason": "current_actor_not_companion",
        "actor_id": current_actor,
        "combat_state": deepcopy(combat_state),
        "source": "deterministic_companion_combat_runtime",
    }