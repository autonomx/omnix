"""Phase 7 — Replay / Timeline Helpers.

Provides:
- timeline/replay helpers
- Uses existing snapshot + diff system
- No UI logic
"""

from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def list_snapshots(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List available snapshots from the simulation state.

    Returns up to 100 snapshots, sorted by (tick, snapshot_id).
    """
    simulation_state = simulation_state or {}
    snapshots = _safe_list(simulation_state.get("snapshots"))
    out = []
    for item in snapshots:
        if not isinstance(item, dict):
            continue
        out.append({
            "snapshot_id": item.get("snapshot_id"),
            "tick": int(item.get("tick", 0) or 0),
            "label": item.get("label", ""),
            "hash": item.get("hash", ""),
        })
    out.sort(key=lambda x: (x["tick"], str(x["snapshot_id"])))
    return out[:100]


def get_snapshot(simulation_state: Dict[str, Any], snapshot_id: str) -> Dict[str, Any]:
    """Get a specific snapshot by id."""
    snapshots = _safe_list((simulation_state or {}).get("snapshots"))
    for item in snapshots:
        if isinstance(item, dict) and item.get("snapshot_id") == snapshot_id:
            return dict(item)
    return {}


def rollback_to_snapshot(simulation_state: Dict[str, Any], snapshot_id: str) -> Dict[str, Any]:
    """Rollback the simulation state to a specific snapshot.

    If the snapshot is not found, returns the current state unchanged.
    """
    snap = get_snapshot(simulation_state, snapshot_id)
    if not snap:
        return dict(simulation_state or {})
    restored = _safe_dict(snap.get("state"))
    restored.setdefault("debug_meta", {})
    restored["debug_meta"]["last_step_reason"] = "rollback"
    restored["debug_meta"]["rollback_snapshot_id"] = snapshot_id
    return restored


def summarize_timeline(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize the timeline: snapshot count, event count, consequence count."""
    simulation_state = simulation_state or {}
    snapshots = list_snapshots(simulation_state)
    events = _safe_list(simulation_state.get("events"))
    consequences = _safe_list(simulation_state.get("consequences"))
    return {
        "tick": int(simulation_state.get("tick", 0) or 0),
        "snapshot_count": len(snapshots),
        "recent_snapshots": snapshots[-10:],
        "event_count": len(events),
        "consequence_count": len(consequences),
    }