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


def build_timeline_row_diff(before_row: Dict[str, Any], after_row: Dict[str, Any]) -> Dict[str, Any]:
    before_row = _safe_dict(before_row)
    after_row = _safe_dict(after_row)
    return {
        "tick_before": _safe_int(before_row.get("tick"), 0),
        "tick_after": _safe_int(after_row.get("tick"), 0),
        "event_delta": _safe_int(after_row.get("event_count"), 0) - _safe_int(before_row.get("event_count"), 0),
        "consequence_delta": _safe_int(after_row.get("consequence_count"), 0) - _safe_int(before_row.get("consequence_count"), 0),
        "sandbox_before": _safe_dict(before_row.get("sandbox_summary")),
        "sandbox_after": _safe_dict(after_row.get("sandbox_summary")),
        "inventory_before": _safe_dict(before_row.get("inventory_summary")),
        "inventory_after": _safe_dict(after_row.get("inventory_summary")),
    }


def build_timeline_summary(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    timeline = _safe_dict(simulation_state.get("timeline"))
    snapshots = _safe_list(timeline.get("ticks"))
    world_consequences = _safe_list(_safe_dict(simulation_state.get("sandbox_state")).get("world_consequences"))

    snapshot_rows = []
    for snap in snapshots[:200]:
        if not isinstance(snap, dict):
            continue
        snapshot_rows.append({
            "tick": _safe_int(snap.get("tick"), 0),
            "snapshot_id": str(snap.get("tick")),
            "label": "tick",
        })

    snapshot_rows.sort(key=lambda x: (x["tick"], str(x["snapshot_id"])))

    return {
        "current_tick": _safe_int(simulation_state.get("tick"), 0),
        "snapshot_count": len(snapshot_rows),
        "snapshots": snapshot_rows[-50:],
        "timeline": timeline,
        "recent_world_consequences": [
            dict(item) for item in world_consequences[-10:]
            if isinstance(item, dict)
        ],
    }


def get_timeline_tick(simulation_state: Dict[str, Any], tick: int) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    timeline = _safe_dict(simulation_state.get("timeline"))
    snapshots = _safe_list(timeline.get("ticks"))
    tick = _safe_int(tick, 0)

    exact = None
    for snap in snapshots:
        if isinstance(snap, dict) and _safe_int(snap.get("tick"), -1) == tick:
            exact = dict(snap)
            break

    return {
        "requested_tick": tick,
        "found": exact is not None,
        "snapshot": exact or {},
    }
