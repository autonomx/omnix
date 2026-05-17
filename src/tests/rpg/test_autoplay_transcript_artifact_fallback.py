from tests.rpg.autoplay_llm_campaign import (
    _normalize_transcript_rows,
    _transcript_rows_are_all_null,
)


def test_transcript_rows_are_all_null_detects_broken_artifact_rows():
    assert _transcript_rows_are_all_null([None, None]) is True
    assert _transcript_rows_are_all_null([{"turn_index": 1}, None]) is False


def test_normalize_transcript_rows_turns_nulls_into_dict_rows():
    rows = _normalize_transcript_rows([None, {}])

    assert rows[0]["turn_index"] == 1
    assert rows[0]["empty_transcript_row_repaired"] is True
    assert rows[1]["turn_index"] == 2
    assert rows[1]["empty_transcript_row_repaired"] is True
