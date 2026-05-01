from __future__ import annotations

from typing import Any, Dict, List, Tuple

VALID_ZONES = {"frontline", "backline"}
VALID_RANGE_BANDS = {"near", "far"}
DEFAULT_POSITION = {
    "zone": "frontline",
    "range_band": "near",
    "engaged_with": [],
    "cover": "none",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def normalize_position(value: Any) -> Dict[str, Any]:
    value = _safe_dict(value)
    zone = _safe_str(value.get("zone") or DEFAULT_POSITION["zone"]).strip().lower()
    range_band = _safe_str(value.get("range_band") or DEFAULT_POSITION["range_band"]).strip().lower()

    if zone not in VALID_ZONES:
        zone = DEFAULT_POSITION["zone"]
    if range_band not in VALID_RANGE_BANDS:
        range_band = DEFAULT_POSITION["range_band"]

    engaged_with = []
    for actor_id in _safe_list(value.get("engaged_with")):
        actor_id = _safe_str(actor_id).strip()
        if actor_id and actor_id not in engaged_with:
            engaged_with.append(actor_id)

    return {
        "zone": zone,
        "range_band": range_band,
        "engaged_with": engaged_with[:6],
        "cover": _safe_str(value.get("cover") or "none").strip().lower() or "none",
    }


def normalize_participant_position(participant: Dict[str, Any]) -> Dict[str, Any]:
    participant = dict(_safe_dict(participant))
    participant["position"] = normalize_position(participant.get("position"))
    return participant


def participant_is_ranged(participant: Dict[str, Any]) -> bool:
    tags = {_safe_str(x).strip().lower() for x in _safe_list(_safe_dict(participant).get("tags"))}
    return "ranged" in tags or "archer" in tags


def can_melee_attack(attacker: Dict[str, Any], target: Dict[str, Any]) -> Tuple[bool, str]:
    attacker_pos = normalize_position(_safe_dict(attacker).get("position"))
    target_pos = normalize_position(_safe_dict(target).get("position"))
    target_id = _safe_str(_safe_dict(target).get("actor_id") or _safe_dict(target).get("id")).strip()

    if target_id and target_id in attacker_pos.get("engaged_with", []):
        return True, "engaged"

    if attacker_pos.get("range_band") == "near" and target_pos.get("range_band") == "near":
        return True, "near"

    return False, "target_too_far"


def can_ranged_attack(attacker: Dict[str, Any], target: Dict[str, Any]) -> Tuple[bool, str]:
    attacker_pos = normalize_position(_safe_dict(attacker).get("position"))
    if attacker_pos.get("zone") == "backline":
        return True, "ranged_from_backline"
    return True, "ranged"


def can_attack_target(attacker: Dict[str, Any], target: Dict[str, Any]) -> Tuple[bool, str]:
    if participant_is_ranged(attacker):
        return can_ranged_attack(attacker, target)
    return can_melee_attack(attacker, target)


def reposition_participant(
    combat_state: Dict[str, Any],
    actor_id: str,
    *,
    zone: str = "frontline",
    range_band: str = "near",
    engage_target_id: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    combat_state = dict(_safe_dict(combat_state))
    participants = dict(_safe_dict(combat_state.get("participants")))
    actor_id = _safe_str(actor_id).strip()
    participant = dict(_safe_dict(participants.get(actor_id)))

    if not participant:
        return combat_state, {
            "changed": False,
            "reason": "actor_not_found",
            "actor_id": actor_id,
        }

    before = normalize_position(participant.get("position"))
    after = normalize_position({
        "zone": zone,
        "range_band": range_band,
        "engaged_with": [engage_target_id] if engage_target_id else before.get("engaged_with", []),
        "cover": before.get("cover", "none"),
    })

    participant["position"] = after
    participants[actor_id] = participant
    combat_state["participants"] = participants

    result = {
        "changed": before != after,
        "actor_id": actor_id,
        "from": before,
        "to": after,
        "reason": "repositioned" if before != after else "position_unchanged",
    }
    combat_state["last_position_result"] = result

    recent = list(combat_state.get("recent_events") or [])
    recent.append({
        "type": "position_changed",
        "actor_id": actor_id,
        "position_result": result,
    })
    combat_state["recent_events"] = recent[-24:]

    return combat_state, result


def flee_penalty_from_position(combat_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    participants = _safe_dict(_safe_dict(combat_state).get("participants"))
    participant = _safe_dict(participants.get(actor_id))
    position = normalize_position(participant.get("position"))
    engaged = bool(position.get("engaged_with"))
    return {
        "applied": engaged,
        "actor_id": actor_id,
        "penalty": 5 if engaged else 0,
        "reason": "engaged" if engaged else "not_engaged",
    }