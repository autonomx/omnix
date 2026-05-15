from tests.rpg.autoplay_llm_campaign import (
    _apply_turn_action_consistency_gate,
    _build_turn_action_consistency_summary,
    _normalize_turn_action_consistency_transcript_rows,
)


def test_turn_action_consistency_repairs_progress_quality_action():
    row = {
        "turn_index": 4,
        "player_action": "I buy two rations from Bran.",
        "progress_quality": {
            "player_action": "I turn to Mira and ask what she saw near the side door.",
            "quality": "no_change",
        },
    }

    repaired = _apply_turn_action_consistency_gate(
        row,
        canonical_turn_action="I buy two rations from Bran.",
    )

    assert repaired["player_action"] == "I buy two rations from Bran."
    assert repaired["progress_quality"]["player_action"] == "I buy two rations from Bran."
    assert repaired["turn_action_consistency"]["ok"] is True


def test_turn_action_consistency_summary_counts_repaired_rows():
    row = {
        "turn_index": 4,
        "canonical_turn_action": "I buy two rations from Bran.",
        "player_action": "I buy two rations from Bran.",
        "progress_quality": {
            "player_action": "I turn to Mira and ask what she saw near the side door.",
        },
    }

    normalized = _normalize_turn_action_consistency_transcript_rows([row])
    summary = _build_turn_action_consistency_summary(transcript=normalized)

    assert summary["checked_count"] == 1
    assert summary["repaired_count"] == 1
    assert summary["unrepaired_count"] == 0
    assert summary["ok"] is True


def test_canonical_action_prefers_visible_player_action_over_stale_proposed_action():
    row = {
        "turn_index": 4,
        "player_action": "I buy two rations from Bran.",
        "progress_quality": {
            "player_action": "I turn to Mira and ask what she saw near the side door.",
        },
    }

    repaired = _apply_turn_action_consistency_gate(
        row,
        canonical_turn_action="I turn to Mira and ask what she saw near the side door.",
    )

    assert repaired["canonical_turn_action"] == "I buy two rations from Bran."
    assert repaired["player_action"] == "I buy two rations from Bran."
    assert repaired["progress_quality"]["player_action"] == "I buy two rations from Bran."
    assert repaired["turn_action_consistency"]["ok"] is True


def test_normalization_does_not_overwrite_player_action_with_stale_canonical():
    row = {
        "turn_index": 4,
        "canonical_turn_action": "I turn to Mira and ask what she saw near the side door.",
        "player_action": "I buy two rations from Bran.",
        "progress_quality": {
            "player_action": "I turn to Mira and ask what she saw near the side door.",
        },
    }

    normalized = _normalize_turn_action_consistency_transcript_rows([row])[0]

    assert normalized["canonical_turn_action"] == "I buy two rations from Bran."
    assert normalized["player_action"] == "I buy two rations from Bran."
    assert normalized["progress_quality"]["player_action"] == "I buy two rations from Bran."
    assert normalized["turn_action_consistency"]["ok"] is True


def test_source_inversion_is_not_allowed_when_original_action_exists():
    row = {
        "turn_index": 4,
        "original_player_action": "I buy two rations from Bran.",
        "visible_player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I turn to Mira and ask what she saw near the side door.",
        "player_action": "I buy two rations from Bran.",
        "progress_quality": {
            "player_action": "I turn to Mira and ask what she saw near the side door.",
        },
    }

    repaired = _apply_turn_action_consistency_gate(
        row,
        canonical_turn_action="I turn to Mira and ask what she saw near the side door.",
    )

    assert repaired["canonical_turn_action"] == "I buy two rations from Bran."
    assert repaired["player_action"] == "I buy two rations from Bran."
    assert repaired["progress_quality"]["player_action"] == "I buy two rations from Bran."
    assert repaired["turn_action_source_check"]["ok"] is True