from __future__ import annotations

from pathlib import Path
from typing import Any

from app.gateway.rpg_turn_job_mirror import _apply_turn_with_job_mirror
from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobStatus, ResourceClass
from app.jobs.rpg_turn_job_guard import RPG_FOREGROUND_RECORD_TYPE
from app.jobs.store import SQLiteJobStore


def test_foreground_turn_submission_is_executed_once(monkeypatch: Any, tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: store)
    calls: list[str] = []

    def apply_turn(session_id: str, command: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(f"{session_id}:{command}")
        return {"ok": True, "final_narration": "Bran answers.", "turn_id": "turn:1"}

    first = _apply_turn_with_job_mirror(
        apply_turn,
        "session:bran",
        "How is business?",
        submission_id="submit:stable",
    )
    second = _apply_turn_with_job_mirror(
        apply_turn,
        "session:bran",
        "How is business?",
        submission_id="submit:stable",
    )

    assert calls == ["session:bran:How is business?"]
    assert first["submission_id"] == "submit:stable"
    assert second["submission_id"] == "submit:stable"
    assert second["idempotent_replay"] is True
    records = store.list_jobs()
    assert len(records) == 1
    assert records[0].type == RPG_FOREGROUND_RECORD_TYPE
    assert records[0].status == JobStatus.COMPLETED
    assert records[0].compat["record_only"] is True


def test_terminal_job_state_cannot_be_reopened_or_overwritten(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    job = store.create_job(
        CreateJobRequest(
            module="test",
            type="test.job",
            resource_class=ResourceClass.CPU,
            input_payload={"value": 1},
        )
    )
    completed = store.complete_job(
        job.id,
        CompleteJobRequest(output_refs=[{"value": "first"}], logs=[]),
    )
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED

    running = store.mark_running(job.id)
    failed = store.fail_job(
        job.id,
        FailJobRequest(code="late_failure", message="late", retryable=False),
    )
    overwritten = store.complete_job(
        job.id,
        CompleteJobRequest(output_refs=[{"value": "second"}], logs=[]),
    )

    assert running is not None and running.status == JobStatus.COMPLETED
    assert failed is not None and failed.status == JobStatus.COMPLETED
    assert overwritten is not None and overwritten.output_refs == [{"value": "first"}]


def test_record_only_type_is_not_an_inline_executable() -> None:
    from app.jobs.inline_feature_jobs import INLINE_FEATURE_JOB_TYPES

    assert RPG_FOREGROUND_RECORD_TYPE not in INLINE_FEATURE_JOB_TYPES
