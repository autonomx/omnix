"""A structured result keeps its structure when its stale result text is patched (WP-5.6)."""
from __future__ import annotations

from app.apps.rpg.session.visible_response_core import _patch_visible_interaction_reason_into_payload_text


def test_a_structured_result_is_patched_in_place_not_stringified() -> None:
    payload = {
        "narration": "You search.\nResult: unknown_item",
        "result": {
            "narration": "Result: item_not_found",
            "steps": [{"text": "RESULT: unknown"}, {"text": "kept"}],
            "roll": 7,
            "empty": "",
        },
    }

    patched = _patch_visible_interaction_reason_into_payload_text(payload, visible_reason="the drawer is locked")

    assert patched["narration"] == "You search.\nResult: the drawer is locked"
    result = patched["result"]
    assert isinstance(result, dict)
    assert result["narration"] == "Result: the drawer is locked"
    assert result["steps"] == [{"text": "RESULT: the drawer is locked"}, {"text": "kept"}]  # a whole line keeps its prefix
    assert (result["roll"], result["empty"]) == (7, "")


def test_an_empty_top_level_text_still_reports_the_reason() -> None:
    patched = _patch_visible_interaction_reason_into_payload_text({"summary": ""}, visible_reason="locked")
    assert patched["summary"] == "Result: locked"
