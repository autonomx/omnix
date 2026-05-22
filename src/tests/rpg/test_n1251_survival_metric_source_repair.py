from __future__ import annotations

from app.rpg.session.survival_metrics import (
    build_survival_metric_source_gate,
    build_survival_metric_source_summary,
    build_survival_pressure_relief_summary,
)
from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
)


def _row_with_full_source(turn: int = 1):
    return {
        "turn_index": turn,
        "result": {
            "turn_contract": {
                "climate_survival": {
                    "tick": turn,
                    "survival": {
                        "hunger": 51,
                        "thirst": 72,
                        "fatigue": 33,
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
                        "thirst_delta": -30,
                        "inventory_consumed": {
                            "consumed": True,
                            "item_id": "waterskin",
                            "name": "Waterskin",
                            "quantity": 1,
                        },
                    },
                },
                "effect_result": {
                    "source": "merged_turn_effect_result",
                    "warnings": ["thirst_high"],
                },
                "survival_action": {
                    "matched": True,
                    "applied": True,
                    "action_kind": "drink_water",
                    "resource_changes": {
                        "inventory_consumed": {
                            "consumed": True,
                            "item_id": "waterskin",
                            "name": "Waterskin",
                            "quantity": 1,
                        },
                    },
                },
                "survival_suggested_actions": [
                    {"type": "survival_relief", "action_kind": "drink_water", "command": "I drink Waterskin"}
                ],
            }
        },
    }


def _row_with_values_but_missing_sources(turn: int = 1):
    return {
        "turn_index": turn,
        "climate_survival": {
            "tick": turn,
            "survival": {
                "hunger": 2,
                "thirst": 3,
                "fatigue": 2,
                "warnings": [],
            },
        },
    }


def _row_with_authoritative_climate_state(turn: int = 1):
    return {
        "turn_index": turn,
        "climate_survival": {
            "format_version": "n1231_climate_survival_state_v1",
            "runtime_enforced": True,
            "source": "deterministic_authoritative_turn_tick",
            "tick": turn,
            "minutes_per_turn": 15,
            "survival": {
                "hunger": 4,
                "thirst": 6,
                "fatigue": 4,
                "warnings": [],
            },
        },
    }


def _compacted_final_transcript_climate_row(turn: int = 1):
    return {
        "turn_index": turn,
        "player": "I wait.",
        "result": {"ok": True, "turn_contract": {}},
        "climate_survival": {
            "tick": turn,
            "survival": {"hunger": 4, "thirst": 6, "fatigue": 4, "warnings": []},
        },
    }


def test_n1251_source_summary_detects_full_nested_turn_contract_evidence() -> None:
    summary = build_survival_metric_source_summary([_row_with_full_source(1)])

    coverage = summary["coverage"]
    assert coverage["row_count"] == 1
    assert coverage["climate_survival_rows"] == 1
    assert coverage["resource_change_rows"] == 1
    assert coverage["climate_tick_source_rows"] == 1
    assert coverage["survival_action_rows"] == 1
    assert coverage["survival_suggestion_rows"] == 1
    assert coverage["relief_applied_rows"] == 1
    assert coverage["warning_rows"] == 1
    assert summary["source_coverage_rate"] == 1.0
    assert build_survival_metric_source_gate(summary)["ok"] is True


def test_n1251_source_gate_flags_value_only_rows_as_advisory_gap() -> None:
    summary = build_survival_metric_source_summary([_row_with_values_but_missing_sources(1)])
    gate = build_survival_metric_source_gate(summary)

    assert summary["coverage"]["climate_survival_rows"] == 1
    assert summary["coverage"]["resource_change_rows"] == 0
    assert summary["coverage"]["climate_tick_source_rows"] == 0
    assert gate["ok"] is False
    assert gate["advisory_only"] is True
    assert "missing_resource_change_rows" in gate["reasons"]
    assert "missing_climate_tick_source_rows" in gate["reasons"]


