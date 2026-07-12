"""Durable cross-process ownership for foreground RPG submissions."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

_STATUS_CLAIMED = "claimed"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, submission_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rpg_foreground_submission_status
                ON rpg_foreground_submissions(status, updated_at)
                """
            )

    def claim(self, session_id: str, submission_id: str) -> ForegroundSubmissionClaim:
        token = uuid.uuid4().hex
        now = _utcnow()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO rpg_foreground_submissions (
                    session_id, submission_id, status, claim_token,
                    job_id, result_json, error_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (session_id, submission_id, _STATUS_CLAIMED, token, now, now),
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

    def attach_job(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        job_id: str,
    ) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rpg_foreground_submissions
                SET job_id = ?, updated_at = ?
                WHERE session_id = ? AND submission_id = ?
                  AND claim_token = ? AND status = ?
                """,
                (
                    job_id,
                    _utcnow(),
                    session_id,
                    submission_id,
                    claim_token,
                    _STATUS_CLAIMED,
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
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rpg_foreground_submissions
                SET status = ?, result_json = ?, error_text = NULL, updated_at = ?
                WHERE session_id = ? AND submission_id = ?
                  AND claim_token = ? AND status = ?
                """,
                (
                    _STATUS_COMPLETED,
                    encoded,
                    _utcnow(),
                    session_id,
                    submission_id,
                    claim_token,
                    _STATUS_CLAIMED,
                ),
            )
        return cursor.rowcount == 1

    def fail(
        self,
        session_id: str,
        submission_id: str,
        claim_token: str,
        error: str,
    ) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rpg_foreground_submissions
                SET status = ?, error_text = ?, updated_at = ?
                WHERE session_id = ? AND submission_id = ?
                  AND claim_token = ? AND status = ?
                """,
                (
                    _STATUS_FAILED,
                    str(error)[:1000],
                    _utcnow(),
                    session_id,
                    submission_id,
                    claim_token,
                    _STATUS_CLAIMED,
                ),
            )
        return cursor.rowcount == 1

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
            if claim.status in {_STATUS_COMPLETED, _STATUS_FAILED}:
                return claim
            if time.monotonic() >= deadline:
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
        raw_result = row["result_json"]
        if raw_result:
            decoded = json.loads(str(raw_result))
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
        )


@lru_cache(maxsize=16)
def _submission_store_for_path(path: str) -> RpgForegroundSubmissionStore:
    return RpgForegroundSubmissionStore(path)


def submission_store_for_job_store(job_store: Any) -> RpgForegroundSubmissionStore | None:
    path = getattr(job_store, "db_path", None)
    if path is None or str(path) == ":memory:":
        return None
    return _submission_store_for_path(str(Path(path)))
