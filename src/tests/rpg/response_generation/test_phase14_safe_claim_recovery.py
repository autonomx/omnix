from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.gateway.rpg_turn_job_mirror import _apply_turn_with_job_mirror
from app.jobs.rpg_foreground_submission_store import RpgForegroundSubmissionStore
from app.testing.in_memory_job_store import InMemoryJobStore


def _time(second: int = 0) -> datetime:
    return datetime(2026, 7, 12, 12, 0, second, tzinfo=timezone.utc)


def test_expired_pre_execution_claim_can_be_taken_over(tmp_path: Path) -> None:
    store = RpgForegroundSubmissionStore(tmp_path / "jobs.sqlite")
    first = store.claim(
        "session:lease",
        "submit:lease",
        lease_seconds=10,
        now=_time(),
    )
    second = store.claim(
        "session:lease",
        "submit:lease",
        lease_seconds=10,
        now=_time() + timedelta(seconds=11),
    )

    assert first.owner is True
    assert second.owner is True
    assert second.claim_token
    assert second.claim_token != first.claim_token
    assert second.execution_started_at is None
    assert store.complete(
        "session:lease",
        "submit:lease",
        str(first.claim_token),
        {"ok": True, "owner": "old"},
    ) is False
    assert store.complete(
        "session:lease",
        "submit:lease",
        str(second.claim_token),
        {"ok": True, "owner": "new"},
    ) is True


def test_started_claim_is_never_taken_over_after_expiry(tmp_path: Path) -> None:
    store = RpgForegroundSubmissionStore(tmp_path / "jobs.sqlite")
    first = store.claim(
        "session:started",
        "submit:started",
        lease_seconds=10,
        now=_time(),
    )
    assert store.attach_job(
        "session:started",
        "submit:started",
        str(first.claim_token),
        "job:started",
        now=_time() + timedelta(seconds=1),
    ) is True
    assert store.mark_execution_started(
        "session:started",
        "submit:started",
        str(first.claim_token),
        now=_time() + timedelta(seconds=2),
    ) is True

    duplicate = store.claim(
        "session:started",
        "submit:started",
        lease_seconds=10,
        now=_time() + timedelta(minutes=5),
    )

    assert duplicate.owner is False
    assert duplicate.claim_token is None
    assert duplicate.execution_started_at == (_time() + timedelta(seconds=2)).isoformat()
    assert store.complete(
        "session:started",
        "submit:started",
        str(first.claim_token),
        {"ok": True, "interaction_id": "interaction:started"},
    ) is True


def test_pre_execution_lease_can_be_renewed(tmp_path: Path) -> None:
    store = RpgForegroundSubmissionStore(tmp_path / "jobs.sqlite")
    first = store.claim(
        "session:renew",
        "submit:renew",
        lease_seconds=10,
        now=_time(),
    )
    assert store.renew(
        "session:renew",
        "submit:renew",
        str(first.claim_token),
        lease_seconds=10,
        now=_time() + timedelta(seconds=5),
    ) is True

    before_expiry = store.claim(
        "session:renew",
        "submit:renew",
        lease_seconds=10,
        now=_time() + timedelta(seconds=12),
    )
    after_expiry = store.claim(
        "session:renew",
        "submit:renew",
        lease_seconds=10,
        now=_time() + timedelta(seconds=16),
    )

    assert before_expiry.owner is False
    assert after_expiry.owner is True
    assert after_expiry.claim_token != first.claim_token


def test_runtime_claim_store_does_not_read_or_mutate_legacy_sqlite_claims(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.sqlite"
    legacy_time = _time().isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE rpg_foreground_submissions (
                session_id TEXT NOT NULL,
                submission_id TEXT NOT NULL,
                status TEXT NOT NULL,
                claim_token TEXT NOT NULL,
                job_id TEXT,
                result_json TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_id, submission_id)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO rpg_foreground_submissions (
                session_id, submission_id, status, claim_token,
                job_id, result_json, error_text, created_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
            """,
            ("session:legacy", "submit:legacy", "claimed", "legacy-token", legacy_time, legacy_time),
        )

    store = RpgForegroundSubmissionStore(db_path)

    assert store.get("session:legacy", "submit:legacy") is None
    fresh = store.claim(
        "session:fresh",
        "submit:fresh",
        now=_time() + timedelta(days=1),
    )
    assert fresh.owner is True
    assert not hasattr(store, "_connect")

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT session_id, submission_id, status, claim_token FROM rpg_foreground_submissions"
        ).fetchall()
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(rpg_foreground_submissions)").fetchall()
        }
    assert rows == [("session:legacy", "submit:legacy", "claimed", "legacy-token")]
    assert "lease_expires_at" not in columns
    assert "execution_started_at" not in columns


def test_gateway_recovers_abandoned_pre_execution_claim(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "jobs.sqlite"
    job_store = InMemoryJobStore(db_path)
    submission_store = RpgForegroundSubmissionStore(db_path)
    old_claim = submission_store.claim(
        "session:gateway-recovery",
        "submit:gateway-recovery",
        lease_seconds=1,
        now=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: job_store)
    monkeypatch.setenv("OMNIX_RPG_SUBMISSION_LEASE_SECONDS", "30")
    calls: list[str] = []

    def apply_turn(session_id: str, command: str, *_: Any, **__: Any) -> dict[str, Any]:
        calls.append(f"{session_id}:{command}")
        return {
            "ok": True,
            "turn_id": "turn:recovered:1",
            "interaction_id": "interaction:recovered:1",
            "final_narration": "Bran answers after ownership is recovered.",
        }

    result = _apply_turn_with_job_mirror(
        apply_turn,
        "session:gateway-recovery",
        "I ask Bran how business is doing.",
        submission_id="submit:gateway-recovery",
    )

    assert calls == [
        "session:gateway-recovery:I ask Bran how business is doing."
    ]
    assert result["submission_id"] == "submit:gateway-recovery"
    assert result["interaction_id"] == "interaction:recovered:1"
    assert submission_store.complete(
        "session:gateway-recovery",
        "submit:gateway-recovery",
        str(old_claim.claim_token),
        {"ok": True, "owner": "old"},
    ) is False
    terminal = submission_store.get(
        "session:gateway-recovery",
        "submit:gateway-recovery",
    )
    assert terminal is not None
    assert terminal.status == "completed"
    assert terminal.result is not None
    assert terminal.result["interaction_id"] == "interaction:recovered:1"
