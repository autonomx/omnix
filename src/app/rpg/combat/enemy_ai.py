from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _hp(participant: Dict[str, Any]) -> int:
    participant = _safe_dict(participant)
    resources = _safe_dict(participant.get("resources"))
    return _safe_int(participant.get("hp", resources.get("hp")), 0)


def _max_hp(participant: Dict[str, Any]) -> int:
    participant = _safe_dict(participant)
    resources = _safe_dict(participant.get("resources"))
    return max(1, _safe_int(participant.get("max_hp", resources.get("max_hp")), 1))


def _hp_ratio(participant: Dict[str, Any]) -> float:
    return max(0.0, min(1.0, _hp(participant) / float(_max_hp(participant))))


def _side(participant: Dict[str, Any]) -> str:
    return _safe_str(
        participant.get("side")
        or participant.get("team")
        or participant.get("combat_team")
        or participant.get("faction")
    ).strip().lower()


def _status(participant: Dict[str, Any]) -> str:
    return _safe_str(participant.get("status")).strip().lower()


def _effect_kinds(participant: Dict[str, Any]) -> set[str]:
    kinds: set[str] = set()
    for effect in _safe_list(_safe_dict(participant).get("status_effects")):
        kind = _safe_str(_safe_dict(effect).get("kind")).strip().lower()
        if kind:
            kinds.add(kind)
    return kinds


def is_active_combatant(participant: Dict[str, Any]) -> bool:
    participant = _safe_dict(participant)
    if not participant:
        return False
    if _hp(participant) <= 0:
        return False
    status = _status(participant)
    if status in {"downed", "unconscious", "defeated", "dead", "fled"}:
        return False
    effects = _effect_kinds(participant)
    if "downed" in effects or "unconscious" in effects:
        return False
    return True


def is_enemy(participant: Dict[str, Any]) -> bool:
    return _side(participant) in {"enemy", "hostile", "monster", "bandit"}


def is_party(participant: Dict[str, Any]) -> bool:
    return _side(participant) in {"party", "player", "ally", "companion"}


def select_enemy_targets(
    combat_state: Dict[str, Any],
    actor_id: str,
) -> Dict[str, Any]:
    combat_state = _safe_dict(combat_state)
    participants = _safe_dict(combat_state.get("participants"))
    actor = _safe_dict(participants.get(actor_id))
    actor_side = _side(actor)

    candidates: List[Dict[str, Any]] = []
    avoided: List[Dict[str, Any]] = []

    for target_id, participant in participants.items():
        target_id = str(target_id)
        participant = _safe_dict(participant)

        if target_id == actor_id:
            continue

        target_side = _side(participant)
        hostile = target_side and target_side != actor_side
        if actor_side in {"enemy", "hostile", "monster", "bandit"}:
            hostile = is_party(participant)
        elif actor_side in {"party", "player", "ally", "companion"}:
            hostile = is_enemy(participant)

        if not hostile:
            continue

        if not is_active_combatant(participant):
            avoided.append({
                "actor_id": target_id,
                "name": participant.get("name", target_id),
                "reason": "inactive_or_downed",
                "hp": _hp(participant),
                "status": participant.get("status", ""),
                "effects": sorted(_effect_kinds(participant)),
            })
            continue

        candidates.append({
            "actor_id": target_id,
            "name": participant.get("name", target_id),
            "hp": _hp(participant),
            "max_hp": _max_hp(participant),
            "hp_ratio": _hp_ratio(participant),
            "status": participant.get("status", ""),
            "effects": sorted(_effect_kinds(participant)),
        })

    candidates.sort(key=lambda row: (float(row.get("hp_ratio", 1.0)), int(row.get("hp", 999999)), str(row.get("actor_id"))))
    selected = candidates[0] if candidates else {}

    return {
        "selected": bool(selected),
        "actor_id": actor_id,
        "target_actor_id": _safe_str(selected.get("actor_id")).strip(),
        "reason": "lowest_active_hp_ratio" if selected else "no_active_hostile_targets",
        "candidates": candidates,
        "avoided": avoided,
    }


