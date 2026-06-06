"""Interactive intent matrix performance review helpers.

Phase 13.3 uses the uploaded interactive intent matrix run as accepted
production-readiness evidence.  The run already emits a matrix performance JSON;
this module turns that JSON into an explicit review artifact pair so matrix runs
have the same structured review surface that Phase 13.2 added for autoplay.

The review is advisory-only and never decides simulation truth.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

REVIEW_JSON_NAME = "interactive-intent-matrix-performance-review.json"
REVIEW_HTML_NAME = "interactive-intent-matrix-performance-review.html"
REVIEW_SOURCE = "interactive_matrix_performance_review"
DEFAULT_TARGETS = {
    "avg_turn_seconds": 4.0,
    "p95_turn_seconds": 8.0,
    "max_turn_seconds": 10.0,
    "provider_backed_avg_turn_seconds": 5.0,
    "deterministic_avg_turn_seconds": 1.0,
    "runtime_apply_share": 0.85,
}
PROVIDER_BACKED_SCENARIOS = {
    "commerce_food_purchase",
    "npc_dialogue_persona",
    "party_companion_recruitment",
    "quest_no_backed_state",
    "rumor_news_no_backed_state",
}
DETERMINISTIC_FAST_SCENARIOS = {
    "combat_basic_attack",
    "survival_food_and_water",
    "travel_route_choice",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _avg(values: Iterable[float]) -> float:
    clean = [float(value) for value in values]
    return round(sum(clean) / len(clean), 4) if clean else 0.0


def _scenario_rows(performance: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(item) for item in performance.get("scenarios") or [] if isinstance(item, dict)]


def _avg_for_ids(rows: Iterable[Mapping[str, Any]], ids: set[str]) -> float:
    values = [
        _safe_float(row.get("avg_turn_seconds"))
        for row in rows
        if _safe_str(row.get("scenario_id")) in ids and _safe_float(row.get("completed_turns")) > 0
    ]
    return _avg(values)


def _slowest(rows: Iterable[Mapping[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    sorted_rows = sorted(
        [_safe_dict(row) for row in rows],
        key=lambda row: _safe_float(row.get("avg_turn_seconds")),
        reverse=True,
    )
    return [
        {
            "scenario_id": _safe_str(row.get("scenario_id")),
            "completed_turns": _safe_int(row.get("completed_turns")),
            "avg_turn_seconds": round(_safe_float(row.get("avg_turn_seconds")), 4),
            "max_turn_seconds": round(_safe_float(row.get("max_turn_seconds")), 4),
            "slow_turn_count": _safe_int(row.get("slow_turn_count")),
        }
        for row in sorted_rows[:limit]
    ]


def build_interactive_matrix_performance_review(
    performance: Mapping[str, Any],
    *,
    evidence_name: str = "interactive-intent-matrix.zip",
    targets: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Build an advisory matrix performance review from matrix performance JSON."""
    performance = _safe_dict(performance)
    targets = dict(DEFAULT_TARGETS if targets is None else targets)
    rows = _scenario_rows(performance)
    phase_totals = _safe_dict(performance.get("phase_totals_seconds"))
    turn_total = _safe_float(phase_totals.get("turn_total_seconds"))
    runtime_apply_total = _safe_float(phase_totals.get("runtime_apply_turn_seconds"))
    runtime_apply_share = round(runtime_apply_total / turn_total, 4) if turn_total > 0 else 0.0
    provider_avg = _avg_for_ids(rows, PROVIDER_BACKED_SCENARIOS)
    deterministic_avg = _avg_for_ids(rows, DETERMINISTIC_FAST_SCENARIOS)
    metrics = {
        "scenario_count": _safe_int(performance.get("scenario_count")),
        "avg_turn_seconds": round(_safe_float(performance.get("avg_turn_seconds")), 4),
        "p95_turn_seconds": round(_safe_float(performance.get("p95_turn_seconds")), 4),
        "max_turn_seconds": round(_safe_float(performance.get("max_turn_seconds")), 4),
        "provider_backed_avg_turn_seconds": provider_avg,
        "deterministic_avg_turn_seconds": deterministic_avg,
        "runtime_apply_share": runtime_apply_share,
    }
    warnings: List[str] = []
    if metrics["avg_turn_seconds"] > targets["avg_turn_seconds"]:
        warnings.append("matrix_avg_turn_seconds_above_target")
    if metrics["p95_turn_seconds"] > targets["p95_turn_seconds"]:
        warnings.append("matrix_p95_turn_seconds_above_target")
    if metrics["max_turn_seconds"] > targets["max_turn_seconds"]:
        warnings.append("matrix_max_turn_seconds_above_target")
    if provider_avg > targets["provider_backed_avg_turn_seconds"]:
        warnings.append("provider_backed_avg_turn_seconds_above_target")
    if deterministic_avg > targets["deterministic_avg_turn_seconds"]:
        warnings.append("deterministic_fast_path_avg_turn_seconds_above_target")
    if runtime_apply_share > targets["runtime_apply_share"]:
        warnings.append("runtime_apply_share_dominates_turn_time")
    return {
        "format_version": "interactive_intent_matrix_performance_review_v1",
        "ok": not warnings,
        "advisory_only": True,
        "source": REVIEW_SOURCE,
        "evidence_name": evidence_name,
        "targets": targets,
        "metrics": metrics,
        "warnings": warnings,
        "slowest_scenarios": _slowest(rows),
        "phase_totals_seconds": {key: round(_safe_float(value), 4) for key, value in sorted(phase_totals.items())},
        "recommended_next_target": _recommended_next_target(warnings),
    }


