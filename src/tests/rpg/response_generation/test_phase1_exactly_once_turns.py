from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import Any

from app.gateway.rpg_turn_job_mirror import _apply_turn_with_job_mirror
from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobStatus, ResourceClass
from app.jobs.rpg_turn_job_guard import RPG_FOREGROUND_RECORD_TYPE
from app.testing.in_memory_job_store import InMemoryJobStore


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
    store = InMemoryJobStore(tmp_path / "jobs.sqlite")
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


def test_foreground_submission_lookup_does_not_scan_all_jobs(monkeypatch: Any, tmp_path: Path) -> None:
    store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: store)
    calls: list[str] = []

    def apply_turn(session_id: str, command: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(command)
        return {"ok": True, "final_narration": "Bran answers.", "interaction_id": "interaction:1"}

    def fail_full_scan(*args: Any, **kwargs: Any) -> list[Any]:
        raise AssertionError("foreground idempotency must not scan the complete job table")

    monkeypatch.setattr(store, "list_jobs", fail_full_scan)

    first = _apply_turn_with_job_mirror(
        apply_turn,
        "session:bran",
        "How is business?",
        submission_id="submit:indexed",
    )
    replay = _apply_turn_with_job_mirror(
        apply_turn,
        "session:bran",
        "How is business?",
        submission_id="submit:indexed",
    )

    assert calls == ["How is business?"]
    assert first["interaction_id"] == "interaction:1"
    assert replay["interaction_id"] == "interaction:1"
    assert replay["idempotent_replay"] is True


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


def test_record_only_type_is_not_an_inline_executable() -> None:
    from app.jobs.inline_feature_jobs import INLINE_FEATURE_JOB_TYPES

    assert RPG_FOREGROUND_RECORD_TYPE not in INLINE_FEATURE_JOB_TYPES
