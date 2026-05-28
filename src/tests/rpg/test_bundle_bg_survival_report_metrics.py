from __future__ import annotations

import json

from app.rpg.survival_report_metrics import (
    build_survival_report_metrics,
    merge_survival_report_metrics,
    render_survival_report_html,
)


def _turn_row(turn, *, survival, pressure=None, tick_result=None, survival_result=None):
    return {
        "turn": turn,
        "turn_contract": {
            "turn_id": f"turn:{turn}",
            "tick": turn,
            "survival": survival,
            "survival_pressure": pressure or {},
            "survival_tick_result": tick_result or {},
            "resolved_result": {
                "survival_result": survival_result or {},
            },
        },
        "result": {
            "survival": survival,
            "survival_pressure": pressure or {},
            "survival_tick_result": tick_result or {},
            "survival_result": survival_result or {},
        },
    }


def test_bundle_bg_aggregates_passive_ticks_actions_blocked_actions_and_pressure() -> None:
    rows = [
        _turn_row(
            1,
            survival={"hunger": 10, "thirst": 22, "fatigue": 30},
            pressure={"hunger": "low", "thirst": "low", "fatigue": "moderate"},
            tick_result={
                "applied": True,
                "reason": "standard_turn",
                "turn_id": "turn:1",
            },
        ),
        _turn_row(
            2,
            survival={"hunger": 12, "thirst": 25, "fatigue": 32},
            pressure={"hunger": "low", "thirst": "moderate", "fatigue": "moderate"},
            tick_result={
                "applied": True,
                "reason": "travel_turn",
                "turn_id": "turn:2",
            },
        ),
        _turn_row(
            3,
            survival={"hunger": 12, "thirst": 0, "fatigue": 32},
            pressure={"hunger": "low", "thirst": "low", "fatigue": "moderate"},
            tick_result={
                "applied": False,
                "skipped": True,
                "reason": "direct_survival_action",
                "turn_id": "turn:3",
            },
            survival_result={
                "ok": True,
                "action_category": "survival",
                "action": "drink_water",
                "effects": {"thirst_delta": -30},
            },
        ),
        _turn_row(
            4,
            survival={"hunger": 80, "thirst": 92, "fatigue": 50},
            pressure={"hunger": "critical", "thirst": "critical", "fatigue": "high"},
            survival_result={
                "ok": False,
                "action_category": "survival",
                "action": "drink_water",
                "blocked_reason": "no_water_available",
            },
        ),
    ]

    metrics = build_survival_report_metrics(rows)

    assert metrics["format_version"] == "survival_report_metrics_v2"
    assert metrics["summary"]["turns_observed"] == 4
    assert metrics["summary"]["passive_tick_count"] == 2
    assert metrics["summary"]["direct_survival_action_count"] == 1
    assert metrics["summary"]["blocked_survival_action_count"] == 1
    assert metrics["advisory_gates"]["advisory_only"] is True
    assert metrics["tick_counts_by_reason"] == {
        "skipped:direct_survival_action": 1,
        "standard_turn": 1,
        "travel_turn": 1,
    }
    assert metrics["action_counts"] == {"drink_water": 1}
    assert metrics["blocked_action_counts"] == {"drink_water": 1}
    assert metrics["blocked_reason_counts"] == {"no_water_available": 1}
    assert metrics["pressure_counts"]["thirst"] == {
        "low": 2,
        "moderate": 1,
        "high": 0,
        "critical": 1,
    }
    assert metrics["summary"]["max_pressure_value"]["thirst"] == 92
    assert metrics["summary"]["warning_counts"]["blocked_survival_actions"] == 1
    assert metrics["summary"]["warning_counts"]["critical_survival_pressure"] == 1
    assert metrics["timeline"][-1]["blocked_actions"] == [
        {"action": "drink_water", "reason": "no_water_available"}
    ]
    json.dumps(metrics)


def test_bundle_bg_extracts_nested_runtime_shapes_without_duplicates() -> None:
    row = {
        "turn_index": 9,
        "result": {
            "survival_tick_result": {
                "applied": True,
                "reason": "wait_turn",
                "turn_id": "turn:9",
            },
            "resolved_result": {
                "interaction_result": {
                    "survival_result": {
                        "ok": True,
                        "action_category": "survival",
                        "action": "eat_rations",
                    }
                },
                "survival_action_context": {
                    "survival": {"hunger": 20, "thirst": 30, "fatigue": 40},
                },
            },
        },
    }

    metrics = build_survival_report_metrics([row])

    assert metrics["tick_counts_by_reason"] == {"wait_turn": 1}
    assert metrics["action_counts"] == {"eat_rations": 1}
    assert metrics["timeline"][0]["turn"] == 9
    assert metrics["timeline"][0]["needs"] == {"hunger": 20, "thirst": 30, "fatigue": 40}
    assert metrics["pressure_counts"]["fatigue"]["moderate"] == 1


def test_bundle_bg_merge_payload_and_render_html_section() -> None:
    rows = [
        _turn_row(
            1,
            survival={"hunger": 55, "thirst": 75, "fatigue": 10},
            pressure={"hunger": "high", "thirst": "critical", "fatigue": "low"},
            tick_result={"applied": True, "reason": "standard_turn", "turn_id": "turn:1"},
        )
    ]

    merged = merge_survival_report_metrics({"report_sections": {"summary": {}}}, rows)
    html = render_survival_report_html(merged["survival_report_metrics"])

    assert "survival_report_metrics" in merged
    assert merged["report_sections"]["survival"] == merged["survival_report_metrics"]
    assert "Survival Report Metrics" in html
    assert "Passive ticks" in html
    assert "Advisory Survival Gates" in html
    assert "Pressure Distribution" in html
    assert "standard_turn" in html
    assert "thirst" in html
    json.dumps(merged)


def test_bundle_bg_empty_report_is_stable_and_json_safe() -> None:
    metrics = build_survival_report_metrics([])
    html = render_survival_report_html(metrics)

    assert metrics["summary"]["turns_observed"] == 0
    assert metrics["summary"]["passive_tick_count"] == 0
    assert metrics["advisory_gates"]["ok"] is True
    assert metrics["pressure_counts"] == {
        "hunger": {"low": 0, "moderate": 0, "high": 0, "critical": 0},
        "thirst": {"low": 0, "moderate": 0, "high": 0, "critical": 0},
        "fatigue": {"low": 0, "moderate": 0, "high": 0, "critical": 0},
    }
    assert "No survival timeline evidence found" in html
    json.dumps(metrics)