def _recommended_next_target(warnings: Iterable[str]) -> str:
    warning_set = set(warnings)
    if "provider_backed_avg_turn_seconds_above_target" in warning_set or "runtime_apply_share_dominates_turn_time" in warning_set:
        return "bounded_latency_reduction_for_provider_backed_intent_paths"
    if "deterministic_fast_path_avg_turn_seconds_above_target" in warning_set:
        return "restore_deterministic_fast_path_latency"
    return "continue_operator_evidence_collection"


def render_interactive_matrix_performance_review_html(review: Mapping[str, Any]) -> str:
    review = _safe_dict(review)
    metrics = _safe_dict(review.get("metrics"))
    warnings = review.get("warnings") or []
    warning_items = "".join(f"<li>{escape(_safe_str(item))}</li>" for item in warnings) or "<li>none</li>"
    metric_rows = "".join(
        f"<tr><td>{escape(_safe_str(key))}</td><td>{escape(_safe_str(value))}</td></tr>"
        for key, value in metrics.items()
    )
    scenario_rows = "".join(
        "<tr>"
        f"<td>{escape(_safe_str(row.get('scenario_id')))}</td>"
        f"<td>{escape(_safe_str(row.get('completed_turns')))}</td>"
        f"<td>{escape(_safe_str(row.get('avg_turn_seconds')))}</td>"
        f"<td>{escape(_safe_str(row.get('max_turn_seconds')))}</td>"
        f"<td>{escape(_safe_str(row.get('slow_turn_count')))}</td>"
        "</tr>"
        for row in review.get("slowest_scenarios") or []
    )
    return "\n".join(
        [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><title>Interactive Matrix Performance Review</title>",
            "<style>body{font-family:system-ui,sans-serif;margin:24px;line-height:1.45}table{border-collapse:collapse;margin:12px 0}td,th{border:1px solid #ddd;padding:6px 10px}.status{font-weight:800}</style>",
            "</head><body>",
            "<h1>Interactive Matrix Performance Review</h1>",
            f"<p class='status'>ok: {str(bool(review.get('ok'))).lower()}</p>",
            f"<p>evidence: {escape(_safe_str(review.get('evidence_name')))}</p>",
            f"<p>recommended next target: {escape(_safe_str(review.get('recommended_next_target')))}</p>",
            "<h2>Metrics</h2><table><tbody>",
            metric_rows,
            "</tbody></table>",
            "<h2>Warnings</h2>",
            f"<ul>{warning_items}</ul>",
            "<h2>Slowest scenarios</h2>",
            "<table><thead><tr><th>Scenario</th><th>Turns</th><th>Avg</th><th>Max</th><th>Slow turns</th></tr></thead><tbody>",
            scenario_rows,
            "</tbody></table>",
            "</body></html>",
        ]
    )


def write_interactive_matrix_performance_review(
    output_root: str | Path,
    performance: Mapping[str, Any],
    *,
    evidence_name: str = "interactive-intent-matrix.zip",
) -> Dict[str, Any]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    review = build_interactive_matrix_performance_review(performance, evidence_name=evidence_name)
    json_path = output_root / REVIEW_JSON_NAME
    html_path = output_root / REVIEW_HTML_NAME
    json_path.write_text(json.dumps(review, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    html_path.write_text(render_interactive_matrix_performance_review_html(review), encoding="utf-8")
    return {
        "ok": True,
        "source": REVIEW_SOURCE,
        "review": review,
        "json_path": str(json_path),
        "html_path": str(html_path),
    }


def write_interactive_matrix_performance_review_from_file(
    performance_json_path: str | Path,
    *,
    output_root: str | Path | None = None,
    evidence_name: str = "interactive-intent-matrix.zip",
) -> Dict[str, Any]:
    performance_json_path = Path(performance_json_path)
    performance = json.loads(performance_json_path.read_text(encoding="utf-8"))
    return write_interactive_matrix_performance_review(
        output_root or performance_json_path.parent,
        performance,
        evidence_name=evidence_name,
    )
