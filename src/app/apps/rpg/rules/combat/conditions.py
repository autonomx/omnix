from __future__ import annotations

from typing import Any, Dict, List
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list, safe_str as _safe_str

MAX_STATUS_EFFECTS_PER_ACTOR = 12


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_status_effect(effect: Dict[str, Any]) -> Dict[str, Any]:
    effect = _safe_dict(effect)
    kind = _safe_str(effect.get("kind")).strip().lower()
    target_actor_id = _safe_str(effect.get("target_actor_id")).strip()

    return {
        "effect_id": _safe_str(
            effect.get("effect_id")
            or f"effect:{kind}:{target_actor_id}"
        ).strip(),
        "kind": kind,
        "source": _safe_str(effect.get("source") or "combat").strip(),
        "source_actor_id": _safe_str(effect.get("source_actor_id")).strip(),
        "target_actor_id": target_actor_id,
        "duration_turns": max(0, _safe_int(effect.get("duration_turns"), 1)),
        "stacks": max(1, _safe_int(effect.get("stacks"), 1)),
        "magnitude": max(0, _safe_int(effect.get("magnitude"), 0)),
        "tick_timing": _safe_str(effect.get("tick_timing") or "start_of_turn").strip(),
    }


def normalize_status_effects(effects: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for effect in _safe_list(effects):
        item = normalize_status_effect(_safe_dict(effect))
        if item.get("kind") and item.get("target_actor_id") and item.get("duration_turns", 0) > 0:
            normalized.append(item)
    return normalized[:MAX_STATUS_EFFECTS_PER_ACTOR]


def get_participant_status_effects(participant: Dict[str, Any]) -> List[Dict[str, Any]]:
    participant = _safe_dict(participant)
    return normalize_status_effects(participant.get("status_effects"))


def actor_has_condition(participant: Dict[str, Any], kind: str) -> bool:
    kind = _safe_str(kind).strip().lower()
    return any(effect.get("kind") == kind for effect in get_participant_status_effects(participant))


def remove_status_effects_from_participant(
    participant: Dict[str, Any],
    kinds: List[str],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    participant = dict(_safe_dict(participant))
    wanted = {_safe_str(kind).strip().lower() for kind in kinds if _safe_str(kind).strip()}
    removed: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []

    for effect in get_participant_status_effects(participant):
        if effect.get("kind") in wanted:
            removed.append(effect)
        else:
            kept.append(effect)

    participant["status_effects"] = normalize_status_effects(kept)
    return participant, removed


def tick_start_of_turn_status_effects(
    participant: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    participant = dict(_safe_dict(participant))
    effects = get_participant_status_effects(participant)

    hp_before = _safe_int(participant.get("hp"), _safe_int(_safe_dict(participant.get("resources")).get("hp"), 0))
    hp_after = hp_before

    ticked: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []

    for effect in effects:
        effect = dict(effect)
        kind = effect.get("kind")
        timing = effect.get("tick_timing") or "start_of_turn"
        duration = _safe_int(effect.get("duration_turns"), 0)

        if timing == "start_of_turn":
            damage = 0
            if kind in {"bleeding", "poisoned", "burning"}:
                damage = max(1, _safe_int(effect.get("magnitude"), 1)) * max(1, _safe_int(effect.get("stacks"), 1))
                hp_after = max(0, hp_after - damage)

            duration -= 1
            effect["duration_turns"] = max(0, duration)
            ticked.append({
                "kind": kind,
                "damage": damage,
                "stacks": effect.get("stacks"),
                "magnitude": effect.get("magnitude"),
                "duration_turns_after": effect["duration_turns"],
            })

        if _safe_int(effect.get("duration_turns"), 0) <= 0:
            expired.append(effect)
        else:
            kept.append(effect)

    participant["hp"] = hp_after
    resources = dict(_safe_dict(participant.get("resources")))
    if resources:
        resources["hp"] = hp_after
        participant["resources"] = resources

    participant["status_effects"] = normalize_status_effects(kept)

    return participant, {
        "ticked": bool(ticked),
        "hp_before": hp_before,
        "hp_after": hp_after,
        "effects_ticked": ticked,
        "effects_expired": expired,
    }
