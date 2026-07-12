from __future__ import annotations

from app.rpg.presentation.visible_response import build_visible_response, visible_response_text


def test_canonical_visible_response_preserves_narration_and_npc_line() -> None:
    result = {
        "final_narration": "Bran rests the polishing rag on the counter.",
        "npc": {
            "id": "npc:bran",
            "speaker": "Bran",
            "line": "Steady enough, though the old road has been quiet.",
        },
    }

    visible = build_visible_response(result)

    assert visible["format_version"] == "rpg_visible_response_v1"
    assert visible["narration"] == "Bran rests the polishing rag on the counter."
    assert visible["messages"] == [
        {
            "kind": "npc_dialogue",
            "speaker_id": "npc:bran",
            "speaker": "Bran",
            "text": "Steady enough, though the old road has been quiet.",
        }
    ]
    assert visible["plain_text"] == (
        "Bran rests the polishing rag on the counter.\n\n"
        'Bran: "Steady enough, though the old road has been quiet."'
    )


def test_canonical_visible_response_reads_first_call_nested_contract() -> None:
    result = {
        "first_call_visible_response": {
            "visible_response": {
                "narration": "Bran glances toward the window.",
                "npc": {"speaker": "Bran", "line": "Quieter than it should be."},
            }
        }
    }

    assert visible_response_text(result) == (
        "Bran glances toward the window.\n\n"
        'Bran: "Quieter than it should be."'
    )


def test_canonical_visible_response_deduplicates_narration_equal_to_dialogue() -> None:
    result = {
        "narration": "Steady enough.",
        "npc": {"speaker": "Bran", "line": "Steady enough."},
    }

    assert visible_response_text(result) == 'Bran: "Steady enough."'


def test_canonical_visible_response_ignores_non_npc_speaker_aliases() -> None:
    result = {
        "narration": "The room settles into an uneasy quiet.",
        "npc": {"speaker": "Omnix", "line": "System text must not become NPC dialogue."},
    }

    visible = build_visible_response(result)
    assert visible["messages"] == []
    assert visible["plain_text"] == "The room settles into an uneasy quiet."


def test_canonical_visible_response_extracts_speech_from_attributed_npc_prose() -> None:
    visible = build_visible_response(
        {
            "narration": "Bran reacts to the question.",
            "npc": {
                "speaker": "Bran",
                "line": (
                    'Bran watches you over the rim of a cup. "Ask plainly. '
                    'Are you looking for the traveler or the road?"'
                ),
            },
        }
    )

    assert visible["messages"][0]["text"] == (
        "Ask plainly. Are you looking for the traveler or the road?"
    )
    assert visible["plain_text"] == (
        "Bran reacts to the question.\n\n"
        'Bran: "Ask plainly. Are you looking for the traveler or the road?"'
    )


def test_canonical_visible_response_rejects_npc_claim_not_grounded_in_quest_clue() -> None:
    clue = "A frightened traveler reported strange lights and armed men near the old mill road."
    visible = build_visible_response(
        {
            "narration": "Bran shares a concrete lead.",
            "npc": {
                "speaker": "npc:Bran",
                "line": "Northern patrols are moving toward the old quarry this week.",
            },
            "quest_transition": {
                "reason": "quest_evidence_already_applied",
                "evidence": {"actor_ref": "npc:Bran", "clue_summary": clue},
            },
        }
    )

    assert visible["messages"] == [
        {
            "kind": "npc_dialogue",
            "speaker_id": None,
            "speaker": "Bran",
            "text": clue,
        }
    ]
    assert "old quarry" not in visible["plain_text"]


def test_canonical_visible_response_keeps_provider_paraphrase_grounded_in_clue() -> None:
    visible = build_visible_response(
        {
            "npc": {
                "speaker": "npc:Bran",
                "line": "The traveler saw strange lights and armed men by the old mill road.",
            },
            "quest_transition": {
                "evidence": {
                    "actor_ref": "npc:Bran",
                    "clue_summary": (
                        "A frightened traveler reported strange lights and armed men near the old mill road."
                    ),
                },
            },
        }
    )

    assert visible["messages"][0]["speaker"] == "Bran"
    assert visible["messages"][0]["text"] == (
        "The traveler saw strange lights and armed men by the old mill road."
    )


def test_canonical_visible_response_rejects_evasive_question_that_only_echoes_clue_terms() -> None:
    clue = "A frightened traveler reported strange lights and armed men near the old mill road."
    visible = build_visible_response(
        {
            "npc": {
                "speaker": "Bran",
                "line": "Are you asking about the frightened traveler or the road?",
            },
            "quest_transition": {
                "evidence": {"actor_ref": "npc:Bran", "clue_summary": clue},
            },
        }
    )

    assert visible["messages"][0]["text"] == clue
