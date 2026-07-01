from __future__ import annotations

from app.assist_core.plan_audit_redaction import redact_plan_audit_detail


def test_plan_audit_redaction_truncates_large_fields() -> None:
    payload = redact_plan_audit_detail({"context": "abcdefghij"}, max_length=4)

    assert payload == {"context": "abcd..."}


def test_plan_audit_redaction_removes_secret_like_fields() -> None:
    payload = redact_plan_audit_detail(
        {
            "token": "abc",
            "api_key": "def",
            "summary": "visible",
        }
    )

    assert payload == {
        "token": "[redacted]",
        "api_key": "[redacted]",
        "summary": "visible",
    }


def test_plan_audit_redaction_handles_missing_fields() -> None:
    assert redact_plan_audit_detail({}) == {}
