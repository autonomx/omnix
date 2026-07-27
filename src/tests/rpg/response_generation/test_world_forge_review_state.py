from __future__ import annotations

from app.rpg.worlds.generation_attempt_history import with_validation_attempt
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


def _result(
    *,
    run_id: str = "run:1",
    candidate_hash: str = "sha256:first",
    validation: dict | None = None,
    previous_result: dict | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "topic_id": "actors",
        "status": "needs_review",
        "candidate_hash": candidate_hash,
        "validation": validation or _failed_validation(),
        "provider": {"provider": "lmstudio", "model": "test", "attempt_count": 1},
        "job_id": f"job:{run_id}",
        "previous_result": previous_result,
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
            "run_id": "run:legacy",
            "topic_id": "actors",
            "candidate_hash": "sha256:legacy",
            "job_id": "job:legacy",
            "provider": {},
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

    assert state["review_decision"] == "accepted"
    assert state["validation_status"] == "failed"
    assert state["waiver_status"] == "active"
    assert state["outstanding_finding_count"] == 1
    assert state["outstanding_findings"] == _failed_validation()["issues"]
    assert state["outstanding_reason_codes"] == ["dangling_entity_ref"]
    assert state["attempt_count"] == 1


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


def test_validation_attempt_is_deterministic_and_not_duplicated() -> None:
    first = with_validation_attempt(
        _failed_validation(),
        run_id="run:1",
        topic_id="actors",
        result_status="needs_review",
        candidate_hash="sha256:first",
        provider={"provider": "lmstudio", "attempt_count": 1},
        job_id="job:1",
    )
    repeated = with_validation_attempt(
        first,
        run_id="run:1",
        topic_id="actors",
        result_status="needs_review",
        candidate_hash="sha256:first",
        provider={"provider": "lmstudio", "attempt_count": 1},
        job_id="job:1",
    )

    assert len(first["attempt_history"]) == 1
    assert repeated["attempt_history"] == first["attempt_history"]
    assert first["attempt_history"][0]["validation_hash"].startswith("sha256:")


def test_review_state_combines_parent_and_manual_retry_attempts() -> None:
    parent = _result(run_id="run:1", candidate_hash="sha256:first")
    child = _result(
        run_id="run:2",
        candidate_hash="sha256:second",
        previous_result=parent,
    )

    state = review_state(child)

    assert state["attempt_count"] == 2
    assert [attempt["trigger"] for attempt in state["attempt_history"]] == [
        "generation",
        "manual_retry",
    ]
    assert [attempt["candidate_hash"] for attempt in state["attempt_history"]] == [
        "sha256:first",
        "sha256:second",
    ]


def test_acceptance_preserves_materialised_attempt_ledger() -> None:
    validation = with_validation_attempt(
        _failed_validation(),
        run_id="run:1",
        topic_id="actors",
        result_status="needs_review",
        candidate_hash="sha256:first",
        provider={"attempt_count": 1},
        job_id="job:1",
    )

    accepted = accepted_review_report(
        validation,
        accepted_at="2026-07-27T20:00:00+00:00",
    )

    assert accepted["attempt_history"] == validation["attempt_history"]
    assert accepted["attempt_history_schema"] == validation["attempt_history_schema"]
