from __future__ import annotations

from app.assist_core.result_validation import validated_result_display


def test_validated_result_display_normalizes_valid_payload() -> None:
    assert validated_result_display(
        {
            "ok": True,
            "item_id": "item-1",
            "summary": "Ready for review.",
            "review": True,
        }
    ) == {
        "ok": True,
        "item_id": "item-1",
        "summary": "Ready for review.",
        "review": True,
    }


def test_validated_result_display_returns_safe_review_state_for_missing_fields() -> None:
    assert validated_result_display({"ok": True, "item_id": "item-1"}) == {
        "ok": False,
        "item_id": "item-1",
        "summary": "Missing required result fields.",
        "review": True,
    }
