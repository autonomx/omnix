from __future__ import annotations

import json

from app.rpg.survival_readiness import (
    attach_survival_readiness,
    build_survival_readiness_projection,
)
from app.rpg.survival_report_metrics import build_survival_report_metrics
from app.rpg.survival_report_polish import build_compact_survival_summary


def _row(
    turn: int,
    *,
    thirst: int = 20,
    pressure: str = "low",
    blocked: bool = False,
    duplicate_tick: bool = False,
    action: str = "drink_water",
):
    survival_result = {
        "ok": not blocked,
        "action_category": "survival",
        "action": action,
    }
    if blocked:
        survival_result["blocked_reason"] = "no_water_available"
    return {
        "turn": turn,
        "result": {
            "survival": {"hunger": 10, "thirst": thirst, "fatigue": 10},
            "survival_pressure": {"hunger": "low", "thirst": pressure, "fatigue": "low"},
            "survival_result": survival_result,
            "suggested_actions": [{"action_id": "survival:drink_water", "action": "drink water", "action_type": "survival"}],
            "survival_tick_result": {"applied": True, "reason": "standard_turn", "turn_id": f"turn:{turn}"},
        },
        "turn_contract": {
            "survival_tick_result": {"applied": True, "reason": "standard_turn", "turn_id": f"turn:{turn}:dup"} if duplicate_tick else {},
        },
    }


def test_bundle_bx_readiness_projection_reports_ready_for_healthy_metrics() -> None:
    metrics = build_survival_report_metrics([_row(1), _row(2, action="rest")])
    compact = build_compact_survival_summary(metrics)

    readiness = build_survival_readiness_projection(metrics, compact)

    assert readiness["format_version"] == "survival_readiness_v1"
    assert readiness["status"] == "ready"
    assert readiness["advisory_only"] is True
    assert readiness["warnings"] == []
    assert readiness["turns_observed"] == 2
    json.dumps(readiness)


def test_bundle_bx_readiness_projection_reports_watch_for_critical_pressure_and_blocked_actions() -> None:
    rows = [
        _row(1, thirst=95, pressure="critical", blocked=True, action="drink_water"),
        _row(2, thirst=95, pressure="critical", blocked=True, action="buy_water"),
        _row(3, thirst=95, pressure="critical", blocked=True, action="fill_waterskin"),
        _row(4, thirst=95, pressure="critical", blocked=False, action="rest"),
        _row(5, thirst=95, pressure="critical", blocked=False, action="make_camp"),
    ]
    metrics = build_survival_report_metrics(rows)
    compact = build_compact_survival_summary(metrics)

    readiness = build_survival_readiness_projection(metrics, compact)

    assert readiness["status"] == "watch"
    assert "critical_pressure_streak" in readiness["failed_advisory_gates"]
    assert "blocked_survival_actions>=3" in readiness["warnings"]
    assert "critical_pressure_streak_detected" in readiness["warnings"]
    assert "survival_action_no_improvement" not in readiness["failed_advisory_gates"]
    assert readiness["pressure_snapshot"]["thirst"]["critical_turns"] == 5


def test_bundle_bx_readiness_projection_reports_not_ready_for_double_tick_gate() -> None:
    metrics = build_survival_report_metrics([_row(1, duplicate_tick=True)])
    compact = build_compact_survival_summary(metrics)

    readiness = build_survival_readiness_projection(metrics, compact)

    assert readiness["status"] == "not_ready"
    assert "passive_tick_single_application" in readiness["failed_advisory_gates"]


def test_bundle_bx_attach_survival_readiness_is_noop_without_metrics_and_attaches_with_metrics() -> None:
    assert attach_survival_readiness({"hello": "world"}) == {"hello": "world"}

    metrics = build_survival_report_metrics([_row(1)])
    compact = build_compact_survival_summary(metrics)
    payload = attach_survival_readiness({"survival_report_metrics": metrics, "survival_summary": compact})

    assert payload["survival_readiness"]["status"] == "ready"
    assert payload["survival_readiness"]["source"] == "survival_readiness_projection"
    json.dumps(payload)
