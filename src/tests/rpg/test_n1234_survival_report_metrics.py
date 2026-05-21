from __future__ import annotations

from tests.rpg.autoplay_llm_campaign import (
    _attach_survival_report_metrics,
    _build_100_turn_evaluation_summary,
    _build_survival_pressure_relief_summary,
    _render_survival_pressure_relief_report_section,
)


def _pressure_row(turn: int, *, hunger: int, thirst: int, fatigue: int):
    return {
        "turn_index": turn,
        "turn_contract": {
            "climate_survival": {
                "tick": turn,
                "survival": {
                    "hunger": hunger,
                    "thirst": thirst,
                    "fatigue": fatigue,
                    "warnings": ["hunger_high"] if hunger >= 70 else [],
                },
            },
            "resource_changes": {
                "source": "n1231_climate_survival_tick",
                "hunger_delta": 1,
                "thirst_delta": 2,
                "fatigue_delta": 1,
            },
            "effect_result": {
                "source": "n1231_climate_survival_tick",
                "warnings": ["hunger_high"] if hunger >= 70 else [],
            },
        },
    }


def _eat_row(turn: int):
    return {
        "turn_index": turn,
        "turn_contract": {
            "climate_survival": {
                "tick": turn,
                "survival": {
                    "hunger": 41,
                    "thirst": 22,
                    "fatigue": 11,
                    "warnings": [],
                },
            },
            "resource_changes": {
                "source": "merged_turn_resource_changes",
                "climate_survival": {
                    "source": "n1231_climate_survival_tick",
                    "hunger_delta": 1,
                    "thirst_delta": 2,
                    "fatigue_delta": 1,
                },
                "survival_action": {
                    "source": "n1232_survival_action_resolution",
                    "action_kind": "eat_food",
                    "hunger_delta": -30,
                    "thirst_delta": 0,
                    "fatigue_delta": 0,
                    "inventory_consumed": {
                        "consumed": True,
                        "item_id": "ration",
                        "name": "Trail ration",
                        "quantity": 1,
                    },
                },
            },
            "survival_action": {
                "matched": True,
                "applied": True,
                "action_kind": "eat_food",
                "resource_changes": {
                    "inventory_consumed": {
                        "consumed": True,
                        "item_id": "ration",
                        "name": "Trail ration",
                        "quantity": 1,
                    },
                },
            },
        },
    }


def _blocked_drink_row(turn: int):
    return {
        "turn_index": turn,
        "turn_contract": {
            "climate_survival": {
                "tick": turn,
                "survival": {
                    "hunger": 40,
                    "thirst": 80,
                    "fatigue": 20,
                    "warnings": ["thirst_high"],
                },
            },
            "resource_changes": {
                "source": "merged_turn_resource_changes",
                "climate_survival": {
                    "source": "n1231_climate_survival_tick",
                    "hunger_delta": 1,
                    "thirst_delta": 2,
                    "fatigue_delta": 1,
                },
                "survival_action": {
                    "source": "n1232_survival_action_resolution",
                    "action_kind": "drink_water",
                    "thirst_delta": 0,
                    "blocked": True,
                    "blocked_reason": "no_drink_item",
                },
            },
            "effect_result": {"warnings": ["thirst_high"]},
            "survival_action": {
                "matched": True,
                "applied": False,
                "blocked": True,
                "blocked_reason": "no_drink_item",
                "action_kind": "drink_water",
            },
        },
    }


def _lodging_row(turn: int):
    return {
        "turn_index": turn,
        "turn_contract": {
            "climate_survival": {
                "tick": turn,
                "survival": {
                    "hunger": 30,
                    "thirst": 30,
                    "fatigue": 25,
                    "warnings": [],
                },
            },
            "resource_changes": {
                "source": "merged_turn_resource_changes",
                "climate_survival": {"source": "n1231_climate_survival_tick", "fatigue_delta": 1},
                "survival_action": {
                    "source": "n1232_survival_action_resolution",
                    "action_kind": "buy_lodging",
                    "fatigue_delta": -55,
                    "purchase": {
                        "applied": True,
                        "price": {"gold": 1, "silver": 0, "copper": 0},
                    },
                },
            },
            "survival_action": {
                "matched": True,
                "applied": True,
                "action_kind": "buy_lodging",
                "resource_changes": {
                    "purchase": {
                        "applied": True,
                        "price": {"gold": 1, "silver": 0, "copper": 0},
                    },
                },
            },
        },
    }


