from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

from app.gateway.rpg_foreground_turn_record import FOREGROUND_TURN_RECORD_MAX_BYTES
from app.gateway.rpg_turn_job_mirror import (
    _apply_turn_with_job_mirror,
    _submission_lock_count,
)
from app.jobs.rpg_last10_report_debug import build_turn_debug_payload
from app.jobs.store import SQLiteJobStore
from app.rpg.presentation.turn_response import build_turn_response_v2

_FORBIDDEN_GRAPH_KEYS = {
    "session",
    "simulation_state",
    "runtime_state",
    "foreground_job",
    "raw_turn_result",
}


def _turn_result(index: int = 1) -> dict[str, Any]:
    return {
        "ok": True,
        "turn_id": f"turn:{index}",
        "interaction_id": f"interaction:{index}",
        "tick": index,
        "state_revision": index + 10,
        "stateful": True,
        "changed_domains": ["conversation", "inventory", "currency"],
        "action_type": "trade",
        "semantic_action_type": "trade",
        "semantic_family": "trade",
        "final_narration": "Bran counts the coins and slides the supplies across the bar.",
        "npc": {
            "speaker_id": "npc:bran",
            "speaker": "Bran",
            "line": "That settles it. Keep the supplies dry and they will see you through the old road.",
        },
        "session": {
            "manifest": {"id": "session:record", "turn_count": index},
            "simulation_state": {"large": "x" * 100_000},
            "runtime_state": {"large": "y" * 100_000},
        },
        "simulation_state": {"large": "z" * 100_000},
        "runtime_state": {"large": "w" * 100_000},
    }


def _contains_forbidden_graph_key(value: Any) -> bool:
    if isinstance(value, dict):
        if _FORBIDDEN_GRAPH_KEYS & set(value):
            return True
        return any(_contains_forbidden_graph_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_graph_key(item) for item in value)
    return False


def test_foreground_job_stores_only_bounded_v2_record(monkeypatch: Any, tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: store)

    result = _apply_turn_with_job_mirror(
        lambda *_args, **_kwargs: _turn_result(),
        "session:record",
        "I buy road supplies from Bran.",
        submission_id="submit:record",
    )

    jobs = store.list_jobs()
    assert len(jobs) == 1
    output = jobs[0].output_refs[0]
    record = output["turn_response"]
    encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    report_debug = build_turn_debug_payload(jobs[0])

    assert result["interaction_id"] == "interaction:1"
    assert output["record_version"] == "rpg_foreground_turn_record_v1"
    assert "raw_turn_result" not in output
    assert len(encoded) <= FOREGROUND_TURN_RECORD_MAX_BYTES
    assert _contains_forbidden_graph_key(record) is False
    assert record["contract_version"] == "rpg_turn_response_v2"
    assert record["simulation_tick"] == 1
    assert record["state"]["revision"] == 11
    assert record["state"]["changed_domains"] == ["conversation", "inventory", "currency"]
    assert record["result"]["stateful"] is True
    assert report_debug["turn_response_record"]["interaction_id"] == "interaction:1"
    assert "raw_turn_result" not in report_debug


def test_compact_replay_is_projection_stable(monkeypatch: Any, tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: store)
    calls = 0

    def apply_turn(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _turn_result(4)

    first = _apply_turn_with_job_mirror(
        apply_turn,
        "session:record",
        "I buy road supplies from Bran.",
        submission_id="submit:stable",
    )
    replay = _apply_turn_with_job_mirror(
        apply_turn,
        "session:record",
        "I buy road supplies from Bran.",
        submission_id="submit:stable",
    )
    projected = build_turn_response_v2(
        replay,
        session_id="session:record",
        command="I buy road supplies from Bran.",
    )

    assert calls == 1
    assert first["interaction_id"] == replay["interaction_id"] == "interaction:4"
    assert replay["idempotent_replay"] is True
    assert projected["simulation_tick"] == 4
    assert projected["state"]["revision"] == 14
    assert projected["state"]["changed_domains"] == ["conversation", "inventory", "currency"]
    assert projected["result"]["stateful"] is True
    assert "Bran" in projected["visible_response"]["plain_text"]


def test_submission_lock_entries_are_released_after_concurrent_replay(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: store)
    calls = 0
    calls_guard = Lock()

    def apply_turn(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        with calls_guard:
            calls += 1
        return _turn_result(7)

    def submit(_: int) -> dict[str, Any]:
        return _apply_turn_with_job_mirror(
            apply_turn,
            "session:record",
            "I ask Bran about the road.",
            submission_id="submit:shared-lock",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(24)))

    assert calls == 1
    assert {result["interaction_id"] for result in results} == {"interaction:7"}
    assert _submission_lock_count() == 0


def test_unique_submission_locks_do_not_accumulate(monkeypatch: Any, tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: store)

    for index in range(20):
        _apply_turn_with_job_mirror(
            lambda *_args, current=index, **_kwargs: _turn_result(current + 1),
            "session:record",
            f"Unique command {index}",
            submission_id=f"submit:unique:{index}",
        )

    assert len(store.list_jobs()) == 20
    assert _submission_lock_count() == 0


def test_source_no_longer_writes_synthetic_or_raw_turn_graphs() -> None:
    source = Path("src/app/gateway/rpg_turn_job_mirror.py").read_text(encoding="utf-8")

    assert "synthetic_job_mirror" not in source
    assert "raw_turn_result" not in source
    assert '"turn_response": turn_record' in source
