from __future__ import annotations

import json
from pathlib import Path

from app.rpg.survival_report_metrics import build_survival_report_metrics
from app.rpg.survival_report_polish import (
    build_compact_survival_summary,
    render_compact_survival_summary_html,
)

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"


def _read_static(path: str) -> str:
    return (STATIC / path).read_text(encoding="utf-8")


def _row(turn: int, *, needs, pressure, blocked=False):
    survival_result = {
        "ok": not blocked,
        "action_category": "survival",
        "action": "drink_water",
    }
    if blocked:
        survival_result["blocked_reason"] = "no_water_available"
    return {
        "turn": turn,
        "result": {
            "survival": needs,
            "survival_pressure": pressure,
            "survival_result": survival_result,
            "survival_tick_result": {"applied": True, "reason": "standard_turn", "turn_id": f"turn:{turn}"},
        },
    }


def test_bundle_bt_survival_inspector_projects_inventory_hints_and_action_availability() -> None:
    js = _read_static("rpg/rpg-survival-inspector.js")

    assert "survivalInventorySummary" in js
    assert "renderInventorySummary" in js
    assert "actionAvailability" in js
    assert "rpg-survival-inventory" in js
    assert "rpg-survival-action-availability" in js
    assert "Waterskin" in js
    assert "Coin" in js
    assert "water ·" in js
    assert "available" in js


def test_bundle_bt_survival_inspector_css_has_inventory_and_availability_classes() -> None:
    css = _read_static("rpg/rpg-survival-inspector.css")

    assert ".rpg-survival-inventory" in css
    assert ".rpg-survival-action-availability" in css
    assert "grid-template-columns: repeat(4" in css
    assert "min-width: 150px" in css


def test_bundle_bt_compact_survival_summary_is_json_safe_and_status_healthy_when_no_warnings() -> None:
    rows = [
        _row(
            1,
            needs={"hunger": 10, "thirst": 20, "fatigue": 15},
            pressure={"hunger": "low", "thirst": "low", "fatigue": "low"},
        )
    ]
    metrics = build_survival_report_metrics(rows)
    compact = build_compact_survival_summary(metrics)
    html = render_compact_survival_summary_html(metrics)

    assert compact["format_version"] == "survival_report_polish_v1"
    assert compact["status"] == "healthy"
    assert compact["turns_observed"] == 1
    assert compact["failed_advisory_gates"] == []
    assert "Survival Summary" in html
    assert "No advisory survival gates are warning" in html
    json.dumps(compact)


def test_bundle_bt_compact_survival_summary_surfaces_advisory_gate_warnings() -> None:
    rows = []
    for turn in range(1, 7):
        rows.append(_row(
            turn,
            needs={"hunger": 10, "thirst": 95, "fatigue": 10},
            pressure={"hunger": "low", "thirst": "critical", "fatigue": "low"},
            blocked=turn <= 3,
        ))
    metrics = build_survival_report_metrics(rows)
    compact = build_compact_survival_summary(metrics)
    html = render_compact_survival_summary_html(metrics)

    assert compact["status"] == "warning"
    assert "critical_pressure_streak" in compact["failed_advisory_gates"]
    assert compact["pressure_snapshot"]["thirst"]["max"] == 95
    assert compact["pressure_snapshot"]["thirst"]["critical_turns"] == 6
    assert "survival-summary-card--warning" in html
    assert "critical_pressure_streak" in html
    assert "Blocked actions" in html
    json.dumps(compact)