def test_n1234_builds_survival_pressure_relief_summary_from_turn_contract_rows() -> None:
    transcript = [
        _pressure_row(1, hunger=71, thirst=20, fatigue=10),
        _eat_row(2),
        _blocked_drink_row(3),
        _lodging_row(4),
    ]

    summary = _build_survival_pressure_relief_summary(transcript)

    assert summary["format_version"] == "n1234_survival_pressure_relief_summary_v1"
    assert summary["turn_count"] == 4
    assert summary["trend_row_count"] == 4
    assert summary["pressure_turn_count"] == 4
    assert summary["survival_warning_count"] >= 2
    assert summary["relief_action_count"] == 2
    assert summary["blocked_relief_count"] == 1
    assert summary["relief_counts_by_kind"]["eat_food"] == 1
    assert summary["relief_counts_by_kind"]["drink_water"] == 1
    assert summary["relief_counts_by_kind"]["buy_lodging"] == 1
    assert summary["blocked_counts_by_reason"]["no_drink_item"] == 1
    assert summary["inventory_consumed_summary"] == [
        {"item_id": "ration", "name": "Trail ration", "quantity": 1}
    ]
    assert summary["service_relief_purchases_summary"] == [
        {
            "service_kind": "lodging",
            "count": 1,
            "blocked_count": 0,
            "total_price": {"gold": 1, "silver": 0, "copper": 0},
        }
    ]
    assert summary["artifact_files"]["summary"] == "survival-pressure-relief-summary.json"
    assert summary["artifact_files"]["trend_rows"] == "survival-pressure-trend-rows.json"


def test_n1234_attaches_artifact_summaries_and_report_section() -> None:
    base = {"ok": True, "report_sections": []}
    attached = _attach_survival_report_metrics(base, [_eat_row(1)])

    assert attached["ok"] is True
    assert "survival_pressure_relief_summary" in attached
    assert "survival_pressure_trend_rows" in attached
    assert "survival-pressure-relief-summary.json" in attached["artifact_level_summaries"]
    assert "survival-pressure-trend-rows.json" in attached["artifact_level_summaries"]
    section = attached["report_sections"][-1]
    assert section["id"] == "n1234-survival-pressure"
    assert "N123.4 Survival Pressure vs Player Response" in section["html"]
    assert "Trail ration" in section["html"]


def test_n1234_html_report_section_contains_metrics_tables() -> None:
    summary = _build_survival_pressure_relief_summary([_eat_row(1), _lodging_row(2)])
    html = _render_survival_pressure_relief_report_section(summary)

    assert "Pressure turns" in html
    assert "Inventory consumed" in html
    assert "Service relief purchases" in html
    assert "Trail ration" in html
    assert "lodging" in html


def test_n1234_100_turn_evaluation_summary_includes_survival_metrics() -> None:
    summary = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[_eat_row(1), _lodging_row(2)],
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={
            "checked_count": 100,
            "invalid_count": 0,
            "provider_json_parse_failed_count": 0,
            "provider_invalid_count": 0,
        },
        progress_quality_summary={
            "meaningful_progress_rate": 0.50,
            "fallback_player_action_rate": 0.0,
            "no_change_turns": 0,
        },
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert summary["ok"] is True
    assert summary["survival_pressure_relief_summary"]["relief_action_count"] == 2
    assert summary["artifact_level_summaries"]["survival-pressure-relief-summary.json"]["turn_count"] == 2
    assert summary["report_sections"][-1]["id"] == "n1234-survival-pressure"
