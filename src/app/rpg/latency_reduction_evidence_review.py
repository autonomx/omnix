"""Evidence review helpers for Phase 13.5 latency-reduction validation.

The helper compares a latency-reduced interactive matrix performance payload
against the accepted Phase 13.3 baseline. It is advisory-only: it never decides
simulation state or production readiness by itself.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

REVIEW_SOURCE = "phase13_5_latency_reduction_evidence_review_v1"
REVIEW_JSON_NAME = "latency-reduction-evidence-review.json"
_BASELINE_PROVIDER_AVG = 5.42
_BASELINE_MAX_TURN = 7.45
_BASELINE_P95 = 6.36
_MIN_PROVIDER_IMPROVEMENT_RATIO = 0.15
_MAX_FAST_PATH_REGRESSION_SECONDS = 1.0

_FAST_SCENARIOS = {"combat_basic_attack", "travel_route_choice", "survival_food_and_water"}
_PROVIDER_SCENARIOS = {
    "rumor_news_no_backed_state",
    "commerce_food_purchase",
    "party_companion_recruitment",
    "quest_no_backed_state",
    "npc_dialogue_persona",
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _f(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _scenario_rows(payload: Mapping[str, Any]) -> list[Dict[str, Any]]:
    return [_d(row) for row in payload.get("scenarios") or [] if isinstance(row, dict)]


def _avg_for(rows: list[Mapping[str, Any]], names: set[str]) -> float:
    values = [
        _f(row.get("avg_turn_seconds"))
        for row in rows
        if _s(row.get("scenario_id")) in names and _f(row.get("completed_turns")) > 0
    ]
    return round(sum(values) / len(values), 4) if values else 0.0


def _source_flags(payload: Mapping[str, Any]) -> Dict[str, Any]:
    flags = _d(payload.get("phase13_4_latency_reduction"))
    if flags:
        return flags
    return _d(_d(payload.get("summary")).get("phase13_4_latency_reduction"))


def build_latency_reduction_evidence_review(
    performance_payload: Mapping[str, Any],
    *,
    evidence_name: str = "latency-reduced-interactive-intent-matrix.zip",
) -> Dict[str, Any]:
    payload = _d(performance_payload)
    rows = _scenario_rows(payload)
    provider_avg = _avg_for(rows, _PROVIDER_SCENARIOS)
    fast_avg = _avg_for(rows, _FAST_SCENARIOS)
    p95 = _f(payload.get("p95_turn_seconds"))
    max_turn = _f(payload.get("max_turn_seconds"))
    source_flags = _source_flags(payload)
    improvement = round((_BASELINE_PROVIDER_AVG - provider_avg) / _BASELINE_PROVIDER_AVG, 4) if provider_avg else 0.0

    warnings: list[str] = []
    if not source_flags.get("enabled"):
        warnings.append("latency_reduction_runner_not_confirmed")
    if provider_avg <= 0:
        warnings.append("provider_backed_average_missing")
    elif improvement < _MIN_PROVIDER_IMPROVEMENT_RATIO:
        warnings.append("provider_backed_improvement_below_target")
    if fast_avg > _MAX_FAST_PATH_REGRESSION_SECONDS:
        warnings.append("deterministic_fast_path_regression")
    if max_turn > _BASELINE_MAX_TURN:
        warnings.append("max_turn_regressed_against_baseline")
    if p95 > _BASELINE_P95:
        warnings.append("p95_turn_regressed_against_baseline")

    latency_confirmed = not warnings or warnings == ["latency_reduction_runner_not_confirmed"]
    next_target = (
        "promote_or_repeat_latency_reduction_with_live_evidence"
        if latency_confirmed
        else "phase13_6_follow_up_provider_backed_latency_target"
    )
    return {
        "format_version": "phase13_5_latency_reduction_evidence_review_v1",
        "ok": latency_confirmed and bool(source_flags.get("enabled")),
        "advisory_only": True,
        "source": REVIEW_SOURCE,
        "evidence_name": evidence_name,
        "baseline": {
            "provider_backed_avg_turn_seconds": _BASELINE_PROVIDER_AVG,
            "p95_turn_seconds": _BASELINE_P95,
            "max_turn_seconds": _BASELINE_MAX_TURN,
        },
        "metrics": {
            "provider_backed_avg_turn_seconds": provider_avg,
            "deterministic_fast_path_avg_turn_seconds": fast_avg,
            "p95_turn_seconds": round(p95, 4),
            "max_turn_seconds": round(max_turn, 4),
            "provider_backed_improvement_ratio": improvement,
        },
        "latency_reduction_source_flags": source_flags,
        "warnings": warnings,
        "recommended_next_target": next_target,
    }


def write_latency_reduction_evidence_review(
    output_root: str | Path,
    performance_payload: Mapping[str, Any],
    *,
    evidence_name: str = "latency-reduced-interactive-intent-matrix.zip",
) -> Dict[str, Any]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    review = build_latency_reduction_evidence_review(performance_payload, evidence_name=evidence_name)
    json_path = output_root / REVIEW_JSON_NAME
    json_path.write_text(json.dumps(review, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return {"ok": True, "review": review, "json_path": str(json_path), "source": REVIEW_SOURCE}
