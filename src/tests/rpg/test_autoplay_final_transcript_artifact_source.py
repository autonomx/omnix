from tests.rpg.autoplay_llm_campaign import (
    _build_final_transcript_artifact_rows,
    _build_transcript_artifact_quality_summary,
)


def test_final_transcript_prefers_in_memory_rows_over_null_artifact_rows():
    rows = _build_final_transcript_artifact_rows(
        transcript=[
            {
                "turn_index": 1,
                "player_action": "I buy two rations from Bran.",
                "canonical_turn_action": "I buy two rations from Bran.",
            }
        ],
        transcript_artifacts={"transcript": [None]},
        summary={"turns_executed": 1},
        session_id="s1",
    )

    assert len(rows) == 1
    assert rows[0]["player_action"] == "I buy two rations from Bran."
    assert rows[0]["transcript_artifact_source"] == "in_memory_transcript"
    assert rows[0]["turn_presentation_identity"]


def test_final_transcript_reconstructs_when_all_sources_are_null():
    rows = _build_final_transcript_artifact_rows(
        transcript=[None],
        transcript_artifacts={"transcript": [None]},
        summary={"turns_executed": 2},
        session_id="s1",
    )

    assert len(rows) == 2
    assert rows[0]["transcript_source"] == "reconstructed_minimal_from_summary"
    assert rows[0]["transcript_artifact_source"] == "reconstructed_minimal_from_summary"


def test_transcript_quality_summary_counts_sources_and_identity():
    rows = _build_final_transcript_artifact_rows(
        transcript=[
            {
                "turn_index": 1,
                "player_action": "I wait.",
                "canonical_turn_action": "I wait.",
            }
        ],
        transcript_artifacts={},
        summary={"turns_executed": 1},
        session_id="s1",
    )

    quality = _build_transcript_artifact_quality_summary(rows)

    assert quality["ok"] is True
    assert quality["row_count"] == 1
    assert quality["null_row_count"] == 0
    assert quality["empty_row_count"] == 0
    assert quality["has_full_rows"] is True
    assert quality["rows_with_turn_identity"] == 1
    assert quality["by_source"]["in_memory_transcript"] == 1