def evaluate_enemy_morale(
    combat_state: Dict[str, Any],
    actor_id: str,
) -> Dict[str, Any]:
    combat_state = _safe_dict(combat_state)
    participants = _safe_dict(combat_state.get("participants"))
    actor = _safe_dict(participants.get(actor_id))

    hp_ratio = _hp_ratio(actor)
    effects = _effect_kinds(actor)

    score = 70
    reasons: List[str] = []

    if hp_ratio <= 0.25:
        score -= 35
        reasons.append("low_hp")
    elif hp_ratio <= 0.5:
        score -= 15
        reasons.append("wounded")

    if "bleeding" in effects:
        score -= 10
        reasons.append("bleeding")
    if "stunned" in effects:
        score -= 15
        reasons.append("stunned")

    enemy_alive = 0
    party_alive = 0
    enemy_down = 0

    actor_side = _side(actor)
    for other_id, participant in participants.items():
        participant = _safe_dict(participant)
        side = _side(participant)

        if actor_side in {"enemy", "hostile", "monster", "bandit"}:
            same_side = is_enemy(participant)
            hostile_side = is_party(participant)
        else:
            same_side = side == actor_side
            hostile_side = side != actor_side

        if same_side:
            if is_active_combatant(participant):
                enemy_alive += 1
            else:
                enemy_down += 1
        elif hostile_side:
            if is_active_combatant(participant):
                party_alive += 1

    if party_alive > enemy_alive:
        score -= 10 * min(3, party_alive - enemy_alive)
        reasons.append("outnumbered")

    if enemy_down:
        score -= 8 * min(3, enemy_down)
        reasons.append("allies_down")

    tags = {_safe_str(x).strip().lower() for x in _safe_list(actor.get("tags"))}
    if "brave" in tags:
        score += 20
        reasons.append("brave")
    if "cowardly" in tags:
        score -= 20
        reasons.append("cowardly")
    if "boss" in tags:
        score += 30
        reasons.append("boss")

    score = max(0, min(100, score))
    threshold = _safe_int(actor.get("morale_threshold"), 35)
    flee = score < threshold

    return {
        "checked": True,
        "actor_id": actor_id,
        "score": score,
        "threshold": threshold,
        "intent": "flee" if flee else "",
        "reason": "low_morale" if flee else "morale_holds",
        "factors": reasons,
        "hp_ratio": hp_ratio,
    }


def choose_enemy_intent(
    combat_state: Dict[str, Any],
    actor_id: str,
) -> Dict[str, Any]:
    combat_state = _safe_dict(combat_state)
    participants = _safe_dict(combat_state.get("participants"))
    actor = _safe_dict(participants.get(actor_id))
    effects = _effect_kinds(actor)

    if "stunned" in effects:
        return {
            "selected": True,
            "actor_id": actor_id,
            "intent": "skip_turn",
            "reason": "stunned",
            "morale_result": {},
            "target_selection_result": {},
        }

    morale_result = evaluate_enemy_morale(combat_state, actor_id)
    if morale_result.get("intent") == "flee":
        return {
            "selected": True,
            "actor_id": actor_id,
            "intent": "flee",
            "reason": "low_morale",
            "morale_result": morale_result,
            "target_selection_result": {},
        }

    if _hp_ratio(actor) <= 0.4 and not _effect_kinds(actor).intersection({"bleeding", "stunned"}):
        # Low but not panicking: defend.
        return {
            "selected": True,
            "actor_id": actor_id,
            "intent": "defend",
            "reason": "low_hp_defensive",
            "morale_result": morale_result,
            "target_selection_result": {},
        }

    target_selection_result = select_enemy_targets(combat_state, actor_id)
    if not target_selection_result.get("selected"):
        return {
            "selected": True,
            "actor_id": actor_id,
            "intent": "hold",
            "reason": "no_active_targets",
            "morale_result": morale_result,
            "target_selection_result": target_selection_result,
        }

    return {
        "selected": True,
        "actor_id": actor_id,
        "intent": "attack",
        "reason": "attack_lowest_hp_active_target",
        "morale_result": morale_result,
        "target_selection_result": target_selection_result,
        "target_actor_id": target_selection_result.get("target_actor_id", ""),
    }


def mark_enemy_fled(
    combat_state: Dict[str, Any],
    actor_id: str,
) -> Dict[str, Any]:
    combat_state = dict(_safe_dict(combat_state))
    participants = dict(_safe_dict(combat_state.get("participants")))
    participant = dict(_safe_dict(participants.get(actor_id)))
    participant["status"] = "fled"
    participant["hp"] = max(0, _hp(participant))
    participants[actor_id] = participant
    combat_state["participants"] = participants

    fled = [str(x) for x in _safe_list(combat_state.get("fled_actor_ids"))]
    if actor_id not in fled:
        fled.append(actor_id)
    combat_state["fled_actor_ids"] = fled

    recent = list(combat_state.get("recent_events") or [])
    recent.append({
        "type": "enemy_fled",
        "actor_id": actor_id,
    })
    combat_state["recent_events"] = recent[-24:]
    return combat_state