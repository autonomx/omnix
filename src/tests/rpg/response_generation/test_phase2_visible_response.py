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
