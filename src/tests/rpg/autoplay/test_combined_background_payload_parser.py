from tests.rpg.autoplay.parallel_pipeline import (
    _combined_payload_has_useful_content,
    _extract_json_object_from_text,
    _extract_nested_combined_payload,
)


def test_extract_nested_combined_payload_accepts_exact_shape():
    parsed = _extract_json_object_from_text(
        """
        {
          "narration": "Bran watches the room settle.",
          "action": "The question lands.",
          "npc": {"speaker": "Bran", "line": "Keep your voice down."},
          "semantic_intent_candidates": [{"intent": "ask"}],
          "future_hook_candidates": [{"summary": "Bran may answer later."}]
        }
        """
    )
    normalized = _extract_nested_combined_payload(parsed)

    assert normalized["narration"] == "Bran watches the room settle."
    assert normalized["npc"]["speaker"] == "Bran"
    assert normalized["semantic_intent_candidates"][0]["intent"] == "ask"
    assert _combined_payload_has_useful_content(normalized) is True


def test_extract_nested_combined_payload_accepts_narration_payload_and_advisory_wrapper():
    parsed = {
        "narration_payload": {
            "narration": "The tavern quiets.",
            "action": "The player observes the room.",
            "npc": {"speaker": "", "line": ""},
        },
        "advisory": {
            "memory_candidates": [
                {"owner": "bran", "summary": "The player watched the exits."}
            ],
            "future_hook_candidates": [
                {"summary": "Someone may notice the player studying the door."}
            ],
        },
    }

    normalized = _extract_nested_combined_payload(parsed)

    assert normalized["narration"] == "The tavern quiets."
    assert normalized["memory_candidates"][0]["owner"] == "bran"
    assert normalized["future_hook_candidates"][0]["summary"].startswith("Someone may notice")
    assert _combined_payload_has_useful_content(normalized) is True


def test_extract_nested_combined_payload_accepts_result_wrapper():
    parsed = {
        "result": {
            "narration": {
                "narration": "The mill creaks in the wind.",
                "action": "The inspection reveals old tracks.",
            },
            "candidates": [
                {
                    "kind": "semantic_intent",
                    "payload": {"intent": "inspect", "summary": "The player inspects."},
                }
            ],
        }
    }

    normalized = _extract_nested_combined_payload(parsed)

    assert normalized["narration"] == "The mill creaks in the wind."
    assert normalized["candidates"][0]["kind"] == "semantic_intent"
    assert _combined_payload_has_useful_content(normalized) is True


def test_combined_payload_missing_useful_content_is_false():
    assert _combined_payload_has_useful_content({"ok": True}) is False