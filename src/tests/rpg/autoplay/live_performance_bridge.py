"""Bridge live harness timing into advisory performance rows."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

SOURCE = "autoplay_live_performance_bridge_v3"


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
    stat = _stat(stage_summary, key)
    for field in ("avg_ms", "mean_ms", "duration_ms", "elapsed_ms"):
        value = _f(stat.get(field))
        if value is not None:
            return value
    value = _f(stage_summary.get(key))
    return value


def _summary_from_trace(trace: Any) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}
    if isinstance(trace, dict):
        items = trace.items()
    elif isinstance(trace, list):
        items = enumerate(trace)
    else:
        return summary
    for key, value in items:
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("stage") or value.get("phase") or key)
            duration = None
            for field in ("duration_ms", "elapsed_ms", "ms", "avg_ms", "mean_ms"):
                duration = _f(value.get(field))
                if duration is not None:
                    break
            if duration is not None:
                summary[name] = {"avg_ms": duration, "count": int(_f(value.get("count")) or 1), "max_ms": duration}
        else:
            duration = _f(value)
            if duration is not None:
                summary[str(key)] = {"avg_ms": duration, "count": 1, "max_ms": duration}
    return summary


def _find_trace_stage_summary(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        for container in (row, _d(row.get("performance")), _d(row.get("turn_result")), _d(row.get("runtime"))):
            for key in (
                "live_manual_substage_summary",
                "turn_perf_trace_summary",
                "manual_stage_trace_summary",
                "manual_harness_trace_summary",
            ):
                value = _d(container.get(key))
                if value:
                    return value
            for key in ("turn_perf_trace", "manual_stage_trace", "manual_harness_trace"):
                value = container.get(key)
                summary = _summary_from_trace(value)
                if summary:
                    return summary
    return {}


def _find_runtime_emission_key_summary(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidates = [row, _d(row.get("performance")), _d(row.get("turn_result")), _d(row.get("runtime"))]
        for container in candidates:
            result_keys = container.get("result_keys") or _d(container.get("traces")).get("result_keys")
            if not isinstance(result_keys, list):
                continue
            keys = {str(key) for key in result_keys}
            if not keys:
                continue
            summary: Dict[str, Any] = {}
            if "manual_harness_trace_summary" in keys or "manual_stage_trace" in keys:
                summary["manual_turn_ms"] = {"avg_ms": None, "count": 0, "source": "runtime_result_emission_keys"}
            if "turn_perf_trace_summary" in keys:
                summary["turn_perf_trace_summary_present"] = {"avg_ms": None, "count": 0, "source": "runtime_result_emission_keys"}
            if summary:
                summary["runtime_result_emission_keys"] = sorted(keys)
                return summary
    return {}


def build_live_performance_bridge_row(run_summary: Mapping[str, Any], rows: Iterable[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    row_list = [row for row in rows if isinstance(row, dict)]
    stage = _d(run_summary.get("stage_summary"))
    if not stage:
        stage = _d(_d(run_summary.get("summary")).get("stage_summary"))
    bridge_source = "live_harness_stage_summary"
    if not stage:
        stage = _find_trace_stage_summary(row_list)
        bridge_source = "result_trace_summary"
    if not stage:
        stage = _find_runtime_emission_key_summary(row_list)
        bridge_source = "runtime_result_emission_keys"
    if not stage:
        return {}
    manual = _avg(stage, "manual_turn_ms")
    state_bounds = _avg(stage, "state_bounds_ms") or _avg(stage, "state_snapshot_ms")
    enqueue = _avg(stage, "background_enqueue_ms") or _avg(stage, "deferred_enqueue_ms")
    pre_runtime_intent = _avg(stage, "pre_runtime_intent_llm_ms")
    deterministic_apply = _avg(stage, "deterministic_runtime_apply_ms")
    grounding_validation = _avg(stage, "grounding_validation_ms")
    repair = _avg(stage, "repair_ms")
    story_hooks = _avg(stage, "story_hooks_ms")
    record_build = _avg(stage, "record_build_ms")
    progress_eval = _avg(stage, "progress_eval_ms")
    base_response = _avg(stage, "base_response_ms")
    attributed = sum(
        value or 0.0
        for value in (
            state_bounds,
            enqueue,
            pre_runtime_intent,
            deterministic_apply,
            grounding_validation,
            repair,
            story_hooks,
            record_build,
            progress_eval,
            base_response,
        )
    )
    return {
        "turn_index": -1,
        "performance": {
            "manual_turn_stage_timing": {
                "manual_turn_ms": manual,
                "pre_runtime_intent_llm_ms": pre_runtime_intent,
                "deterministic_runtime_apply_ms": deterministic_apply,
                "grounding_validation_ms": grounding_validation,
                "repair_ms": repair,
                "state_snapshot_ms": state_bounds,
                "deferred_enqueue_ms": enqueue,
            },
            "live_manual_timing_bridge": {
                "source": SOURCE,
                "bridge_source": bridge_source,
                "stage_summary": stage,
                "manual_turn_unattributed_avg_ms": round(max(0.0, (manual or 0.0) - attributed), 3) if manual is not None else None,
                "note": "Live harness timing is coarser than interactive runtime sub-stage timing; missing sub-stages remain unknown until the live turn path emits them directly.",
            },
        },
        "source": SOURCE,
    }


def append_live_performance_bridge_row(rows: Iterable[Mapping[str, Any]], run_summary: Mapping[str, Any]) -> List[Dict[str, Any]]:
    bridged = [dict(row) for row in rows if isinstance(row, dict)]
    row = build_live_performance_bridge_row(run_summary, bridged)
    if row:
        bridged.append(row)
    return bridged
