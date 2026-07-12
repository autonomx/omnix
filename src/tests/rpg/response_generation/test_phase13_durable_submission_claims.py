from __future__ import annotations

import multiprocessing
import os
import queue
import time
from pathlib import Path
from typing import Any

import pytest

from app.jobs.rpg_foreground_submission_store import RpgForegroundSubmissionStore


def _cross_process_turn_worker(
    db_path: str,
    start_event: Any,
    execution_queue: Any,
    result_queue: Any,
) -> None:
    from app.gateway.rpg_turn_job_mirror import _apply_turn_with_job_mirror
    from app.jobs import store as job_store_module
    from app.jobs.store import SQLiteJobStore

    local_store = SQLiteJobStore(db_path)
    job_store_module.default_job_store = lambda: local_store

    def apply_turn(session_id: str, command: str, *_: Any, **__: Any) -> dict[str, Any]:
        execution_queue.put(os.getpid())
        time.sleep(0.2)
        return {
            "ok": True,
            "turn_id": "turn:durable:1",
            "interaction_id": "interaction:durable:1",
            "final_narration": "Bran answers from behind the bar.",
            "npc": {
                "speaker_id": "npc:bran",
                "speaker": "Bran",
                "line": "Business is steady enough for now.",
            },
        }

    start_event.wait(5.0)
    try:
        result = _apply_turn_with_job_mirror(
            apply_turn,
            "session:durable",
            "I ask Bran how business is doing.",
            submission_id="submit:durable:shared",
        )
        result_queue.put(
            {
                "ok": True,
                "interaction_id": result.get("interaction_id"),
                "submission_id": result.get("submission_id"),
                "idempotent_replay": result.get("idempotent_replay") is True,
            }
        )
    except Exception as exc:  # pragma: no cover - surfaced to the parent assertion
        result_queue.put({"ok": False, "error": repr(exc)})


def test_submission_claim_is_unique_across_store_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.sqlite"
    first_store = RpgForegroundSubmissionStore(db_path)
    second_store = RpgForegroundSubmissionStore(db_path)

    first = first_store.claim("session:one", "submit:one")
    second = second_store.claim("session:one", "submit:one")

    assert first.owner is True
    assert first.claim_token
    assert second.owner is False
    assert second.claim_token is None
    assert second.status == "claimed"

    assert first_store.complete(
        "session:one",
        "submit:one",
        str(first.claim_token),
        {"ok": True, "interaction_id": "interaction:one"},
    ) is True
    recovered = second_store.get("session:one", "submit:one")

    assert recovered is not None
    assert recovered.status == "completed"
    assert recovered.result == {"ok": True, "interaction_id": "interaction:one"}


def test_claim_token_prevents_non_owner_finalization(tmp_path: Path) -> None:
    store = RpgForegroundSubmissionStore(tmp_path / "jobs.sqlite")
    claim = store.claim("session:one", "submit:one")

    assert store.complete(
        "session:one",
        "submit:one",
        "not-the-owner-token",
        {"ok": True},
    ) is False
    assert store.fail(
        "session:one",
        "submit:one",
        "not-the-owner-token",
        "not owner",
    ) is False
    current = store.get("session:one", "submit:one")

    assert claim.owner is True
    assert current is not None
    assert current.status == "claimed"
    assert current.result is None
    assert current.error is None


def test_two_gateway_processes_execute_one_shared_submission(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    execution_queue = context.Queue()
    result_queue = context.Queue()
    db_path = str(tmp_path / "jobs.sqlite")
    processes = [
        context.Process(
            target=_cross_process_turn_worker,
            args=(db_path, start_event, execution_queue, result_queue),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=15.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)

    assert [process.exitcode for process in processes] == [0, 0]
    results = [result_queue.get(timeout=3.0) for _ in processes]
    assert all(result["ok"] is True for result in results), results
    assert {result["interaction_id"] for result in results} == {"interaction:durable:1"}
    assert {result["submission_id"] for result in results} == {"submit:durable:shared"}
    assert sum(1 for result in results if result["idempotent_replay"]) == 1

    execution_queue.get(timeout=3.0)
    with pytest.raises(queue.Empty):
        execution_queue.get(timeout=0.3)
