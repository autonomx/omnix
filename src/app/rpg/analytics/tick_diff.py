from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _keys_changed(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    all_keys = sorted(set(before.keys()) | set(after.keys()))
    changed = []
    for key in all_keys:
        if before.get(key) != after.get(key):
            changed.append(str(key))
    return changed


def build_tick_diff(before_state: Dict[str, Any], after_state: Dict[str, Any]) -> Dict[str, Any]:
    before_state = _safe_dict(before_state)
    after_state = _safe_dict(after_state)

    before_events = _safe_list(before_state.get("events"))
    after_events = _safe_list(after_state.get("events"))
    before_consequences = _safe_list(before_state.get("consequences"))
    after_consequences = _safe_list(after_state.get("consequences"))

    before_social = _safe_dict(before_state.get("social_state"))
    after_social = _safe_dict(after_state.get("social_state"))
    before_sandbox = _safe_dict(before_state.get("sandbox_state"))
    after_sandbox = _safe_dict(after_state.get("sandbox_state"))

    before_npc_minds = _safe_dict(before_state.get("npc_minds"))
    after_npc_minds = _safe_dict(after_state.get("npc_minds"))

    before_player_state = _safe_dict(before_state.get("player_state"))
    after_player_state = _safe_dict(after_state.get("player_state"))
    before_inventory = _safe_dict(before_player_state.get("inventory_state"))
    after_inventory = _safe_dict(after_player_state.get("inventory_state"))

    changed_npcs = []
    for npc_id in sorted(set(before_npc_minds.keys()) | set(after_npc_minds.keys())):
        if before_npc_minds.get(npc_id) != after_npc_minds.get(npc_id):
            changed_npcs.append(npc_id)

    before_event_id_set = set()
    has_event_ids = False
    for e in before_events:
        if isinstance(e, dict) and e.get("id") is not None:
            before_event_id_set.add(str(e.get("id")))
            has_event_ids = True

    before_consequence_id_set = set()
    has_consequence_ids = False
    for c in before_consequences:
        if isinstance(c, dict) and c.get("id") is not None:
            before_consequence_id_set.add(str(c.get("id")))
            has_consequence_ids = True

    new_events = []
    for i, item in enumerate(after_events):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if has_event_ids and item_id is not None:
            if str(item_id) not in before_event_id_set:
                new_events.append(dict(item))
        elif i >= len(before_events):
            new_events.append(dict(item))

    new_consequences = []
    for i, item in enumerate(after_consequences):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if has_consequence_ids and item_id is not None:
            if str(item_id) not in before_consequence_id_set:
                new_consequences.append(dict(item))
        elif i >= len(before_consequences):
            new_consequences.append(dict(item))

    return {
        "tick_before": _safe_int(before_state.get("tick"), 0),
        "tick_after": _safe_int(after_state.get("tick"), 0),
        "new_events": new_events[:20],
        "new_consequences": new_consequences[:20],
        "social_keys_changed": _keys_changed(before_social, after_social),
        "sandbox_keys_changed": _keys_changed(before_sandbox, after_sandbox),
        "player_keys_changed": _keys_changed(before_player_state, after_player_state),
        "inventory_keys_changed": _keys_changed(before_inventory, after_inventory),
        "inventory_before": before_inventory,
        "inventory_after": after_inventory,
        "changed_npc_ids": changed_npcs[:20],
        "summary": {
            "event_delta": len(after_events) - len(before_events),
            "consequence_delta": len(after_consequences) - len(before_consequences),
            "npc_changes": len(changed_npcs),
            "inventory_item_kinds_before": len(_safe_list(before_inventory.get("items"))),
            "inventory_item_kinds_after": len(_safe_list(after_inventory.get("items"))),
        },
    }
