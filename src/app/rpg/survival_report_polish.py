"""Bundle BT — compact survival report polish helpers.

These helpers sit beside the existing BG/BQ metrics renderer and provide a small,
product-facing summary card that report writers can place near the top of an
autoplay/campaign report without copying the full debug timeline.
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict, Mapping

SURVIVAL_REPORT_POLISH_SOURCE = "survival_report_polish"
SURVIVAL_REPORT_POLISH_VERSION = "survival_report_polish_v1"
_NEEDS = ("hunger", "thirst", "fatigue")


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def build_compact_survival_summary(metrics: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = _safe_dict(metrics)
    summary = _safe_dict(metrics.get("summary"))
    gates = _safe_dict(metrics.get("advisory_gates"))
    failed = list(gates.get("failed") or [])
    pressure_counts = _safe_dict(metrics.get("pressure_counts"))
    max_pressure = _safe_dict(summary.get("max_pressure_value"))
    pressure_snapshot = {
        need: {
            "max": _safe_int(max_pressure.get(need)),
            "critical_turns": _safe_int(_safe_dict(pressure_counts.get(need)).get("critical")),
            "high_turns": _safe_int(_safe_dict(pressure_counts.get(need)).get("high")),
        }
        for need in _NEEDS
    }
    status = "healthy"
    if failed:
        status = "warning"
    elif any(row["critical_turns"] for row in pressure_snapshot.values()):
        status = "watch"

    return {
        "format_version": SURVIVAL_REPORT_POLISH_VERSION,
        "status": status,
        "turns_observed": _safe_int(summary.get("turns_observed")),
        "passive_ticks": _safe_int(summary.get("passive_tick_count")),
        "direct_actions": _safe_int(summary.get("direct_survival_action_count")),
        "blocked_actions": _safe_int(summary.get("blocked_survival_action_count")),
        "failed_advisory_gates": failed,
        "pressure_snapshot": pressure_snapshot,
        "source": SURVIVAL_REPORT_POLISH_SOURCE,
    }


def render_compact_survival_summary_html(metrics: Mapping[str, Any]) -> str:
    compact = build_compact_survival_summary(metrics)
    failed = compact["failed_advisory_gates"]
    pressure = _safe_dict(compact.get("pressure_snapshot"))
    need_cards = "".join(
        "<div class='survival-summary-need'>"
        f"<strong>{escape(need.title())}</strong>"
        f"<span>max {_safe_int(_safe_dict(pressure.get(need)).get('max'))}/100</span>"
        f"<small>critical {_safe_int(_safe_dict(pressure.get(need)).get('critical_turns'))} · high {_safe_int(_safe_dict(pressure.get(need)).get('high_turns'))}</small>"
        "</div>"
        for need in _NEEDS
    )
    failed_html = (
        "<ul>" + "".join(f"<li>{escape(_safe_str(name))}</li>" for name in failed) + "</ul>"
        if failed else
        "<p>No advisory survival gates are warning.</p>"
    )
    return "\n".join([
        f"<section id='survival-summary-card' class='survival-summary-card survival-summary-card--{escape(compact['status'])}'>",
        "<h2>Survival Summary</h2>",
        "<div class='survival-summary-grid'>",
        f"<div><strong>Status</strong><span>{escape(compact['status'])}</span></div>",
        f"<div><strong>Turns observed</strong><span>{compact['turns_observed']}</span></div>",
        f"<div><strong>Passive ticks</strong><span>{compact['passive_ticks']}</span></div>",
        f"<div><strong>Direct actions</strong><span>{compact['direct_actions']}</span></div>",
        f"<div><strong>Blocked actions</strong><span>{compact['blocked_actions']}</span></div>",
        "</div>",
        "<div class='survival-summary-needs'>",
        need_cards,
        "</div>",
        "<h3>Advisory Gates</h3>",
        failed_html,
        "</section>",
    ])
