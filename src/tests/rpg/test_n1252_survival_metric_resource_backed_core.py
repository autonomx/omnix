from __future__ import annotations

from app.rpg.session.survival_metrics import (
    build_survival_metric_source_gate,
    build_survival_metric_source_summary,
    build_survival_pressure_relief_summary,
    has_climate_tick_source,
)


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


def test_n1252_core_metric_counts_climate_plus_resource_changes_as_source_backed() -> None:
    assert has_climate_tick_source(_resource_backed_row()) is True
    assert has_climate_tick_source(_value_only_row()) is False


def test_n1252_core_metric_source_summary_counts_resource_backed_rows_only() -> None:
    summary = build_survival_metric_source_summary([
        _resource_backed_row(1),
        _resource_backed_row(2),
        _value_only_row(3),
    ])
    gate = build_survival_metric_source_gate(summary)

    assert summary["coverage"]["row_count"] == 3
    assert summary["coverage"]["climate_survival_rows"] == 3
    assert summary["coverage"]["resource_change_rows"] == 2
    assert summary["coverage"]["climate_tick_source_rows"] == 2
    assert gate["ok"] is True


def test_n1252_core_pressure_summary_uses_resource_backed_source_without_fake_deltas() -> None:
    summary = build_survival_pressure_relief_summary([
        _resource_backed_row(1),
        _value_only_row(2),
    ])

    assert summary["pressure_turn_count"] == 1
    assert summary["source_coverage_summary"]["coverage"]["climate_tick_source_rows"] == 1
    assert summary["source_gate"]["ok"] is True
    assert summary["net_resource_deltas"] == {
        "hunger_delta": 0,
        "thirst_delta": 0,
        "fatigue_delta": 0,
    }
    assert summary["relief_action_count"] == 0
