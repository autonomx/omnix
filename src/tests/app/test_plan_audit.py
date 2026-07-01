from __future__ import annotations

from app.assist_core.plan_audit import plan_audit_payload


def test_plan_audit_payload_uses_fixed_timestamp_and_safe_flags() -> None:
    assert plan_audit_payload(
        source="plan_request",
        mode="rpg",
        timestamp="2026-01-01T00:00:00Z",
        detail={"item_id": "plan-1"},
    ) == {
        "source": "plan_request",
        "mode": "rpg",
        "timestamp": "2026-01-01T00:00:00Z",
        "detail": {"item_id": "plan-1"},
        "read_only": True,
        "executes": False,
        "review_required": True,
    }


def test_plan_audit_payload_defaults_detail_to_empty_record() -> None:
    payload = plan_audit_payload(
        source="plan_result",
        mode="agent_mode",
        timestamp="2026-01-01T00:00:00Z",
    )

    assert payload["detail"] == {}
    assert payload["read_only"] is True
    assert payload["executes"] is False
    assert payload["review_required"] is True
