"""Bridge live harness timing into advisory performance rows."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

SOURCE = "autoplay_live_performance_bridge_v1"


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _stat(stage_summary: Mapping[str, Any], key: str) -> Dict[str, Any]:
    return _d(stage_summary.get(key))


def _avg(stage_summary: Mapping[str, Any], key: str) -> float | None:
    return _f(_stat(stage_summary, key).get("avg_ms"))


def build_live_performance_bridge_row(run_summary: Mapping[str, Any]) -> Dict[str, Any]:
    stage = _d(run_summary.get("stage_summary"))
    if not stage:
        stage = _d(_d(run_summary.get("summary")).get("stage_summary"))
    if not stage:
        return {}
    manual = _avg(stage, "manual_turn_ms")
    state_bounds = _avg(stage, "state_bounds_ms")
    enqueue = _avg(stage, "background_enqueue_ms")
    story_hooks = _avg(stage, "story_hooks_ms")
    record_build = _avg(stage, "record_build_ms")
    progress_eval = _avg(stage, "progress_eval_ms")
    base_response = _avg(stage, "base_response_ms")
    attributed = sum(value or 0.0 for value in (state_bounds, enqueue, story_hooks, record_build, progress_eval, base_response))
    return {
        "turn_index": -1,
        "performance": {
            "manual_turn_stage_timing": {
                "manual_turn_ms": manual,
                "state_snapshot_ms": state_bounds,
                "deferred_enqueue_ms": enqueue,
            },
            "live_manual_timing_bridge": {
                "source": SOURCE,
                "stage_summary": stage,
                "manual_turn_unattributed_avg_ms": round(max(0.0, (manual or 0.0) - attributed), 3) if manual is not None else None,
                "note": "Live harness timing is coarser than interactive runtime sub-stage timing; missing sub-stages remain unknown until the live turn path emits them directly.",
            },
        },
        "source": SOURCE,
    }


def append_live_performance_bridge_row(rows: Iterable[Mapping[str, Any]], run_summary: Mapping[str, Any]) -> List[Dict[str, Any]]:
    bridged = [dict(row) for row in rows if isinstance(row, dict)]
    row = build_live_performance_bridge_row(run_summary)
    if row:
        bridged.append(row)
    return bridged
