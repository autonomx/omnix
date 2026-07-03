from __future__ import annotations

from app.assist_core.hermes_sequence_job_contract import hermes_sequence_job_progress


def state(statuses: list[str]) -> dict:
    return {
        "session_id": "session-1",
        "sequence_id": "seq-1",
        "sequence": {"items": [{"item_id": f"item-{index}"} for index in range(len(statuses))]},
        "item_statuses": [{"item_id": f"item-{index}", "status": status} for index, status in enumerate(statuses)],
    }


def test_sequence_job_progress_reports_completed() -> None:
    result = hermes_sequence_job_progress(state(["done", "done"]))

    assert result["status"] == "completed"
    assert result["progress_percent"] == 100


def test_sequence_job_progress_reports_failed_blocked() -> None:
    result = hermes_sequence_job_progress({**state(["done", "blocked"]), "blocked_reason": "combat_action"})

    assert result["status"] == "failed"
    assert result["blocked_reason"] == "combat_action"


def test_sequence_job_progress_preserves_paused_and_resumed_statuses() -> None:
    assert hermes_sequence_job_progress(state(["done", "pending"]), job_status="paused")["status"] == "paused"
    assert hermes_sequence_job_progress(state(["done", "pending"]), job_status="running")["status"] == "running"
