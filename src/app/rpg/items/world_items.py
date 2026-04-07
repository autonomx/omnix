"""Phase 18.3A — World item state: ground loot and scene objects."""
from __future__ import annotations

from typing import Any, Dict, List
import hashlib


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def ensure_world_item_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure simulation_state has a well-formed world_items subtree."""
    simulation_state = dict(simulation_state or {})
    wi = simulation_state.setdefault("world_items", {})
    if not isinstance(wi, dict):
        simulation_state["world_items"] = {"by_location": {}}
    wi = simulation_state["world_items"]
    wi.setdefault("by_location", {})
    return simulation_state


def spawn_world_item(
    simulation_state: Dict[str, Any],
    location_id: str,
    item_def: Dict[str, Any],
) -> Dict[str, Any]:
    """Spawn an item in a world location."""
    simulation_state = ensure_world_item_state(simulation_state)
    location_id = _safe_str(location_id) or "unknown"
    item_def = dict(item_def or {})
    item_id = _safe_str(item_def.get("item_id"))
    # Generate deterministic instance_id
    content = f"{location_id}-{item_id}-{len(simulation_state['world_items']['by_location'].get(location_id, []))}"
    instance_id = item_def.get("instance_id") or ("wi_" + hashlib.sha256(content.encode()).hexdigest()[:10])
    item_def["instance_id"] = str(instance_id)
    item_def["location_id"] = location_id

    by_loc = simulation_state["world_items"]["by_location"]
    if location_id not in by_loc:
        by_loc[location_id] = []
    by_loc[location_id].append(item_def)
    return simulation_state


def pickup_world_item(
    simulation_state: Dict[str, Any],
    item_instance_id: str,
) -> Dict[str, Any]:
    """Remove an item from world and return it. Sets _picked_up_item on simulation_state."""
    simulation_state = ensure_world_item_state(simulation_state)
    item_instance_id = _safe_str(item_instance_id)
    by_loc = simulation_state["world_items"]["by_location"]
    picked = None
    for loc_id, items in by_loc.items():
        for i, item in enumerate(list(items)):
            if isinstance(item, dict) and _safe_str(item.get("instance_id")) == item_instance_id:
                picked = item
                items.pop(i)
                break
        if picked:
            break
    simulation_state["_picked_up_item"] = picked or {}
    return simulation_state


def drop_world_item(
    simulation_state: Dict[str, Any],
    item_id: str,
    location_id: str = "",
    qty: int = 1,
) -> Dict[str, Any]:
    """Drop an item into a world location."""
    simulation_state = ensure_world_item_state(simulation_state)
    location_id = _safe_str(location_id) or _safe_str(_safe_dict(simulation_state.get("player_state")).get("current_scene_id")) or "unknown"
    item_def = {"item_id": _safe_str(item_id), "qty": max(1, _safe_int(qty))}
    return spawn_world_item(simulation_state, location_id, item_def)


def list_scene_items(
    simulation_state: Dict[str, Any],
    location_id: str,
) -> List[Dict[str, Any]]:
    """Return items present at a location."""
    simulation_state = ensure_world_item_state(simulation_state)
    location_id = _safe_str(location_id)
    by_loc = _safe_dict(simulation_state.get("world_items", {}).get("by_location"))
    items = by_loc.get(location_id, [])
    return [dict(i) for i in items if isinstance(i, dict)]
