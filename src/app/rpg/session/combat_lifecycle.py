from __future__ import annotations

import hashlib
from typing import Any, Dict, List


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _i(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except Exception:
            return default
    return default


def _stable_id(*parts: Any) -> str:
    raw = ":".join(_s(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"combat:{digest}"


def _combat_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _d(result)
    nested = _d(result.get("result"))
    for payload in (
        _d(result.get("combat_narration_payload")),
        _d(nested.get("combat_narration_payload")),
        _d(result.get("narration_payload")),
        _d(nested.get("narration_payload")),
        _d(result.get("structured_narration")),
        _d(nested.get("structured_narration")),
    ):
        if _s(payload.get("source")) == "deterministic_combat_fast_summary" and _d(payload.get("combat_delta")):
            return payload
    return {}


def _combat_delta(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = _combat_payload(result)
    delta = _d(payload.get("combat_delta")) or _d(payload.get("combat_delta_contract"))
    if delta:
        return delta
    result = _d(result)
    nested = _d(result.get("result"))
    return _d(result.get("combat_delta_contract")) or _d(nested.get("combat_delta_contract"))


def build_combat_lifecycle_snapshot(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build deterministic lifecycle metadata from an already-resolved combat delta.

    PR.1 foundation only: this does not decide damage, initiative, victory, XP,
    or loot. It exposes a stable schema around the authoritative combat delta so
    Phase 1 can add enemy turns, initiative queues, XP, and loot without changing
    the fast combat state contract again.
    """

    result = _d(result)
    nested = _d(result.get("result"))
    delta = _combat_delta(result)
    if not delta:
        return {}

    target_id = _s(delta.get("target_id") or nested.get("target_id") or "enemy:road_bandit")
    target_name = _s(delta.get("target_name") or nested.get("target_name") or "bandit") or "enemy"
    actor_id = _s(delta.get("actor_id") or "player") or "player"
    damage = _i(delta.get("damage_applied"), 0)
    hp_before = delta.get("target_hp_before")
    hp_after = delta.get("target_hp_after")
    defeated = bool(delta.get("defeated") or delta.get("combat_ended"))
    combat_ended = bool(delta.get("combat_ended") or defeated)
    turn_index = _i(result.get("tick") or nested.get("tick") or result.get("turn_index") or nested.get("turn_index"), 0)

    entry = {
        "schema": "combat_log_entry_v1",
        "entry_id": _stable_id(turn_index, actor_id, target_id, damage, hp_before, hp_after, defeated),
        "turn_index": turn_index,
        "round_index": max(1, turn_index),
        "phase": "player_action",
        "actor_id": actor_id,
        "actor_side": "player",
        "target_id": target_id,
        "target_name": target_name,
        "target_side": "enemy",
        "action_type": _s(delta.get("action_type") or "attack") or "attack",
        "hit": damage > 0 or defeated,
        "damage_applied": damage,
        "target_hp_before": hp_before,
        "target_hp_after": hp_after,
        "defeated": defeated,
        "combat_ended": combat_ended,
        "source": "deterministic_combat_delta_contract_v1",
    }

    next_actor_id = "" if combat_ended else target_id
    return {
        "schema": "combat_lifecycle_v1",
        "source": "pr1_combat_lifecycle_foundation",
        "initiative": {
            "schema": "combat_initiative_v1",
            "order": [actor_id, target_id],
            "active_actor_id": actor_id,
            "next_actor_id": next_actor_id,
            "round_index": max(1, turn_index),
            "turn_phase": "combat_complete" if combat_ended else "awaiting_enemy_turn",
        },
        "enemy_turn": {
            "schema": "enemy_turn_skeleton_v1",
            "pending": not combat_ended,
            "actor_id": next_actor_id,
            "reason": "enemy_turn_not_yet_resolved_in_pr1_foundation" if not combat_ended else "combat_ended",
        },
        "combat_log": [entry],
        "progression_hooks": {
            "schema": "combat_progression_hooks_v1",
            "xp_pending": defeated,
            "loot_pending": defeated,
            "resolved": False,
            "reason": "placeholder_for_phase1_xp_loot_resolution",
        },
    }


def enrich_combat_lifecycle_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _d(result)
    lifecycle = build_combat_lifecycle_snapshot(result)
    if not lifecycle:
        return result
    result["combat_lifecycle"] = lifecycle
    result["combat_log"] = lifecycle.get("combat_log", [])
    if "result" in result:
        nested = _d(result.get("result"))
        nested["combat_lifecycle"] = lifecycle
        nested["combat_log"] = lifecycle.get("combat_log", [])
        result["result"] = nested
    for key in ("narration_payload", "structured_narration", "combat_narration_payload"):
        payload = _d(result.get(key))
        if payload:
            payload["combat_lifecycle"] = lifecycle
            payload["combat_log"] = lifecycle.get("combat_log", [])
            result[key] = payload
    return result