def test_n1251_authoritative_climate_state_counts_as_tick_source_without_fabricating_deltas() -> None:
    summary = build_survival_metric_source_summary([_row_with_authoritative_climate_state(1)])
    gate = build_survival_metric_source_gate(summary)

    assert summary["coverage"]["row_count"] == 1
    assert summary["coverage"]["climate_survival_rows"] == 1
    assert summary["coverage"]["resource_change_rows"] == 0
    assert summary["coverage"]["climate_tick_source_rows"] == 1
    assert summary["coverage"]["nonzero_delta_rows"] == 0
    assert gate["ok"] is True
    assert gate["reasons"] == []


def test_n1251_repaired_survival_pressure_summary_includes_source_coverage_and_real_metrics() -> None:
    summary = build_survival_pressure_relief_summary([_row_with_full_source(1)])

    assert summary["format_version"] == "n1234_survival_pressure_relief_summary_v2_n1251"
    assert summary["pressure_turn_count"] == 1
    assert summary["survival_warning_count"] == 1
    assert summary["relief_action_count"] == 1
    assert summary["relief_counts_by_kind"]["drink_water"] == 1
    assert summary["inventory_consumed_summary"] == [
        {"item_id": "waterskin", "name": "Waterskin", "quantity": 1}
    ]
    assert summary["source_coverage_summary"]["coverage"]["climate_tick_source_rows"] == 1
    assert summary["source_gate"]["ok"] is True
    assert summary["trend_rows"][0]["source_present"] is True


def test_n1251_authoritative_climate_state_counts_pressure_source_without_relief_or_delta() -> None:
    summary = build_survival_pressure_relief_summary([_row_with_authoritative_climate_state(1)])

    assert summary["pressure_turn_count"] == 1
    assert summary["survival_warning_count"] == 0
    assert summary["relief_action_count"] == 0
    assert summary["net_resource_deltas"] == {
        "hunger_delta": 0,
        "thirst_delta": 0,
        "fatigue_delta": 0,
    }
    assert summary["source_coverage_summary"]["coverage"]["climate_tick_source_rows"] == 1
    assert summary["source_gate"]["ok"] is True
    assert summary["trend_rows"][0]["source_present"] is True


def test_n1251_autoplay_evaluation_summary_attaches_real_vs_synthetic_and_source_gate() -> None:
    result = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[_row_with_full_source(1)],
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={"checked_count": 100, "invalid_count": 0, "provider_json_parse_failed_count": 0, "provider_invalid_count": 0},
        progress_quality_summary={"meaningful_progress_rate": 0.5, "fallback_player_action_rate": 0.0, "no_change_turns": 0},
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert result["real_run_survival_metrics"]["source_gate"]["ok"] is True
    assert "synthetic_survival_balance_simulation" in result
    assert result["survival_metric_source_gate"]["ok"] is True
    assert result["artifact_level_summaries"]["survival-metric-source-summary.json"]["coverage"]["row_count"] == 1
    assert result["artifact_level_summaries"]["survival-metric-source-gate.json"]["ok"] is True
    assert any(section["id"] == "n1251-survival-source" for section in result["report_sections"])


def test_n1251_source_repair_wrapper_projects_compacted_final_rows_before_summary() -> None:
    result = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[_compacted_final_transcript_climate_row(1)],
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={"checked_count": 100, "invalid_count": 0, "provider_json_parse_failed_count": 0, "provider_invalid_count": 0},
        progress_quality_summary={"meaningful_progress_rate": 0.5, "fallback_player_action_rate": 0.0, "no_change_turns": 0},
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert result["survival_metric_source_gate"]["ok"] is True
    assert result["survival_metric_source_gate"]["reasons"] == []
    assert result["survival_metric_source_summary"]["coverage"]["climate_tick_source_rows"] == 1
    assert result["survival_metric_source_summary"]["coverage"]["nonzero_delta_rows"] == 0
    assert result["real_run_survival_metrics"]["pressure_turn_count"] == 1
    assert result["real_run_survival_metrics"]["relief_action_count"] == 0


def test_n1251_readiness_summary_exposes_advisory_survival_metric_source_gate() -> None:
    readiness = _build_100_turn_readiness_summary(
        summary={"scenario_progression_arc_summary": {"graph_count": 9}},
        transcript=[_row_with_values_but_missing_sources(1)],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )

    assert readiness["gates"]["survival_metric_source_ok"] is False
    assert "survival_metric_source_ok" in readiness["advisory_gates"]
    assert readiness["survival_metric_source_gate"]["advisory_only"] is True
