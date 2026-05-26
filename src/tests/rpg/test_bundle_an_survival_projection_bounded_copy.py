from __future__ import annotations

import pytest

from app.rpg.session.survival_transcript_resource_backing import (
    RESOURCE_BACKED_CLIMATE_SOURCE,
    restore_resource_backed_climate_source,
    restore_resource_backed_climate_sources,
)


def _large_row_without_survival_payload() -> dict:
    return {
        "turn_index": 1,
        "player_action": "travel to the old road",
        "huge_nested_payload": [
            {"index": index, "text": "x" * 256, "nested": [{"value": index}]}
            for index in range(200)
        ],
    }


def _resource_backed_survival_row() -> dict:
    return {
        "turn_index": 7,
        "player_action": "rest and drink water",
        "climate_survival": {
            "survival": {"thirst": 2, "hunger": 1, "fatigue": 3},
        },
        "resource_changes": {
            "water": -1,
            "rations": 0,
        },
        "turn_contract": {
            "action": "rest",
            "resource_changes": {"water": -1},
        },
        "huge_nested_payload": [
            {"index": index, "text": "x" * 256, "nested": [{"value": index}]}
            for index in range(200)
        ],
    }


def test_survival_projection_returns_unchanged_large_rows_without_deepcopy():
    row = _large_row_without_survival_payload()

    projected = restore_resource_backed_climate_source(row)

    assert projected is row
    assert projected["huge_nested_payload"] is row["huge_nested_payload"]
    assert "survival_evidence_projection" not in projected


def test_survival_projection_restores_source_without_copying_large_payload():
    row = _resource_backed_survival_row()

    projected = restore_resource_backed_climate_source(row)

    assert projected is not row
    assert projected["huge_nested_payload"] is row["huge_nested_payload"]
    assert projected["climate_survival"] is not row["climate_survival"]
    assert projected["turn_contract"] is not row["turn_contract"]
    assert projected["climate_survival"]["source"] == RESOURCE_BACKED_CLIMATE_SOURCE
    assert projected["turn_contract"]["climate_survival"]["source"] == RESOURCE_BACKED_CLIMATE_SOURCE
    assert projected["survival_evidence_projection"]["resource_backed_climate_source_restored"] is True


def test_survival_projection_batch_preserves_length_and_bounds_copying():
    rows = [_large_row_without_survival_payload(), _resource_backed_survival_row()]

    projected = restore_resource_backed_climate_sources(rows)

    assert len(projected) == 2
    assert projected[0] is rows[0]
    assert projected[1] is not rows[1]
    assert projected[1]["huge_nested_payload"] is rows[1]["huge_nested_payload"]


def test_survival_projection_avoids_deepcopy_for_unchanged_rows_when_deepcopy_is_blocked(monkeypatch):
    import app.rpg.session.survival_transcript_resource_backing as backing

    def explode(_value):
        raise MemoryError("deepcopy should not run for unchanged rows")

    monkeypatch.setattr(backing, "deepcopy", explode)
    row = _large_row_without_survival_payload()

    projected = backing.restore_resource_backed_climate_source(row)

    assert projected is row
