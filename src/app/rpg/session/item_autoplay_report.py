"""Autoplay/report payload helpers for deterministic RPG item coverage."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.rpg.session.item_diagnostics import build_item_diagnostics
from app.rpg.session.item_objectives import build_item_objectives
from app.rpg.session.item_report_session import build_item_report_for_session
from app.rpg.session.item_scenarios import build_item_scenario_plan

ITEM_AUTOPLAY_REPORT_SOURCE = "engine_item_autoplay_report_v1"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _turn(state: dict[str, Any]) -> int:
    return int(state.get("current_turn") or state.get("turn_count") or 0)


def _trace_counts(state: dict[str, Any]) -> dict[str, int]:
    mechanics = _safe_dict(state.get("mechanics"))
    keys = (
        "item_traces",
        "market_traces",
        "pickup_traces",
        "item_effect_traces",
        "item_combat_traces",
        "item_report_sections",
        "item_diagnostic_traces",
        "item_scenario_traces",
    )
    return {key: len(_safe_list(mechanics.get(key))) for key in keys if _safe_list(mechanics.get(key))}


def _recent_trace_events(state: dict[str, Any], *, limit: int) -> list[str]:
    mechanics = _safe_dict(state.get("mechanics"))
    events: list[str] = []
    for trace in _safe_list(mechanics.get("item_traces"))[: max(0, int(limit or 0))]:
        trace_dict = _safe_dict(trace)
        event = trace_dict.get("event") or trace_dict.get("session_event") or trace_dict.get("stage")
        if event:
            events.append(str(event))
    return events


def build_item_autoplay_report_payload(
    state: dict[str, Any],
    *,
    station: str | None = None,
    genre: str = "classic_fantasy",
    objective_limit: int = 8,
    scenario_limit: int = 8,
    recent_trace_limit: int = 8,
) -> dict[str, Any]:
    """Build a compact deterministic item coverage payload for autoplay reports."""

    source = deepcopy(_safe_dict(state))
    report = build_item_report_for_session(source, station=station, genre=genre, source="autoplay_report")
    diagnostics = build_item_diagnostics(
        source,
        station=station,
        genre=genre,
        objective_limit=objective_limit,
        scenario_limit=scenario_limit,
    )
    objectives = build_item_objectives(source, station=station, genre=genre, limit=objective_limit)
    scenario = build_item_scenario_plan(source, station=station, genre=genre, limit=scenario_limit)
    coverage = _safe_dict(report.get("coverage"))
    summary = _safe_dict(report.get("summary"))
    diagnostics_summary = _safe_dict(diagnostics.get("summary"))
    scenario_summary = _safe_dict(scenario.get("summary"))
    objective_list = _safe_list(objectives.get("objectives"))
    payload_summary = {
        "turn": _turn(source),
        "coverage_score": coverage.get("score", summary.get("coverage_score", 0)),
        "coverage_gap_count": len(_safe_list(coverage.get("gaps"))),
        "objective_count": len(objective_list),
        "scenario_step_count": int(scenario_summary.get("step_count") or len(_safe_list(scenario.get("steps")))),
        "blocked_step_count": int(scenario_summary.get("blocked_step_count") or 0),
        "audit_issue_count": int(diagnostics_summary.get("audit_issue_count") or 0),
        "audit_warning_count": int(diagnostics_summary.get("audit_warning_count") or 0),
        "trace_counts": _trace_counts(source),
        "recent_trace_events": _recent_trace_events(source, limit=recent_trace_limit),
    }
    return {
        "ok": True,
        "summary": payload_summary,
        "report": report,
        "diagnostics": diagnostics,
        "objectives": objective_list,
        "scenario": scenario,
        "mechanics_source": ITEM_AUTOPLAY_REPORT_SOURCE,
    }


def build_item_autoplay_report_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Convert an item autoplay payload into compact report rows."""

    summary = _safe_dict(payload.get("summary"))
    rows = [
        {"label": "Coverage score", "value": str(summary.get("coverage_score", 0))},
        {"label": "Coverage gaps", "value": str(summary.get("coverage_gap_count", 0))},
        {"label": "Objectives", "value": str(summary.get("objective_count", 0))},
        {"label": "Scenario steps", "value": str(summary.get("scenario_step_count", 0))},
        {"label": "Blocked steps", "value": str(summary.get("blocked_step_count", 0))},
        {"label": "Audit issues", "value": str(summary.get("audit_issue_count", 0))},
        {"label": "Audit warnings", "value": str(summary.get("audit_warning_count", 0))},
    ]
    trace_counts = _safe_dict(summary.get("trace_counts"))
    if trace_counts:
        rows.append(
            {
                "label": "Trace buckets",
                "value": ", ".join(f"{key}:{value}" for key, value in sorted(trace_counts.items())),
            }
        )
    return rows
