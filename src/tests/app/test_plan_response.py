from __future__ import annotations

from app.assist_core.plan_response import plan_response_payload


def test_plan_response_requires_review_without_execution() -> None:
    payload = plan_response_payload("p1", "summary")

    assert payload["ok"] is True
    assert payload["item_id"] == "p1"
    assert payload["review"] is True
    assert payload["execute"] is False
