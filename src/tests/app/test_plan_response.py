from __future__ import annotations

from app.assist_core.plan_response import plan_response_payload


def test_plan_response_payload_defaults_to_review_only() -> None:
    assert plan_response_payload({}) == {
        "ok": False,
        "item_id": "plan",
        "summary": "Review proposal before use.",
        "review": True,
        "executes": False,
        "steps": [],
        "risks": [],
    }


def test_plan_response_payload_normalizes_steps_and_risks() -> None:
    payload = plan_response_payload(
        {
            "ok": True,
            "item_id": "plan-1",
            "summary": "Ready for review.",
            "steps": [{"id": "step-1", "title": "Read", "status": "ready"}],
            "risks": [{"id": "risk-1", "label": "Boundary", "severity": "high"}],
        }
    )

    assert payload["ok"] is True
    assert payload["review"] is True
    assert payload["executes"] is False
    assert payload["steps"][0]["reviewRequired"] is True
    assert payload["risks"][0]["reviewRequired"] is True
