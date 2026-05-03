from __future__ import annotations

from typing import Any, Dict

from app.rpg.lore.state import (
    get_lore_entry,
    is_lore_available_to_player,
    is_lore_known_by,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_lore_condition(
    simulation_state: Dict[str, Any],
    condition: Dict[str, Any],
) -> Dict[str, Any]:
    condition = _safe_dict(condition)
    condition_type = str(condition.get("type") or "")
    lore_id = str(condition.get("lore_id") or "")

    if condition_type == "lore_exists":
        entry = get_lore_entry(simulation_state, lore_id)
        return {
            "ok": bool(entry),
            "type": condition_type,
            "lore_id": lore_id,
            "reason": "lore_exists" if entry else "lore_missing",
        }

    if condition_type == "lore_revealed_to_player":
        ok = is_lore_available_to_player(simulation_state, lore_id)
        return {
            "ok": ok,
            "type": condition_type,
            "lore_id": lore_id,
            "reason": "revealed" if ok else "not_revealed",
        }

    if condition_type == "lore_known_by":
        entity_id = str(condition.get("entity_id") or "")
        ok = is_lore_known_by(simulation_state, lore_id, entity_id)
        return {
            "ok": ok,
            "type": condition_type,
            "lore_id": lore_id,
            "entity_id": entity_id,
            "reason": "known_by_entity" if ok else "not_known_by_entity",
        }

    if condition_type == "lore_truth_status":
        expected = str(condition.get("truth_status") or "")
        entry = get_lore_entry(simulation_state, lore_id)
        actual = str((entry or {}).get("truth_status") or "")
        return {
            "ok": actual == expected,
            "type": condition_type,
            "lore_id": lore_id,
            "expected": expected,
            "actual": actual,
            "reason": "truth_status_matches" if actual == expected else "truth_status_mismatch",
        }

    if condition_type == "lore_has_tag":
        tag = str(condition.get("tag") or "")
        entry = get_lore_entry(simulation_state, lore_id)
        tags = set((entry or {}).get("tags") or [])
        ok = tag in tags
        return {
            "ok": ok,
            "type": condition_type,
            "lore_id": lore_id,
            "tag": tag,
            "actual_tags": sorted(tags),
            "reason": "tag_present" if ok else "tag_missing",
        }

    return {
        "ok": False,
        "type": condition_type,
        "lore_id": lore_id,
        "reason": f"unknown_lore_condition_type:{condition_type}",
    }