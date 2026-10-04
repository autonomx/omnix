from __future__ import annotations

from app.rpg.worlds.generation_finding_policy import (
    finding_severity,
    finding_waiver_policy_report,
)


def _result(
    *,
    code: str,
    severity: str = "warning",
    waiver_status: str = "active",
    reason: str = "Reviewed and accepted as a presentation-only limitation.",
) -> dict:
    return {
        "topic_id": "actors",
        "status": "accepted",
        "validation": {
            "validation_status": "failed",
            "waiver_status": waiver_status,
            "outstanding_findings": [
                {
                    "code": code,
                    "severity": severity,
                    "item_id": "ent:actor:001",
                    "field_id": "description",
                    "message": "Retained validation finding.",
                }
            ],
            "waiver": {
                "status": waiver_status,
                "reason": reason,
                "accepted_by": "local-game-master",
                "accepted_at": "2026-07-27T23:00:00+00:00",
            },
        },
    }


def test_reasoned_warning_waiver_is_certifiable_and_visible() -> None:
    report = finding_waiver_policy_report([_result(code="style_repetition")])

    assert report["passed"] is True
    assert report["severity_counts"] == {"warning": 1}
    assert report["active_waiver_count"] == 1
    assert report["active_waivers"][0]["reason"].startswith("Reviewed")
    assert report["blocking_findings"] == []


def test_error_finding_cannot_be_waived() -> None:
    report = finding_waiver_policy_report(
        [_result(code="semantic_contradiction", severity="error")]
    )

    assert report["passed"] is False
    assert report["invalid_waiver_count"] == 1
    assert report["invalid_waivers"][0]["policy_reason"] == "severity_not_waivable"
    assert report["blocking_findings"][0]["severity"] == "error"


def test_warning_waiver_requires_a_reason() -> None:
    report = finding_waiver_policy_report(
        [_result(code="style_repetition", reason="")]
    )

    assert report["passed"] is False
    assert report["invalid_waivers"][0]["policy_reason"] == "waiver_reason_required"


def test_unwaived_finding_remains_blocking() -> None:
    report = finding_waiver_policy_report(
        [_result(code="style_repetition", waiver_status="none")]
    )

    assert report["passed"] is False
    assert report["blocking_findings"][0]["policy_reason"] == "finding_not_waived"


def test_structural_fatal_code_overrides_provider_warning_label() -> None:
    finding = {"code": "duplicate_id", "severity": "warning"}

    assert finding_severity(finding) == "fatal"
    report = finding_waiver_policy_report(
        [_result(code="duplicate_id", severity="warning")]
    )
    assert report["passed"] is False
    assert report["blocking_findings"][0]["severity"] == "fatal"


def test_unknown_severity_fails_closed_as_error() -> None:
    assert finding_severity({"code": "new_validator_code"}) == "error"
