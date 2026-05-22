from __future__ import annotations

from app.rpg.session.survival_metrics import build_survival_metric_source_summary
from app.rpg.session.survival_transcript import (
    persist_survival_evidence_into_transcript_row,
    persist_survival_evidence_into_transcript_rows,
)
from tests.rpg.autoplay_llm_campaign import (
    _build_100_turn_evaluation_summary,
    _build_100_turn_readiness_summary,
)


def _compact_row(turn: int = 1):
    return {
        "turn_index": turn,
        "player": "I wait.",
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


def _compacted_contract_climate_row(turn: int = 1):
    return {
        "turn_index": turn,
        "player": "I wait.",
        "result": {
            "turn_contract": {
                "climate_survival": {
                    "tick": turn,
                    "survival": {
                        "hunger": 4,
                        "thirst": 6,
                        "fatigue": 4,
                        "warnings": [],
                    },
                },
            }
        },
    }


def _value_only_row(turn: int = 1):
    return {
        "turn_index": turn,
        "climate_survival": {
            "tick": turn,
            "survival": {"hunger": 2, "thirst": 3, "fatigue": 2, "warnings": []},
        },
    }


def test_n1252_projects_nested_turn_contract_survival_evidence_to_final_row_fields() -> None:
    projected = persist_survival_evidence_into_transcript_row(_compact_row(7))

    assert projected["turn_contract"]["resource_changes"]["climate_survival"]["source"] == "n1231_climate_survival_tick"
    assert projected["resource_changes"]["climate_survival"]["source"] == "n1231_climate_survival_tick"
    assert projected["survival_action"]["action_kind"] == "drink_water"
    assert projected["survival_suggested_actions"][0]["action_kind"] == "drink_water"
    assert projected["hunger_delta"] == 1
    assert projected["thirst_delta"] == -28
    assert projected["fatigue_delta"] == 1
    assert projected["survival_evidence_projection"]["climate_tick_source_present"] is True


def test_n1252_restores_source_for_compacted_nested_turn_contract_climate_rows() -> None:
    projected = persist_survival_evidence_into_transcript_row(_compacted_contract_climate_row(9))

    climate = projected["turn_contract"]["climate_survival"]
    assert climate["format_version"] == "n1231_climate_survival_state_v1"
    assert climate["runtime_enforced"] is True
    assert climate["source"] == "n1252_projected_turn_contract_climate_survival"
    assert projected["climate_survival"]["source"] == "n1252_projected_turn_contract_climate_survival"
    assert projected["survival_evidence_projection"]["climate_survival_preserved"] is True
    assert projected["survival_evidence_projection"]["climate_source_restored"] is True
    assert projected["survival_evidence_projection"]["resource_changes_preserved"] is False
    assert projected["survival_evidence_projection"]["climate_tick_source_present"] is True
    assert "hunger_delta" not in projected
    assert "thirst_delta" not in projected
    assert "fatigue_delta" not in projected


def test_n1252_projection_does_not_fabricate_source_for_value_only_rows() -> None:
    projected = persist_survival_evidence_into_transcript_row(_value_only_row(1))

    assert projected["survival_evidence_projection"]["climate_survival_preserved"] is True
    assert projected["survival_evidence_projection"]["climate_source_restored"] is False
    assert projected["survival_evidence_projection"]["resource_changes_preserved"] is False
    assert projected["survival_evidence_projection"]["climate_tick_source_present"] is False


def test_n1252_projected_rows_are_visible_to_n1251_source_summary() -> None:
    rows = persist_survival_evidence_into_transcript_rows([_compact_row(1), _value_only_row(2)])
    summary = build_survival_metric_source_summary(rows)

    assert summary["coverage"]["row_count"] == 2
    assert summary["coverage"]["climate_survival_rows"] == 2
    assert summary["coverage"]["resource_change_rows"] == 1
    assert summary["coverage"]["climate_tick_source_rows"] == 1
    assert summary["coverage"]["survival_action_rows"] == 1
    assert summary["coverage"]["survival_suggestion_rows"] == 1


def test_n1252_compacted_contract_climate_rows_are_visible_to_n1251_source_summary() -> None:
    rows = persist_survival_evidence_into_transcript_rows([
        _compacted_contract_climate_row(1),
        _value_only_row(2),
    ])
    summary = build_survival_metric_source_summary(rows)

    assert summary["coverage"]["row_count"] == 2
    assert summary["coverage"]["climate_survival_rows"] == 2
    assert summary["coverage"]["resource_change_rows"] == 0
    assert summary["coverage"]["climate_tick_source_rows"] == 1
    assert summary["coverage"]["survival_action_rows"] == 0
    assert summary["coverage"]["survival_suggestion_rows"] == 0
    assert summary["coverage"]["nonzero_delta_rows"] == 0


def test_n1252_evaluation_summary_projects_transcript_before_survival_source_gate() -> None:
    summary = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[_compact_row(1)],
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={"checked_count": 100, "invalid_count": 0, "provider_json_parse_failed_count": 0, "provider_invalid_count": 0},
        progress_quality_summary={"meaningful_progress_rate": 0.5, "fallback_player_action_rate": 0.0, "no_change_turns": 0},
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert summary["survival_metric_source_gate"]["ok"] is True
    assert summary["survival_metric_source_summary"]["coverage"]["climate_tick_source_rows"] == 1
    assert summary["real_run_survival_metrics"]["pressure_turn_count"] == 1
    assert summary["real_run_survival_metrics"]["relief_action_count"] == 1
    assert summary["artifact_level_summaries"]["survival-metric-source-gate.json"]["ok"] is True


def test_n1252_evaluation_summary_accepts_compacted_turn_contract_climate_source() -> None:
    summary = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[_compacted_contract_climate_row(1)],
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={"checked_count": 100, "invalid_count": 0, "provider_json_parse_failed_count": 0, "provider_invalid_count": 0},
        progress_quality_summary={"meaningful_progress_rate": 0.5, "fallback_player_action_rate": 0.0, "no_change_turns": 0},
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    assert summary["survival_metric_source_gate"]["ok"] is True
    assert summary["survival_metric_source_gate"]["reasons"] == []
    assert summary["survival_metric_source_summary"]["coverage"]["climate_tick_source_rows"] == 1
    assert summary["survival_metric_source_summary"]["coverage"]["nonzero_delta_rows"] == 0
    assert summary["real_run_survival_metrics"]["pressure_turn_count"] == 1
    assert summary["real_run_survival_metrics"]["relief_action_count"] == 0
    assert summary["artifact_level_summaries"]["survival-metric-source-gate.json"]["ok"] is True


def test_n1252_readiness_summary_keeps_metric_source_gate_advisory_when_source_missing() -> None:
    readiness = _build_100_turn_readiness_summary(
        summary={"scenario_progression_arc_summary": {"graph_count": 9}},
        transcript=[_value_only_row(1)],
        requested_turns=100,
        turns_executed=100,
        runtime_errors=[],
        warnings=[],
    )

    assert readiness["gates"]["survival_metric_source_ok"] is False
    assert "survival_metric_source_ok" in readiness["advisory_gates"]
    assert readiness["survival_metric_source_gate"]["advisory_only"] is True
