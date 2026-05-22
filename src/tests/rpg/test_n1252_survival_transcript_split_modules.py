from __future__ import annotations

from app.rpg.session import survival_transcript as legacy
from app.rpg.session.survival_transcript_projector import (
    persist_survival_evidence_into_transcript_row,
)
from app.rpg.session.survival_transcript_sources import (
    COMPACTED_FINAL_ROW_CLIMATE_SOURCE,
    is_final_transcript_context,
    projection_was_value_only,
)


def _final_row(turn: int = 1):
    return {
        "turn_index": turn,
        "player": "I wait.",
        "result": {"ok": True},
        "climate_survival": {
            "tick": turn,
            "survival": {"hunger": 4, "thirst": 6, "fatigue": 4, "warnings": []},
        },
    }


def _value_only(turn: int = 1):
    return {
        "turn_index": turn,
        "climate_survival": {
            "tick": turn,
            "survival": {"hunger": 4, "thirst": 6, "fatigue": 4, "warnings": []},
        },
    }


def test_n1252_split_projector_restores_source_for_final_transcript_context() -> None:
    projected = persist_survival_evidence_into_transcript_row(_final_row())

    assert projected["survival_evidence_projection"]["climate_source_restored"] is True
    assert projected["survival_evidence_projection"]["restored_climate_source"] == COMPACTED_FINAL_ROW_CLIMATE_SOURCE
    assert projected["survival_evidence_projection"]["climate_tick_source_present"] is True


def test_n1252_split_projector_keeps_value_only_rows_source_less_and_idempotent() -> None:
    once = persist_survival_evidence_into_transcript_row(_value_only())
    twice = persist_survival_evidence_into_transcript_row(once)

    assert once["survival_evidence_projection"]["climate_source_restored"] is False
    assert once["survival_evidence_projection"]["climate_tick_source_present"] is False
    assert projection_was_value_only(once) is True
    assert twice["survival_evidence_projection"]["climate_source_restored"] is False
    assert twice["survival_evidence_projection"]["climate_tick_source_present"] is False


def test_n1252_legacy_survival_transcript_facade_reexports_projector() -> None:
    projected = legacy.persist_survival_evidence_into_transcript_row(_final_row())

    assert legacy.COMPACTED_FINAL_ROW_CLIMATE_SOURCE == COMPACTED_FINAL_ROW_CLIMATE_SOURCE
    assert legacy.is_final_transcript_context(_final_row()) is True
    assert is_final_transcript_context(_value_only()) is False
    assert projected["survival_evidence_projection"]["climate_tick_source_present"] is True
