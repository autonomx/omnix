"""Durable cross-process ownership for foreground RPG submissions."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

_STATUS_CLAIMED = "claimed"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"
_TERMINAL_STATUSES = {_STATUS_COMPLETED, _STATUS_FAILED}
_DEFAULT_LEASE_SECONDS = 30.0


def _as_utc(value: datetime | None = None) -> datetime:
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return _as_utc(value).isoformat()


def _lease_expiry(now: datetime, lease_seconds: float) -> str:
    seconds = max(0.1, min(600.0, float(lease_seconds)))
    return (now + timedelta(seconds=seconds)).isoformat()


@dataclass(frozen=True)
class ForegroundSubmissionClaim:
    session_id: str
    submission_id: str
    status: str
    owner: bool
    claim_token: str | None = None
    job_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    lease_expires_at: str | None = None
    execution_started_at: str | None = None


class RpgForegroundSubmissionStore:
    """SQLite-backed submission ownership shared by gateway processes."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rpg_foreground_submissions (
                    session_id TEXT NOT NULL,
                    submission_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    claim_token TEXT NOT NULL,
                    job_id TEXT,
                    result_json TEXT,
                    error_text TEXT,
                    lease_expires_at TEXT,
                    execution_started_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, submission_id)
                )
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(rpg_foreground_submissions)").fetchall()
            }
            added_lease = "lease_expires_at" not in columns
            added_started = "execution_started_at" not in columns
            if added_lease:
                conn.execute(
                    "ALTER TABLE rpg_foreground_submissions ADD COLUMN lease_expires_at TEXT"
                )
            if added_started:
                conn.execute(
                    "ALTER TABLE rpg_foreground_submissions ADD COLUMN execution_started_at TEXT"
                )
            if added_started:
                conn.execute(
                    """
                    UPDATE rpg_foreground_submissions
                    SET execution_started_at = updated_at
                    WHERE status = ? AND execution_started_at IS NULL
                    """,
                    (_STATUS_CLAIMED,),
                )
            if added_lease:
                conn.execute(
                    """
                    UPDATE rpg_foreground_submissions
                    SET lease_expires_at = updated_at
                    WHERE lease_expires_at IS NULL
                    """
                )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rpg_foreground_submission_status
                ON rpg_foreground_submissions(status, updated_at)
                """
            )

    def claim(
        self,
        session_id: str,
        submission_id: str,
        *,
        lease_seconds: float = _DEFAULT_LEASE_SECONDS,
        now: datetime | None = None,
    ) -> ForegroundSubmissionClaim:
        token = uuid.uuid4().hex
        instant = _as_utc(now)
        now_text = instant.isoformat()
        expires_at = _lease_expiry(instant, lease_seconds)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO rpg_foreground_submissions (
                    session_id, submission_id, status, claim_token,
                    job_id, result_json, error_text, lease_expires_at,
                    execution_started_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, ?, ?)
                """,
                (
                    session_id,
                    submission_id,
                    _STATUS_CLAIMED,
                    token,
                    expires_at,
                    now_text,
                    now_text,
                ),
            )
            owner = cursor.rowcount == 1
            if not owner:
                cursor = conn.execute(
                    """
                    UPDATE rpg_foreground_submissions
                    SET claim_token = ?, lease_expires_at = ?, updated_at = ?,
                        result_json = NULL, error_text = NULL
                    WHERE session_id = ? AND submission_id = ?
                      AND status = ? AND execution_started_at IS NULL
                      AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                    """,
                    (
                        token,
                        expires_at,
                        now_text,
                        session_id,
                        submission_id,
                        _STATUS_CLAIMED,
                        now_text,
                    ),
                )
                owner = cursor.rowcount == 1
            row = conn.execute(
                """
                SELECT * FROM rpg_foreground_submissions
                WHERE session_id = ? AND submission_id = ?
                """,
                (session_id, submission_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("foreground submission claim was not persisted")
        return self._row_to_claim(row, owner=owner, owner_token=token if owner else None)

    def get(self, session_id: str, submission_id: str) -> ForegroundSubmissionClaim | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM rpg_foreground_submissions
                WHERE session_id = ? AND submission_id = ?
                """,
                (session_id, submission_id),
            ).fetchone()
        return self._row_to_claim(row, owner=False, owner_token=None) if row is not None else None

    def renew(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        *,
        lease_seconds: float = _DEFAULT_LEASE_SECONDS,
        now: datetime | None = None,
    ) -> bool:
        instant = _as_utc(now)
        now_text = instant.isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rpg_foreground_submissions
                SET lease_expires_at = ?, updated_at = ?
                WHERE session_id = ? AND submission_id = ?
                  AND claim_token = ? AND status = ?
                  AND execution_started_at IS NULL
                  AND lease_expires_at > ?
                """,
                (
                    _lease_expiry(instant, lease_seconds),
                    now_text,
                    session_id,
                    submission_id,
                    claim_token,
                    _STATUS_CLAIMED,
                    now_text,
                ),
            )
        return cursor.rowcount == 1

    def attach_job(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        job_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        now_text = _timestamp(now)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rpg_foreground_submissions
                SET job_id = ?, updated_at = ?
                WHERE session_id = ? AND submission_id = ?
                  AND claim_token = ? AND status = ?
                  AND execution_started_at IS NULL
                  AND lease_expires_at > ?
                """,
                (
                    job_id,
                    now_text,
                    session_id,
                    submission_id,
                    claim_token,
                    _STATUS_CLAIMED,
                    now_text,
                ),
            )
        return cursor.rowcount == 1

    def mark_execution_started(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        now_text = _timestamp(now)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rpg_foreground_submissions
                SET execution_started_at = ?, updated_at = ?
                WHERE session_id = ? AND submission_id = ?
                  AND claim_token = ? AND status = ?
                  AND execution_started_at IS NULL
                  AND lease_expires_at > ?
                """,
                (
                    now_text,
                    now_text,
                    session_id,
                    submission_id,
                    claim_token,
                    _STATUS_CLAIMED,
                    now_text,
                ),
            )
        return cursor.rowcount == 1

    def complete(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        result: dict[str, Any],
    ) -> bool:
        encoded = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return self._finalize(
            session_id,
            submission_id,
            claim_token,
            status=_STATUS_COMPLETED,
            result_json=encoded,
            error_text=None,
        )

    def fail(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        error: str,
    ) -> bool:
        return self._finalize(
            session_id,
            submission_id,
            claim_token,
            status=_STATUS_FAILED,
            result_json=None,
            error_text=str(error)[:1000],
        )

    def _finalize(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        *,
        status: str,
        result_json: str | None,
        error_text: str | None,
    ) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rpg_foreground_submissions
                SET status = ?, result_json = ?, error_text = ?, updated_at = ?
                WHERE session_id = ? AND submission_id = ?
                  AND claim_token = ? AND status = ?
                """,
                (
                    status,
                    result_json,
                    error_text,
                    _timestamp(),
                    session_id,
                    submission_id,
                    claim_token,
                    _STATUS_CLAIMED,
                ),
            )
        return cursor.rowcount == 1

    def wait_for_terminal_or_claim(
        self,
        session_id: str,
        submission_id: str,
        *,
        timeout_seconds: float,
        lease_seconds: float = _DEFAULT_LEASE_SECONDS,
        poll_seconds: float = 0.02,
    ) -> ForegroundSubmissionClaim:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            claim = self.claim(
                session_id,
                submission_id,
                lease_seconds=lease_seconds,
            )
            if claim.owner or claim.status in _TERMINAL_STATUSES:
                return claim
            if time.monotonic() >= deadline:
                return claim
            time.sleep(max(0.001, poll_seconds))

    def wait_for_terminal(
        self,
        session_id: str,
        submission_id: str,
        *,
        timeout_seconds: float,
        poll_seconds: float = 0.02,
    ) -> ForegroundSubmissionClaim:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            claim = self.get(session_id, submission_id)
            if claim is None:
                raise RuntimeError("foreground submission claim disappeared")
            if claim.status in _TERMINAL_STATUSES or time.monotonic() >= deadline:
                return claim
            time.sleep(max(0.001, poll_seconds))

    @staticmethod
    def _row_to_claim(
        row: sqlite3.Row,
        *,
        owner: bool,
        owner_token: str | None,
    ) -> ForegroundSubmissionClaim:
        result: dict[str, Any] | None = None
        if row["result_json"]:
            decoded = json.loads(str(row["result_json"]))
            if isinstance(decoded, dict):
                result = decoded
        return ForegroundSubmissionClaim(
            session_id=str(row["session_id"]),
            submission_id=str(row["submission_id"]),
            status=str(row["status"]),
            owner=owner,
            claim_token=owner_token,
            job_id=str(row["job_id"]) if row["job_id"] else None,
            result=result,
            error=str(row["error_text"]) if row["error_text"] else None,
            lease_expires_at=(
                str(row["lease_expires_at"]) if row["lease_expires_at"] else None
            ),
            execution_started_at=(
                str(row["execution_started_at"])
                if row["execution_started_at"]
                else None
            ),
        )


@lru_cache(maxsize=16)
def _submission_store_for_path(path: str) -> RpgForegroundSubmissionStore:
    return RpgForegroundSubmissionStore(path)


def submission_store_for_job_store(job_store: Any) -> RpgForegroundSubmissionStore | None:
    path = getattr(job_store, "db_path", None)
    if path is None or str(path) == ":memory:":
        return None
    return _submission_store_for_path(str(Path(path)))
