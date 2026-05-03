from __future__ import annotations

from typing import Any, Dict

from app.rpg.lore.state import (
    add_lore_known_by,
    add_lore_tag,
    reveal_lore_to_player,
    set_lore_truth_status,
    upsert_lore_entry,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_lore_transition(
    simulation_state: Dict[str, Any],
    transition: Dict[str, Any],
    *,
    turn_index: int = 0,
) -> Dict[str, Any]:
    transition = _safe_dict(transition)
    action = str(transition.get("action") or "")
    lore_id = str(transition.get("lore_id") or "")

    if action == "upsert":
        entry = dict(transition)
        entry.pop("action", None)
        entry.setdefault("metadata", {})
        entry["metadata"]["updated_turn"] = int(turn_index or 0)
        return dict(
            upsert_lore_entry(simulation_state, entry),
            action=action,
        )

    if action == "reveal_to_player":
        return dict(
            reveal_lore_to_player(simulation_state, lore_id),
            action=action,
        )

    if action == "set_truth_status":
        return dict(
            set_lore_truth_status(
                simulation_state,
                lore_id,
                str(transition.get("truth_status") or ""),
            ),
            action=action,
        )

    if action == "add_known_by":
        return dict(
            add_lore_known_by(
                simulation_state,
                lore_id,
                str(transition.get("entity_id") or ""),
            ),
            action=action,
        )

    if action == "add_tag":
        return dict(
            add_lore_tag(
                simulation_state,
                lore_id,
                str(transition.get("tag") or ""),
            ),
            action=action,
        )

    return {
        "ok": False,
        "action": action,
        "lore_id": lore_id,
        "reason": f"unknown_lore_action:{action}",
    }