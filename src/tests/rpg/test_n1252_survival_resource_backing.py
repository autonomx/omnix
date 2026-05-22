from __future__ import annotations

from app.rpg.session.survival_metrics import build_survival_metric_source_summary
from app.rpg.session.survival_transcript_resource_backing import (
    RESOURCE_BACKED_CLIMATE_SOURCE,
    restore_resource_backed_climate_source,
    restore_resource_backed_climate_sources,
)
from tests.rpg.autoplay_llm_campaign import _build_100_turn_evaluation_summary


def _resource_backed_row(turn: int = 1):
    return {
        "turn_index": turn,
        "climate_survival": {
            "tick": turn,
            "survival": {"hunger": 4, "thirst": 6, "fatigue": 4, "warnings": []},
        },
        "resource_changes": {
            "source": "merged_turn_resource_changes",
            "gold_delta": 0,
        },
    }


def _value_only_row(turn: int = 1):
    return {
        "turn_index": turn,
        "climate_survival": {
            "tick": turn,
            "survival": {"hunger": 4, "thirst": 6, "fatigue": 4, "warnings": []},
        },
    }


def test_n1252_resource_backing_restores_source_only_when_resource_changes_exist() -> None:
    restored = restore_resource_backed_climate_source(_resource_backed_row(3))
    value_only = restore_resource_backed_climate_source(_value_only_row(4))

    assert restored["climate_survival"]["source"] == RESOURCE_BACKED_CLIMATE_SOURCE
    assert restored["climate_survival"]["format_version"] == "n1231_climate_survival_state_v1"
    assert restored["survival_evidence_projection"]["resource_backed_climate_source_restored"] is True
    assert "source" not in value_only["climate_survival"]
    assert "survival_evidence_projection" not in value_only


def test_n1252_resource_backed_rows_count_as_source_evidence() -> None:
    rows = restore_resource_backed_climate_sources([_resource_backed_row(1), _value_only_row(2)])
    summary = build_survival_metric_source_summary(rows)

    assert summary["coverage"]["row_count"] == 2
    assert summary["coverage"]["climate_survival_rows"] == 2
    assert summary["coverage"]["resource_change_rows"] == 1
    assert summary["coverage"]["climate_tick_source_rows"] == 1


def test_n1252_source_repair_wrapper_applies_resource_backed_restoration() -> None:
    result = _build_100_turn_evaluation_summary(
        turns_executed=100,
        requested_turns=100,
        runtime_errors=[],
        warnings=[],
        transcript=[_resource_backed_row(1), _value_only_row(2)],
        performance_summary={"avg_turn_seconds": 1.0, "p95_turn_seconds": 2.0},
        narration_grounding_summary={"checked_count": 100, "invalid_count": 0, "provider_json_parse_failed_count": 0, "provider_invalid_count": 0},
        progress_quality_summary={"meaningful_progress_rate": 0.5, "fallback_player_action_rate": 0.0, "no_change_turns": 0},
        checkpoint_summary={"failure_count": 0},
        loop_detection_summary={"repeated_action_window_count": 0, "loop_warning_count": 0},
    )

    coverage = result["survival_metric_source_summary"]["coverage"]
    assert result["survival_metric_source_gate"]["ok"] is True
    assert coverage["climate_survival_rows"] == 2
    assert coverage["resource_change_rows"] == 1
    assert coverage["climate_tick_source_rows"] == 1
    assert result["real_run_survival_metrics"]["pressure_turn_count"] == 1
