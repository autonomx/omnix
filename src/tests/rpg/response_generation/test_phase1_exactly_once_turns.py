from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import Any

from app.apps.rpg.session.jobs.foreground_submission_store import InMemoryForegroundSubmissionStore
from app.apps.rpg.session.jobs.foreground_turn import execute_foreground_turn
from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobStatus, ResourceClass
from tests.support.in_memory_jobs import InMemoryJobStore


def test_provider_free_job_store_is_explicit_in_memory_double(tmp_path: Path) -> None:
    namespace = tmp_path / "jobs.sqlite"
    store = InMemoryJobStore(namespace)

    assert not hasattr(store, "_connect")
    assert not namespace.exists()
    created = store.create_job(
        CreateJobRequest(
            module="test",
            type="test.in-memory",
            resource_class=ResourceClass.CPU,
        )
    )
    assert store.get_job(created.id) is not None
    assert not namespace.exists()


def test_provider_free_job_store_serializes_concurrent_writers(tmp_path: Path) -> None:
    store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    created: list[str] = []
    errors: list[Exception] = []

    def create(index: int) -> None:
        try:
            job = store.create_job(
                CreateJobRequest(
                    module="test",
                    type=f"test.concurrent-writer.{index}",
                    resource_class=ResourceClass.CPU,
                )
            )
            created.append(job.id)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    writers = [Thread(target=create, args=(index,)) for index in range(8)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join(timeout=5)

    assert not errors
    assert len(created) == 8
    assert len(set(created)) == 8
    assert len(store.list_jobs()) == 8
    assert all(not writer.is_alive() for writer in writers)


def test_foreground_turn_submission_is_executed_once(monkeypatch: Any, tmp_path: Path) -> None:
    jobs = InMemoryJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: jobs)
    submissions = InMemoryForegroundSubmissionStore(tmp_path / "submissions")
    calls: list[str] = []

    def apply_turn(session_id: str, command: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(f"{session_id}:{command}")
        return {"ok": True, "final_narration": "Bran answers.", "turn_id": "turn:1", "interaction_id": "interaction:1"}

    first = execute_foreground_turn(apply_turn, "session:bran", "How is business?", submission_id="submit:stable",
                                    submissions=submissions)
    second = execute_foreground_turn(apply_turn, "session:bran", "How is business?", submission_id="submit:stable",
                                     submissions=submissions)

    assert calls == ["session:bran:How is business?"]
    assert first["submission_id"] == "submit:stable"
    assert second["submission_id"] == "submit:stable"
    assert second["idempotent_replay"] is True and second["interaction_id"] == "interaction:1"
    assert submissions.get("session:bran", "submit:stable").status == "completed"
    assert jobs.list_jobs() == []  # the claim is the record of the turn: no job is written for it (F2)


def test_terminal_job_state_cannot_be_reopened_or_overwritten(tmp_path: Path) -> None:
    store = InMemoryJobStore(tmp_path / "jobs.sqlite")
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
