"""SQLite-backed local job store and conservative scheduler."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.runtime_paths import resources_data_root

from .models import (
    CancelJobRequest,
    CancelState,
    ClaimJobRequest,
    ClaimJobResponse,
    CompleteJobRequest,
    CreateJobRequest,
    FailJobRequest,
    JobError,
    JobEventRecord,
    JobLease,
    JobProgress,
    JobRecord,
    JobStage,
    JobStatus,
    ResourceClass,
    TERMINAL_STATUSES,
)


RUNNABLE_STATUSES = {JobStatus.QUEUED, JobStatus.RETRYING, JobStatus.WAITING}
ACTIVE_STATUSES = {JobStatus.LEASED, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _default_stage(request: CreateJobRequest) -> JobStage:
    return JobStage(
        id="run",
        label=request.type,
        resource_class=request.resource_class,
    )


def default_job_db_path() -> Path:
    override = os.environ.get("OMNIX_JOBS_DB_PATH")
    if override:
        return Path(override)
    return resources_data_root() / "omnix_jobs.sqlite"


class SQLiteJobStore:
    """Durable local store for shared jobs.

    The store is intentionally synchronous and small. Phase 8 uses it as the
    durable adapter behind gateway APIs before model-heavy execution is moved
    into workers.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_job_db_path()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        """Queue cross-process writers before any transaction reads occur."""

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            if self.db_path != Path(":memory:"):
                conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    module TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resource_class TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    stages_json TEXT NOT NULL,
                    progress_json TEXT NOT NULL,
                    logs_json TEXT NOT NULL,
                    input_ref_json TEXT,
                    input_payload_json TEXT,
                    output_refs_json TEXT NOT NULL,
                    error_json TEXT,
                    lease_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancel_json TEXT NOT NULL,
                    compat_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_rpg_submission
                ON jobs(
                    type,
                    json_extract(input_ref_json, '$.session_id'),
                    json_extract(input_payload_json, '$.submission_id')
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id)")

    def create_job(self, request: CreateJobRequest) -> JobRecord:
        now = _utcnow()
        stages = request.stages or [_default_stage(request)]
        job = JobRecord(
            id=f"job:{uuid.uuid4().hex}",
            owner_id=request.owner_id,
            module=request.module,
            type=request.type,
            status=JobStatus.QUEUED,
            resource_class=request.resource_class,
            priority=request.priority,
            stages=stages,
            progress=JobProgress(),
            logs=[],
            input_ref=request.input_ref,
            input_payload=request.input_payload,
            output_refs=[],
            error=None,
            lease=None,
            created_at=now,
            updated_at=now,
            cancel=CancelState(),
            compat=request.compat,
        )
        with self._write_connection() as conn:
            self._insert_job(conn, job)
            self._append_event(conn, job.id, "job.created", job.model_dump(mode="json"))
        return job

    def list_jobs(self, limit: int | None = None) -> list[JobRecord]:
        query = "SELECT * FROM jobs ORDER BY created_at DESC, id DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (max(0, limit),)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def find_job_by_submission(
        self,
        *,
        job_type: str,
        session_id: str,
        submission_id: str,
    ) -> JobRecord | None:
        """Return one RPG job without scanning and decoding the full job table."""

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE type = ?
                  AND json_extract(input_ref_json, '$.session_id') = ?
                  AND json_extract(input_payload_json, '$.submission_id') = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (job_type, session_id, submission_id),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def delete_job(self, job_id: str) -> bool:
        """Delete one job and its event rows from the local job store."""

        with self._write_connection() as conn:
            conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount > 0

    def claim_next(
        self,
        request: ClaimJobRequest,
        *,
        residency: list[Any] | None = None,
        residency_policy: Any | None = None,
    ) -> ClaimJobResponse:
        from .residency import ResidencyDecisionAction, gpu_residency_request_from_job, plan_model_residency

        now = datetime.now(timezone.utc)
        allowed = {resource.value for resource in request.resource_classes}
        residency_records = residency
        with self._write_connection() as conn:
            self._release_expired_leases(conn, now)
            active_jobs = [
                self._row_to_job(row)
                for row in conn.execute(
                    "SELECT * FROM jobs WHERE status IN (?,?,?)",
                    tuple(status.value for status in ACTIVE_STATUSES),
                ).fetchall()
            ]
            active_gpu = any(job.resource_class.value.startswith("gpu:") for job in active_jobs)
            active_cpu = sum(1 for job in active_jobs if job.resource_class == ResourceClass.CPU)
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status IN (?,?,?)
                ORDER BY priority DESC, created_at ASC, id ASC
                """,
                tuple(status.value for status in RUNNABLE_STATUSES),
            ).fetchall()

            for row in rows:
                job = self._row_to_job(row)
                if allowed and job.resource_class.value not in allowed:
                    continue
                residency_decision = None
                if residency_records is not None:
                    residency_request = gpu_residency_request_from_job(job)
                    if residency_request is not None:
                        residency_decision = plan_model_residency(residency_request, residency_records, residency_policy)
                        if residency_decision.action != ResidencyDecisionAction.CAN_RUN:
                            continue
                can_share_active_gpu = bool(
                    residency_decision is not None
                    and residency_policy is not None
                    and getattr(residency_policy, "allow_co_residency", False)
                )
                if job.resource_class.value.startswith("gpu:") and active_gpu and not can_share_active_gpu:
                    continue
                if job.resource_class == ResourceClass.CPU and active_cpu >= request.cpu_limit:
                    continue

                claimed = self._claim_job(conn, job, request, now)
                return ClaimJobResponse(ok=True, job=claimed)

        return ClaimJobResponse(ok=False, reason="no_runnable_job")

    def complete_job(self, job_id: str, request: CompleteJobRequest) -> JobRecord | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        now = _utcnow()
        job.status = JobStatus.COMPLETED
        job.updated_at = now
        job.completed_at = now
        job.lease = None
        job.output_refs = request.output_refs
        job.logs.extend(request.logs)
        job.progress = JobProgress(current=1, total=1, message="completed")
        job.stages = [
            stage.model_copy(
                update={
                    "status": JobStatus.COMPLETED,
                    "completed_at": stage.completed_at or now,
                    "progress": JobProgress(current=1, total=1, message="completed"),
                }
            )
            for stage in job.stages
        ]
        return self._save_with_event(job, "job.completed")

    def mark_running(self, job_id: str) -> JobRecord | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        now = _utcnow()
        job.status = JobStatus.RUNNING
        job.updated_at = now
        job.started_at = job.started_at or now
        if job.stages:
            first_stage = job.stages[0]
            job.stages[0] = first_stage.model_copy(
                update={
                    "status": JobStatus.RUNNING,
                    "started_at": first_stage.started_at or now,
                    "progress": JobProgress(current=0, total=1, message="running"),
                }
            )
        return self._save_with_event(job, "job.updated")

    def update_progress(
        self,
        job_id: str,
        *,
        current: int,
        total: int,
        message: str | None = None,
        stage_id: str | None = None,
        stage_status: JobStatus = JobStatus.RUNNING,
    ) -> JobRecord | None:
        job = self.get_job(job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return job
        now = _utcnow()
        progress = JobProgress(current=max(0, current), total=max(1, total), message=message)
        job.progress = progress
        job.updated_at = now
        if job.status in {JobStatus.QUEUED, JobStatus.LEASED, JobStatus.WAITING, JobStatus.RETRYING}:
            job.status = JobStatus.RUNNING
            job.started_at = job.started_at or now
        if stage_id:
            job.stages = [
                stage.model_copy(
                    update={
                        "status": stage_status,
                        "started_at": stage.started_at or now,
                        "completed_at": now if stage_status == JobStatus.COMPLETED else stage.completed_at,
                        "progress": JobProgress(
                            current=1 if stage_status == JobStatus.COMPLETED else 0,
                            total=1,
                            message=message,
                        ),
                    }
                )
                if stage.id == stage_id
                else stage
                for stage in job.stages
            ]
        return self._save_with_event(job, "job.updated")

    def fail_job(self, job_id: str, request: FailJobRequest) -> JobRecord | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        now = _utcnow()
        job.status = JobStatus.FAILED
        job.updated_at = now
        job.completed_at = now
        job.lease = None
        job.error = JobError(
            code=request.code,
            message=request.message,
            retryable=request.retryable,
            details=request.details,
        )
        job.stages = [
            stage.model_copy(
                update={
                    "status": JobStatus.FAILED,
                    "completed_at": stage.completed_at or now,
                    "error": job.error,
                }
            )
            if stage.status in {JobStatus.RUNNING, JobStatus.LEASED}
            else stage
            for stage in job.stages
        ]
        return self._save_with_event(job, "job.failed")

    def cancel_job(self, job_id: str, request: CancelJobRequest) -> JobRecord | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        if job.status in TERMINAL_STATUSES:
            return job
        now = _utcnow()
        job.cancel = CancelState(
            requested=True,
            requested_at=now,
            acknowledged_at=now if job.status in RUNNABLE_STATUSES else None,
            reason=request.reason,
        )
        if job.status in RUNNABLE_STATUSES:
            job.status = JobStatus.CANCELED
            job.completed_at = now
            event_type = "job.canceled"
        else:
            job.status = JobStatus.CANCEL_REQUESTED
            event_type = "job.updated"
        job.updated_at = now
        return self._save_with_event(job, event_type)

    def list_events(self, after_id: int = 0, limit: int = 100) -> list[JobEventRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM job_events
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (after_id, limit),
            ).fetchall()
        return [
            JobEventRecord(
                id=int(row["id"]),
                job_id=str(row["job_id"]),
                event_type=str(row["event_type"]),
                payload=_json_loads(row["payload_json"], {}),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def _release_expired_leases(self, conn: sqlite3.Connection, now: datetime) -> None:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status IN (?,?,?)",
            tuple(status.value for status in ACTIVE_STATUSES),
        ).fetchall()
        for row in rows:
            job = self._row_to_job(row)
            expires_at = _parse_time(job.lease.expires_at if job.lease else None)
            if expires_at and expires_at <= now and job.status != JobStatus.CANCEL_REQUESTED:
                job.status = JobStatus.QUEUED
                job.lease = None
                job.updated_at = _utcnow()
                self._update_job(conn, job)
                self._append_event(conn, job.id, "job.updated", job.model_dump(mode="json"))

    def _claim_job(
        self,
        conn: sqlite3.Connection,
        job: JobRecord,
        request: ClaimJobRequest,
        now: datetime,
    ) -> JobRecord:
        claimed_at = now.isoformat()
        expires_at = (now + timedelta(seconds=request.lease_seconds)).isoformat()
        job.status = JobStatus.LEASED
        job.lease = JobLease(
            worker_id=request.worker_id,
            token=uuid.uuid4().hex,
            claimed_at=claimed_at,
            expires_at=expires_at,
        )
        job.updated_at = claimed_at
        job.started_at = job.started_at or claimed_at
        self._update_job(conn, job)
        self._append_event(conn, job.id, "job.updated", job.model_dump(mode="json"))
        return job

    def _save_with_event(self, job: JobRecord, event_type: str) -> JobRecord:
        with self._write_connection() as conn:
            self._update_job(conn, job)
            self._append_event(conn, job.id, event_type, job.model_dump(mode="json"))
        return job

    def _insert_job(self, conn: sqlite3.Connection, job: JobRecord) -> None:
        conn.execute(
            """
            INSERT INTO jobs (
                id, owner_id, module, type, status, resource_class, priority,
                stages_json, progress_json, logs_json, input_ref_json,
                input_payload_json, output_refs_json, error_json, lease_json,
                created_at, updated_at, started_at, completed_at, cancel_json,
                compat_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._job_values(job),
        )

    def _update_job(self, conn: sqlite3.Connection, job: JobRecord) -> None:
        values = self._job_values(job)
        conn.execute(
            """
            UPDATE jobs SET
                owner_id = ?, module = ?, type = ?, status = ?,
                resource_class = ?, priority = ?, stages_json = ?,
                progress_json = ?, logs_json = ?, input_ref_json = ?,
                input_payload_json = ?, output_refs_json = ?, error_json = ?,
                lease_json = ?, created_at = ?, updated_at = ?, started_at = ?,
                completed_at = ?, cancel_json = ?, compat_json = ?
            WHERE id = ?
            """,
            values[1:] + (values[0],),
        )

    def _append_event(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO job_events (job_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, event_type, _json_dumps(payload), _utcnow()),
        )

    def _job_values(self, job: JobRecord) -> tuple[Any, ...]:
        return (
            job.id,
            job.owner_id,
            job.module,
            job.type,
            job.status.value,
            job.resource_class.value,
            job.priority,
            _json_dumps([stage.model_dump(mode="json") for stage in job.stages]),
            _json_dumps(job.progress.model_dump(mode="json")),
            _json_dumps(job.logs),
            _json_dumps(job.input_ref) if job.input_ref is not None else None,
            _json_dumps(job.input_payload) if job.input_payload is not None else None,
            _json_dumps(job.output_refs),
            _json_dumps(job.error.model_dump(mode="json")) if job.error else None,
            _json_dumps(job.lease.model_dump(mode="json")) if job.lease else None,
            job.created_at,
            job.updated_at,
            job.started_at,
            job.completed_at,
            _json_dumps(job.cancel.model_dump(mode="json")),
            _json_dumps(job.compat),
        )

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=str(row["id"]),
            owner_id=row["owner_id"],
            module=str(row["module"]),
            type=str(row["type"]),
            status=JobStatus(str(row["status"])),
            resource_class=ResourceClass(str(row["resource_class"])),
            priority=int(row["priority"]),
            stages=[JobStage(**stage) for stage in _json_loads(row["stages_json"], [])],
            progress=JobProgress(**_json_loads(row["progress_json"], {})),
            logs=_json_loads(row["logs_json"], []),
            input_ref=_json_loads(row["input_ref_json"], None),
            input_payload=_json_loads(row["input_payload_json"], None),
            output_refs=_json_loads(row["output_refs_json"], []),
            error=JobError(**_json_loads(row["error_json"], {})) if row["error_json"] else None,
            lease=JobLease(**_json_loads(row["lease_json"], {})) if row["lease_json"] else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            cancel=CancelState(**_json_loads(row["cancel_json"], {})),
            compat=_json_loads(row["compat_json"], {}),
        )


def default_job_store() -> SQLiteJobStore:
    return SQLiteJobStore()
