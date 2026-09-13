from __future__ import annotations


def test_provider_choices_content_wins_over_empty_tool_calls() -> None:
    from app.rpg.session.visible_response_contract import extract_provider_message_content, is_invalid_visible_value

    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "{\"ok\": true, \"npc\": {\"speaker\": \"Bran\", \"line\": \"Rumors? Ask plain what kind you want.\"}}",
                    "tool_calls": [],
                }
            }
        ],
        "usage": {"prompt_tokens": 12},
        "stats": {},
    }

    assert extract_provider_message_content(payload).startswith('{"ok": true')
    assert is_invalid_visible_value(payload["choices"][0]["message"]["tool_calls"])


def test_raw_provider_metadata_is_invalid_visible_text() -> None:
    from app.rpg.session.visible_response_contract import is_invalid_visible_value, visible_response_text

    assert is_invalid_visible_value([])
    assert is_invalid_visible_value({"tool_calls": []})
    assert is_invalid_visible_value("[]")
    assert is_invalid_visible_value("[object Object]")
    assert visible_response_text({"tool_calls": []}) == ""


def test_visible_turn_record_uses_canonical_npc_line() -> None:
    from app.rpg.session.visible_response_contract import build_visible_turn_record

    record = build_visible_turn_record(
        {
            "narration": "Bran answers carefully.",
            "visible_response": {
                "narration": "Bran answers carefully.",
                "npc": {"speaker": "Bran", "line": "Rumors come in with road dust."},
            },
            "tool_calls": [],
        },
        player_input="I ask Bran, any rumors lately?",
    )

    assert record["visible_text"] == "Bran: Rumors come in with road dust."
    assert record["visible_text_valid"] is True
    assert record["rejected_visible_candidates"] == [
        {"source": "top_level_tool_calls", "reason": "invalid_visible_value", "value_type": "list"}
    ]
