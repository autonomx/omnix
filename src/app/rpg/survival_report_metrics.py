"""Bundle BG — survival report/autoplay metric aggregation.

This module is deliberately runtime-shape tolerant: autoplay transcripts, turn
contracts, response payloads, and compact report sidecars have historically used
slightly different nesting.  BG walks those bounded rows and extracts canonical
BA-BF survival evidence without mutating gameplay state.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from html import escape
from typing import Any, Dict, Iterable, List, Mapping, Tuple

SURVIVAL_REPORT_SOURCE = "runtime_survival_report_metrics"
SURVIVAL_REPORT_VERSION = "survival_report_metrics_v1"
SURVIVAL_TIMELINE_LIMIT = 250
SURVIVAL_TOP_REASON_LIMIT = 12

_NEEDS: Tuple[str, str, str] = ("hunger", "thirst", "fatigue")
_PRESSURE_LABELS: Tuple[str, str, str, str] = ("low", "moderate", "high", "critical")
_DIRECT_ACTIONS = {
    "drink_water",
    "drink_from_waterskin",
    "eat_food",
    "eat_rations",
    "rest",
    "sleep",
    "make_camp",
    "buy_water",
    "buy_rations",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _norm_action(value: Any) -> str:
    return _safe_str(value).strip().lower().replace(" ", "_").replace(":", "_")


def _walk(value: Any, *, depth: int = 0, max_depth: int = 7) -> Iterable[Dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested, depth=depth + 1, max_depth=max_depth)
    elif isinstance(value, list):
        for item in value[:200]:
            yield from _walk(item, depth=depth + 1, max_depth=max_depth)


def _first_dict_by_key(row: Mapping[str, Any], key: str) -> Dict[str, Any]:
    for item in _walk(row):
        nested = _safe_dict(item.get(key))
        if nested:
            return nested
    return {}


def _all_dicts_by_key(row: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for item in _walk(row):
        nested = _safe_dict(item.get(key))
        if nested and id(nested) not in seen:
            seen.add(id(nested))
            out.append(nested)
    return out


def _turn_index(row: Mapping[str, Any], fallback: int) -> int:
    for item in _walk(row):
        value = item.get("turn_index") or item.get("turn") or item.get("tick")
        if value is not None:
            return _safe_int(value, fallback)
    return fallback


def _extract_survival_state(row: Mapping[str, Any]) -> Dict[str, Any]:
    candidates = (
        _first_dict_by_key(row, "survival"),
        _safe_dict(_first_dict_by_key(row, "survival_action_context").get("survival")),
    )
    for candidate in candidates:
        if any(key in candidate for key in _NEEDS):
            return candidate
    return {}


def _extract_pressure(row: Mapping[str, Any], survival_state: Mapping[str, Any]) -> Dict[str, str]:
    pressure = _first_dict_by_key(row, "survival_pressure")
    if pressure:
        return {need: _safe_str(pressure.get(need) or "low") for need in _NEEDS}
    out: Dict[str, str] = {}
    for need in _NEEDS:
        value = _safe_int(_safe_dict(survival_state).get(need), 0)
        if value >= 75:
            out[need] = "critical"
        elif value >= 50:
            out[need] = "high"
        elif value >= 25:
            out[need] = "moderate"
        else:
            out[need] = "low"
    return out


def _survival_action_results(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in _walk(row):
        candidate = _safe_dict(item.get("survival_result")) or item
        if _safe_str(candidate.get("action_category")) != "survival":
            continue
        action = _norm_action(candidate.get("action"))
        if not action:
            continue
        key = f"{action}:{candidate.get('ok')}:{candidate.get('blocked_reason')}:{candidate.get('reason')}:{id(candidate)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _survival_tick_results(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for tick_result in _all_dicts_by_key(row, "survival_tick_result"):
        key = _safe_str(tick_result.get("turn_id")) or str(id(tick_result))
        if key in seen:
            continue
        seen.add(key)
        out.append(tick_result)
    return out


def _row_timeline_entry(row: Mapping[str, Any], fallback_turn: int) -> Dict[str, Any]:
    turn = _turn_index(row, fallback_turn)
    survival_state = _extract_survival_state(row)
    pressure = _extract_pressure(row, survival_state)
    tick_results = _survival_tick_results(row)
    action_results = _survival_action_results(row)
    entry = {
        "turn": turn,
        "needs": {need: _safe_int(_safe_dict(survival_state).get(need), 0) for need in _NEEDS},
        "pressure": pressure,
        "tick_applied": any(bool(item.get("applied")) for item in tick_results),
        "tick_reason": _safe_str((tick_results[-1] if tick_results else {}).get("reason")),
        "actions": [_norm_action(item.get("action")) for item in action_results if _norm_action(item.get("action"))],
        "blocked_actions": [
            {
                "action": _norm_action(item.get("action")),
                "reason": _safe_str(item.get("blocked_reason") or item.get("reason")),
            }
            for item in action_results
            if item.get("ok") is False or item.get("blocked_reason")
        ],
    }
    return entry


def build_survival_report_metrics(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate survival evidence from autoplay/report rows."""
    timeline: List[Dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    blocked_counts: Counter[str] = Counter()
    blocked_reasons: Counter[str] = Counter()
    tick_counts: Counter[str] = Counter()
    pressure_counts: Dict[str, Counter[str]] = {need: Counter() for need in _NEEDS}
    max_pressure_value: Dict[str, int] = {need: 0 for need in _NEEDS}
    warning_counts: Counter[str] = Counter()

    for index, raw_row in enumerate(rows, start=1):
        row = _safe_dict(raw_row)
        if not row:
            continue
        entry = _row_timeline_entry(row, index)
        timeline.append(entry)

        for need in _NEEDS:
            label = _safe_str(entry["pressure"].get(need) or "low")
            pressure_counts[need][label] += 1
            max_pressure_value[need] = max(max_pressure_value[need], _safe_int(entry["needs"].get(need), 0))

        for tick in _survival_tick_results(row):
            if tick.get("applied"):
                tick_counts[_safe_str(tick.get("reason") or "unknown")] += 1
            elif tick.get("skipped"):
                tick_counts[f"skipped:{_safe_str(tick.get('reason') or 'unknown')}"] += 1

        for action_result in _survival_action_results(row):
            action = _norm_action(action_result.get("action"))
            if not action:
                continue
            if action_result.get("ok") is False or action_result.get("blocked_reason"):
                blocked_counts[action] += 1
                blocked_reasons[_safe_str(action_result.get("blocked_reason") or action_result.get("reason") or "unknown")] += 1
            else:
                action_counts[action] += 1

    passive_tick_count = sum(count for reason, count in tick_counts.items() if not reason.startswith("skipped:"))
    direct_action_count = sum(action_counts.values())
    blocked_action_count = sum(blocked_counts.values())

    if blocked_action_count:
        warning_counts["blocked_survival_actions"] = blocked_action_count
    if any(max_pressure_value[need] >= 90 for need in _NEEDS):
        warning_counts["critical_survival_pressure"] = sum(1 for need in _NEEDS if max_pressure_value[need] >= 90)
    if direct_action_count and passive_tick_count and direct_action_count > passive_tick_count * 2:
        warning_counts["possible_survival_action_loop"] = direct_action_count

    capped_timeline = timeline[-SURVIVAL_TIMELINE_LIMIT:]
    return {
        "format_version": SURVIVAL_REPORT_VERSION,
        "summary": {
            "turns_observed": len(timeline),
            "passive_tick_count": passive_tick_count,
            "direct_survival_action_count": direct_action_count,
            "blocked_survival_action_count": blocked_action_count,
            "max_pressure_value": dict(max_pressure_value),
            "warning_counts": dict(warning_counts),
        },
        "tick_counts_by_reason": dict(sorted(tick_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "blocked_action_counts": dict(sorted(blocked_counts.items())),
        "blocked_reason_counts": dict(blocked_reasons.most_common(SURVIVAL_TOP_REASON_LIMIT)),
        "pressure_counts": {
            need: {label: pressure_counts[need].get(label, 0) for label in _PRESSURE_LABELS}
            for need in _NEEDS
        },
        "timeline": capped_timeline,
        "source": SURVIVAL_REPORT_SOURCE,
    }


def merge_survival_report_metrics(report_payload: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    payload = deepcopy(_safe_dict(report_payload))
    metrics = build_survival_report_metrics(rows)
    payload["survival_report_metrics"] = metrics
    payload.setdefault("report_sections", {})
    sections = _safe_dict(payload.get("report_sections"))
    sections["survival"] = metrics
    payload["report_sections"] = sections
    return payload


def render_survival_report_html(metrics: Mapping[str, Any]) -> str:
    metrics = _safe_dict(metrics)
    summary = _safe_dict(metrics.get("summary"))
    pressure_counts = _safe_dict(metrics.get("pressure_counts"))
    action_counts = _safe_dict(metrics.get("action_counts"))
    blocked_counts = _safe_dict(metrics.get("blocked_action_counts"))
    tick_counts = _safe_dict(metrics.get("tick_counts_by_reason"))
    timeline = _safe_list(metrics.get("timeline"))[-40:]

    def rows_for_counts(counts: Mapping[str, Any]) -> str:
        if not counts:
            return "<tr><td colspan='2'>None</td></tr>"
        return "".join(
            f"<tr><td>{escape(_safe_str(key))}</td><td>{_safe_int(value)}</td></tr>"
            for key, value in sorted(counts.items(), key=lambda kv: (-_safe_int(kv[1]), _safe_str(kv[0])))
        )

    pressure_rows = "".join(
        "<tr>"
        f"<td>{escape(need)}</td>"
        f"<td>{_safe_int(_safe_dict(pressure_counts.get(need)).get('low'))}</td>"
        f"<td>{_safe_int(_safe_dict(pressure_counts.get(need)).get('moderate'))}</td>"
        f"<td>{_safe_int(_safe_dict(pressure_counts.get(need)).get('high'))}</td>"
        f"<td>{_safe_int(_safe_dict(pressure_counts.get(need)).get('critical'))}</td>"
        "</tr>"
        for need in _NEEDS
    )
    timeline_rows = "".join(
        "<tr>"
        f"<td>{_safe_int(_safe_dict(row).get('turn'))}</td>"
        f"<td>{escape(_safe_str(_safe_dict(row).get('tick_reason')))}</td>"
        f"<td>{escape(', '.join(_safe_str(a) for a in _safe_list(_safe_dict(row).get('actions'))))}</td>"
        f"<td>{escape(', '.join(_safe_str(_safe_dict(a).get('action')) + ':' + _safe_str(_safe_dict(a).get('reason')) for a in _safe_list(_safe_dict(row).get('blocked_actions'))))}</td>"
        f"<td>{escape(str(_safe_dict(row).get('needs') or {}))}</td>"
        "</tr>"
        for row in timeline
    ) or "<tr><td colspan='5'>No survival timeline evidence found.</td></tr>"

    return "\n".join(
        [
            "<section id='survival-report-metrics' class='report-section survival-report-metrics'>",
            "<h2>Survival Report Metrics</h2>",
            "<div class='metric-grid'>",
            f"<div><strong>Turns observed</strong><span>{_safe_int(summary.get('turns_observed'))}</span></div>",
            f"<div><strong>Passive ticks</strong><span>{_safe_int(summary.get('passive_tick_count'))}</span></div>",
            f"<div><strong>Direct survival actions</strong><span>{_safe_int(summary.get('direct_survival_action_count'))}</span></div>",
            f"<div><strong>Blocked survival actions</strong><span>{_safe_int(summary.get('blocked_survival_action_count'))}</span></div>",
            "</div>",
            "<h3>Passive Tick Reasons</h3>",
            f"<table><tbody>{rows_for_counts(tick_counts)}</tbody></table>",
            "<h3>Direct Survival Actions</h3>",
            f"<table><tbody>{rows_for_counts(action_counts)}</tbody></table>",
            "<h3>Blocked Survival Actions</h3>",
            f"<table><tbody>{rows_for_counts(blocked_counts)}</tbody></table>",
            "<h3>Pressure Distribution</h3>",
            "<table><thead><tr><th>Need</th><th>Low</th><th>Moderate</th><th>High</th><th>Critical</th></tr></thead>",
            f"<tbody>{pressure_rows}</tbody></table>",
            "<h3>Recent Survival Timeline</h3>",
            "<table><thead><tr><th>Turn</th><th>Tick</th><th>Actions</th><th>Blocked</th><th>Needs</th></tr></thead>",
            f"<tbody>{timeline_rows}</tbody></table>",
            "</section>",
        ]
    )
