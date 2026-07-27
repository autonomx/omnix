from __future__ import annotations

from app.rpg.worlds.generation_review_state import (
    accepted_review_report,
    review_state,
    validation_evidence,
)


def _failed_validation() -> dict:
    return {
        "schema_version": "rpg_world_generation_review_v1",
        "status": "needs_review",
        "blocking": True,
        "reason_codes": ["dangling_entity_ref"],
        "issues": [
            {
                "code": "dangling_entity_ref",
                "topic_id": "actors",
                "entity_id": "ent:actor:004",
                "field_id": "group_ids",
                "message": "Unknown group reference.",
                "supplied_value": "ent:groups:[MegaCorps]",
            }
        ],
        "summary": "Candidate requires review.",
    }


def test_acceptance_preserves_failed_validation_as_active_waiver() -> None:
    report = accepted_review_report(
        _failed_validation(),
        accepted_at="2026-07-27T20:00:00+00:00",
        waiver_reason="Retry budget exhausted; continue authoring.",
    )

    assert report["status"] == "accepted"
    assert report["review_decision"] == "accepted"
    assert report["validation_status"] == "failed"
    assert report["waiver_status"] == "active"
    assert report["blocking"] is False
    assert report["validation_blocking"] is True
    assert report["reason_codes"] == ["dangling_entity_ref"]
    assert report["issues"][0]["field_id"] == "group_ids"
    assert report["outstanding_findings"] == report["issues"]
    assert report["waiver"]["reason"] == "Retry budget exhausted; continue authoring."
    assert report["previous_validation"]["status"] == "needs_review"


def test_acceptance_after_passed_validation_has_no_waiver() -> None:
    report = accepted_review_report(
        {
            "status": "accepted",
            "blocking": False,
            "reason_codes": [],
            "issues": [],
        },
        accepted_at="2026-07-27T20:00:00+00:00",
    )

    assert report["review_decision"] == "accepted"
    assert report["validation_status"] == "passed"
    assert report["waiver_status"] == "none"
    assert report["outstanding_findings"] == []


def test_review_state_projects_legacy_accepted_previous_validation() -> None:
    state = review_state(
        {
            "status": "accepted",
            "validation": {
                "status": "accepted",
                "blocking": False,
                "reason_codes": [],
                "issues": [],
                "previous_validation": _failed_validation(),
            },
        }
    )

    assert state == {
        "review_decision": "accepted",
        "validation_status": "failed",
        "waiver_status": "active",
        "outstanding_finding_count": 1,
        "outstanding_findings": _failed_validation()["issues"],
        "outstanding_reason_codes": ["dangling_entity_ref"],
    }


def test_validation_evidence_prefers_explicit_current_outstanding_findings() -> None:
    evidence = validation_evidence(
        {
            "status": "accepted",
            "validation_status": "failed",
            "outstanding_reason_codes": ["current_failure"],
            "outstanding_findings": [
                {
                    "code": "current_failure",
                    "topic_id": "actors",
                    "message": "Current evidence.",
                }
            ],
            "previous_validation": _failed_validation(),
        }
    )

    assert evidence["validation_status"] == "failed"
    assert evidence["outstanding_reason_codes"] == ["current_failure"]
    assert evidence["outstanding_findings"][0]["message"] == "Current evidence."
