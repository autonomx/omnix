from tests.rpg.autoplay_llm_campaign import (
    _assert_transcript_artifact_rows_not_null,
    _normalize_transcript_rows,
)


def test_normalize_transcript_rows_repairs_null_rows():
    transcript = [
        {"turn_index": 1, "player_action": "I wait."},
        None,
        {},
    ]

    normalized = _normalize_transcript_rows(transcript)

    assert len(normalized) == 3
    assert normalized[0]["turn_index"] == 1
    assert normalized[1]["turn_index"] == 2
    assert normalized[1]["empty_transcript_row_repaired"] is True
    assert normalized[2]["turn_index"] == 3
    assert normalized[2]["empty_transcript_row_repaired"] is True

    _assert_transcript_artifact_rows_not_null(normalized)


def test_assert_transcript_artifact_rows_rejects_raw_null_rows():
    try:
        _assert_transcript_artifact_rows_not_null([{"turn_index": 1}, None])
    except RuntimeError as exc:
        assert "transcript_artifact_rows_null" in str(exc)
    else:
        raise AssertionError("expected null transcript row failure")
