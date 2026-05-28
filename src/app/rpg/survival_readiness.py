"""Bundle BX — compact survival long-run readiness projection.

This module consumes the v2 survival metrics and/or BT compact summary and emits
a small advisory readiness object for 100/1000-turn report gates.  It does not
fail gameplay by itself; callers decide whether to treat warnings as fatal.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

SURVIVAL_READINESS_VERSION = "survival_readiness_v1"
SURVIVAL_READINESS_SOURCE = "survival_readiness_projection"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_survival_readiness_projection(
    metrics: Mapping[str, Any],
    compact_summary: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    metrics = _safe_dict(metrics)
    compact_summary = _safe_dict(compact_summary)
    summary = _safe_dict(metrics.get("summary"))
    advisory = _safe_dict(metrics.get("advisory_gates"))
    failed = list(_safe_list(advisory.get("failed")))
    gates = _safe_dict(advisory.get("gates"))
    pressure = _safe_dict(compact_summary.get("pressure_snapshot"))
    if not pressure:
        max_pressure = _safe_dict(summary.get("max_pressure_value"))
        pressure_counts = _safe_dict(metrics.get("pressure_counts"))
        pressure = {
            need: {
                "max": _safe_int(max_pressure.get(need)),
                "critical_turns": _safe_int(_safe_dict(pressure_counts.get(need)).get("critical")),
                "high_turns": _safe_int(_safe_dict(pressure_counts.get(need)).get("high")),
            }
            for need in ("hunger", "thirst", "fatigue")
        }

    turns = _safe_int(summary.get("turns_observed") or compact_summary.get("turns_observed"))
    blocked = _safe_int(summary.get("blocked_survival_action_count") or compact_summary.get("blocked_actions"))
    direct = _safe_int(summary.get("direct_survival_action_count") or compact_summary.get("direct_actions"))
    passive = _safe_int(summary.get("passive_tick_count") or compact_summary.get("passive_ticks"))
    status = "ready"
    warnings: list[str] = []

    if failed:
        status = "watch"
        warnings.extend(f"gate:{name}" for name in failed)
    if blocked >= 3:
        status = "watch"
        warnings.append("blocked_survival_actions>=3")
    if any(_safe_int(_safe_dict(row).get("critical_turns")) >= 4 for row in pressure.values()):
        status = "watch"
        warnings.append("critical_pressure_streak_detected")
    if turns >= 25 and passive <= 0:
        status = "watch"
        warnings.append("no_passive_survival_ticks_observed")
    if direct >= 1 and passive >= 1 and direct > passive * 3:
        status = "watch"
        warnings.append("direct_survival_actions_dominate_ticks")
    if any(name in failed for name in ("passive_tick_single_application", "survival_action_no_improvement")):
        status = "not_ready"
    if compact_summary.get("status") == "warning" and status == "ready":
        status = "watch"
        warnings.append("compact_summary_warning")

    return {
        "format_version": SURVIVAL_READINESS_VERSION,
        "status": status,
        "advisory_only": True,
        "turns_observed": turns,
        "passive_ticks": passive,
        "direct_survival_actions": direct,
        "blocked_survival_actions": blocked,
        "failed_advisory_gates": failed,
        "warnings": sorted(set(warnings)),
        "pressure_snapshot": pressure,
        "gate_summaries": {
            name: {
                "ok": _safe_dict(gate).get("ok", True),
                "threshold": _safe_dict(gate).get("threshold"),
            }
            for name, gate in gates.items()
        },
        "source": SURVIVAL_READINESS_SOURCE,
    }


def attach_survival_readiness(report_payload: Mapping[str, Any]) -> Dict[str, Any]:
    payload = dict(_safe_dict(report_payload))
    metrics = _safe_dict(payload.get("survival_report_metrics"))
    compact = _safe_dict(payload.get("survival_summary"))
    if not metrics:
        return payload
    payload["survival_readiness"] = build_survival_readiness_projection(metrics, compact)
    return payload
