"""Bundle BX/BY — compact survival long-run readiness projection.

This module consumes the v2 survival metrics and/or BT compact summary and emits
a small advisory readiness object for 100/1000-turn report gates.  It does not
fail gameplay by itself; callers decide whether to treat warnings as fatal.  BY
adds a tiny HTML renderer so readiness can be shipped as a first-class report
artifact beside metrics and summary files.
"""
from __future__ import annotations

from html import escape
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


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


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


def render_survival_readiness_html(readiness: Mapping[str, Any]) -> str:
    readiness = _safe_dict(readiness)
    status = _safe_str(readiness.get("status") or "unknown")
    warnings = _safe_list(readiness.get("warnings"))
    failed = _safe_list(readiness.get("failed_advisory_gates"))
    pressure = _safe_dict(readiness.get("pressure_snapshot"))
    warning_html = (
        "<ul>" + "".join(f"<li>{escape(_safe_str(item))}</li>" for item in warnings) + "</ul>"
        if warnings else
        "<p>No survival readiness warnings.</p>"
    )
    failed_html = (
        "<ul>" + "".join(f"<li>{escape(_safe_str(item))}</li>" for item in failed) + "</ul>"
        if failed else
        "<p>No failed advisory survival gates.</p>"
    )
    pressure_html = "".join(
        "<div class='survival-readiness-pressure'>"
        f"<strong>{escape(_safe_str(need).title())}</strong>"
        f"<span>max {_safe_int(_safe_dict(row).get('max'))}/100</span>"
        f"<small>critical {_safe_int(_safe_dict(row).get('critical_turns'))} · high {_safe_int(_safe_dict(row).get('high_turns'))}</small>"
        "</div>"
        for need, row in pressure.items()
    )
    return "\n".join([
        f"<section id='survival-readiness' class='survival-readiness survival-readiness--{escape(status)}'>",
        "<h2>Survival Readiness</h2>",
        "<div class='survival-readiness-grid'>",
        f"<div><strong>Status</strong><span>{escape(status)}</span></div>",
        f"<div><strong>Advisory only</strong><span>{str(bool(readiness.get('advisory_only'))).lower()}</span></div>",
        f"<div><strong>Turns observed</strong><span>{_safe_int(readiness.get('turns_observed'))}</span></div>",
        f"<div><strong>Passive ticks</strong><span>{_safe_int(readiness.get('passive_ticks'))}</span></div>",
        f"<div><strong>Direct actions</strong><span>{_safe_int(readiness.get('direct_survival_actions'))}</span></div>",
        f"<div><strong>Blocked actions</strong><span>{_safe_int(readiness.get('blocked_survival_actions'))}</span></div>",
        "</div>",
        "<h3>Pressure Snapshot</h3>",
        f"<div class='survival-readiness-pressure-grid'>{pressure_html}</div>",
        "<h3>Warnings</h3>",
        warning_html,
        "<h3>Failed Advisory Gates</h3>",
        failed_html,
        "</section>",
    ])


def attach_survival_readiness(report_payload: Mapping[str, Any]) -> Dict[str, Any]:
    payload = dict(_safe_dict(report_payload))
    metrics = _safe_dict(payload.get("survival_report_metrics"))
    compact = _safe_dict(payload.get("survival_summary"))
    if not metrics:
        return payload
    payload["survival_readiness"] = build_survival_readiness_projection(metrics, compact)
    return payload
