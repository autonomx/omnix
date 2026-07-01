from __future__ import annotations

from app.assist_core.review_boundary import review_boundary_payload


def test_review_boundary_approval_alone_is_not_ready_for_execution() -> None:
    payload = review_boundary_payload({"decision": "approved"})

    assert payload["ok"] is True
    assert payload["ready_for_execution"] is False
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_review_boundary_requires_future_runner_for_ready_state() -> None:
    payload = review_boundary_payload({"decision": "approved"}, runner_available=True)

    assert payload["ready_for_execution"] is True
    assert payload["executes"] is False


def test_review_boundary_rejected_label_stays_not_ready() -> None:
    payload = review_boundary_payload({"decision": "rejected"}, runner_available=True)

    assert payload["ok"] is False
    assert payload["ready_for_execution"] is False
    assert payload["executes"] is False
