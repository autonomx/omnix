from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from app.jobs.models import (
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
)

from .database import PostgresDatabase, default_database
from .execution_repositories import JobClaimConflict
from .identity_service import bootstrap_local_tenant
from .runtime import ensure_postgresql_runtime_ready
from .unit_of_work import unit_of_work


T = TypeVar("T")


def _model(model: type[T], values: dict[str, Any]) -> T:
    fields = getattr(model, "model_fields", {})
    payload = {key: value for key, value in values.items() if key in fields}
    return model.model_validate(payload)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresJobStoreAdapter:
    """Compatibility facade over the authoritative PostgreSQL job ledger."""

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def create_job(self, request: CreateJobRequest) -> JobRecord:
        request_payload = request.model_dump(mode="json")
        stages = request.stages or []
        metadata = dict(request_payload.get("metadata") or {})
        metadata["compat_contract"] = {
            "stages": [stage.model_dump(mode="json") for stage in stages],
            "input_ref": request_payload.get("input_ref"),
            "compat": request_payload.get("compat") or {},
            "logs": [],
            "cancel": {},
        }
        with unit_of_work(self.database) as work:
            record = work.jobs.create_job(
                self.context,
                {
                    "id": request_payload.get("id") or self._new_job_id(),
                    "owner_user_id": request_payload.get("owner_id") or self.context.user_id,
                    "module": request.module,
                    "job_type": request.type,
                    "resource_class": self._enum_value(request.resource_class),
                    "priority": request.priority,
                    "input_payload": request.input_payload or {},
                    "max_attempts": int(request_payload.get("max_attempts") or 3),
                    "metadata": metadata,
                },
            )
            work.commit()
        return self._record(record)

    def list_jobs(self, limit: int | None = None) -> list[JobRecord]:
        with unit_of_work(self.database) as work:
            records = work.jobs.list_jobs(
                self.context,
                limit=500 if limit is None else limit,
            )
            work.rollback()
        return [self._record(record) for record in records]

    def get_job(self, job_id: str) -> JobRecord | None:
        with unit_of_work(self.database) as work:
            record = work.jobs.get_job(self.context, job_id)
            work.rollback()
        return self._record(record) if record is not None else None

    def delete_job(self, job_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM omnix_jobs WHERE id = %s AND workspace_id = %s",
                (job_id, self.context.workspace_id),
            )
        return cursor.rowcount > 0

    def claim_next(
        self,
        request: ClaimJobRequest,
        *,
        residency: list[Any] | None = None,
        residency_policy: Any | None = None,
    ) -> ClaimJobResponse:
        del residency, residency_policy
        worker_id = str(
            getattr(request, "worker_id", None)
            or getattr(request, "owner_id", None)
            or "worker:local"
        )
        resource_classes = [self._enum_value(value) for value in request.resource_classes]
        lease_seconds = int(
            getattr(request, "lease_seconds", None)
            or getattr(request, "lease_duration_seconds", None)
            or 30
        )
        with unit_of_work(self.database) as work:
            record = work.jobs.claim_next(
                self.context,
                worker_id=worker_id,
                resource_classes=resource_classes,
                lease_seconds=lease_seconds,
            )
            work.commit()
        if record is None:
            return ClaimJobResponse(ok=False, reason="no_runnable_job")
        return ClaimJobResponse(ok=True, job=self._record(record))

    def renew_lease(
        self,
        job_id: str,
        *,
        worker_id: str | None = None,
        lease_token: str | None = None,
        lease_seconds: int = 30,
    ) -> JobRecord | None:
        current = self.get_job(job_id)
        if current is None:
            return None
        lease = getattr(current, "lease", None)
        owner = worker_id or self._lease_value(lease, "worker_id", "owner_id")
        token = lease_token or self._lease_value(lease, "lease_token", "token")
        if not owner or not token:
            raise JobClaimConflict(f"job has no active lease: {job_id}")
        with unit_of_work(self.database) as work:
            record = work.jobs.renew_lease(
                self.context,
                job_id=job_id,
                worker_id=owner,
                lease_token=token,
                lease_seconds=lease_seconds,
            )
            work.commit()
        return self._record(record)

    def mark_running(self, job_id: str) -> JobRecord | None:
        current = self.get_job(job_id)
        if current is None:
            return None
        if current.status == JobStatus.RUNNING:
            return current
        if self._runs_without_worker_lease(current):
            with unit_of_work(self.database) as work:
                record = work.jobs.mark_record_only_running(self.context, job_id=job_id)
                work.commit()
            return self._record(record)
        lease = getattr(current, "lease", None)
        owner = self._lease_value(lease, "worker_id", "owner_id")
        token = self._lease_value(lease, "lease_token", "token")
        if not owner or not token:
            return current
        with unit_of_work(self.database) as work:
            record = work.jobs.mark_running(
                self.context,
                job_id=job_id,
                worker_id=owner,
                lease_token=token,
            )
            work.commit()
        return self._record(record)

    def complete_job(self, job_id: str, request: CompleteJobRequest) -> JobRecord | None:
        current = self.get_job(job_id)
        if current is None:
            return None
        lease = getattr(current, "lease", None)
        owner = self._lease_value(lease, "worker_id", "owner_id")
        token = self._lease_value(lease, "lease_token", "token")
        if not owner or not token:
            if self._runs_without_worker_lease(current):
                request_payload = request.model_dump(mode="json")
                with unit_of_work(self.database) as work:
                    self._append_compat_logs(work, job_id, request_payload.get("logs") or [])
                    record = work.jobs.complete_record_only(
                        self.context,
                        job_id=job_id,
                        output_refs=request.output_refs,
                        progress={"current": 1, "total": 1, "message": "completed"},
                    )
                    work.commit()
                return self._record(record)
            raise JobClaimConflict(f"job completion requires an active lease: {job_id}")
        request_payload = request.model_dump(mode="json")
        with unit_of_work(self.database) as work:
            self._append_compat_logs(work, job_id, request_payload.get("logs") or [])
            record = work.jobs.complete(
                self.context,
                job_id=job_id,
                worker_id=owner,
                lease_token=token,
                output_refs=request.output_refs,
                progress={"current": 1, "total": 1, "message": "completed"},
            )
            work.commit()
        return self._record(record)

    def fail_job(self, job_id: str, request: FailJobRequest) -> JobRecord | None:
        current = self.get_job(job_id)
        if current is None:
            return None
        lease = getattr(current, "lease", None)
        owner = self._lease_value(lease, "worker_id", "owner_id")
        token = self._lease_value(lease, "lease_token", "token")
        if not owner or not token:
            if self._runs_without_worker_lease(current):
                payload = request.model_dump(mode="json")
                error = {
                    "code": payload.get("code") or "job_failed",
                    "message": payload.get("message") or "job failed",
                    "details": payload.get("details") or {},
                }
                with unit_of_work(self.database) as work:
                    self._append_compat_logs(work, job_id, payload.get("logs") or [])
                    record = work.jobs.fail_record_only(
                        self.context,
                        job_id=job_id,
                        error=error,
                    )
                    work.commit()
                return self._record(record)
            raise JobClaimConflict(f"job failure requires an active lease: {job_id}")
        payload = request.model_dump(mode="json")
        error = payload.get("error") or {
            "code": payload.get("code") or "job_failed",
            "message": payload.get("message") or "job failed",
        }
        with unit_of_work(self.database) as work:
            self._append_compat_logs(work, job_id, payload.get("logs") or [])
            record = work.jobs.fail(
                self.context,
                job_id=job_id,
                worker_id=owner,
                lease_token=token,
                error=error,
                retry_delay_seconds=int(payload.get("retry_delay_seconds") or 0),
            )
            work.commit()
        return self._record(record)

    def request_cancel(self, job_id: str, request: CancelJobRequest) -> JobRecord | None:
        with unit_of_work(self.database) as work:
            record = work.jobs.get_job(self.context, job_id)
            if record is None:
                work.rollback()
                return None
            updated = work.jobs.request_cancel(self.context, job_id)
            payload = request.model_dump(mode="json")
            work.connection.execute(
                """
                UPDATE omnix_jobs
                   SET metadata = jsonb_set(
                       metadata,
                       '{compat_contract,cancel}',
                       %s::jsonb,
                       TRUE
                   )
                 WHERE id = %s AND workspace_id = %s
                """,
                (
                    self._json(payload),
                    job_id,
                    self.context.workspace_id,
                ),
            )
            work.commit()
        return self._record(updated)

    def update_progress(self, job_id: str, progress: JobProgress) -> JobRecord | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                UPDATE omnix_jobs
                   SET progress = %s::jsonb, updated_at = CURRENT_TIMESTAMP
                 WHERE id = %s AND workspace_id = %s
                RETURNING id
                """,
                (
                    self._json(progress.model_dump(mode="json")),
                    job_id,
                    self.context.workspace_id,
                ),
            ).fetchone()
        return self.get_job(job_id) if row is not None else None

    def update_job_input(
        self,
        job_id: str,
        input_payload: dict[str, Any],
        *,
        compat: dict[str, Any] | None = None,
    ) -> JobRecord | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT metadata FROM omnix_jobs WHERE id = %s AND workspace_id = %s",
                (job_id, self.context.workspace_id),
            ).fetchone()
            if row is None:
                return None
            metadata = dict(row[0] or {})
            contract = dict(metadata.get("compat_contract") or {})
            if compat is not None:
                contract["compat"] = dict(compat)
            metadata["compat_contract"] = contract
            updated = connection.execute(
                """
                UPDATE omnix_jobs
                   SET input_payload = %s::jsonb,
                       metadata = %s::jsonb,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = %s AND workspace_id = %s
                RETURNING id
                """,
                (
                    self._json(input_payload),
                    self._json(metadata),
                    job_id,
                    self.context.workspace_id,
                ),
            ).fetchone()
        return self.get_job(job_id) if updated is not None else None

    def update_job_stages(self, job_id: str, stages: list[JobStage]) -> JobRecord | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT metadata FROM omnix_jobs WHERE id = %s AND workspace_id = %s",
                (job_id, self.context.workspace_id),
            ).fetchone()
            if row is None:
                return None
            metadata = dict(row[0] or {})
            contract = dict(metadata.get("compat_contract") or {})
            contract["stages"] = [stage.model_dump(mode="json") for stage in stages]
            metadata["compat_contract"] = contract
            updated = connection.execute(
                """
                UPDATE omnix_jobs
                   SET metadata = %s::jsonb,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = %s AND workspace_id = %s
                RETURNING id
                """,
                (self._json(metadata), job_id, self.context.workspace_id),
            ).fetchone()
        return self.get_job(job_id) if updated is not None else None

    def finalize_cancel(self, job_id: str, reason: str) -> JobRecord | None:
        now = _utcnow()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT metadata FROM omnix_jobs WHERE id = %s AND workspace_id = %s",
                (job_id, self.context.workspace_id),
            ).fetchone()
            if row is None:
                return None
            metadata = dict(row[0] or {})
            contract = dict(metadata.get("compat_contract") or {})
            cancel = dict(contract.get("cancel") or {})
            cancel.update(
                {
                    "requested": True,
                    "requested_at": cancel.get("requested_at") or now,
                    "acknowledged_at": now,
                    "reason": cancel.get("reason") or reason,
                }
            )
            contract["cancel"] = cancel
            metadata["compat_contract"] = contract
            updated = connection.execute(
                """
                UPDATE omnix_jobs
                   SET status = 'canceled',
                       lease_owner = NULL,
                       lease_token = NULL,
                       lease_expires_at = NULL,
                       completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                       updated_at = CURRENT_TIMESTAMP,
                       metadata = %s::jsonb
                 WHERE id = %s AND workspace_id = %s
                RETURNING id
                """,
                (self._json(metadata), job_id, self.context.workspace_id),
            ).fetchone()
        return self.get_job(job_id) if updated is not None else None

    def append_log(self, job_id: str, message: str) -> JobRecord | None:
        with unit_of_work(self.database) as work:
            record = work.jobs.get_job(self.context, job_id)
            if record is None:
                work.rollback()
                return None
            self._append_compat_logs(work, job_id, [str(message)])
            work.commit()
        return self.get_job(job_id)

    def list_events(self, job_id: str) -> list[JobEventRecord]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, job_id, event_type, payload, created_at
                  FROM omnix_job_events
                 WHERE workspace_id = %s AND job_id = %s
                 ORDER BY id ASC
                """,
                (self.context.workspace_id, job_id),
            ).fetchall()
        return [
            _model(
                JobEventRecord,
                {
                    "id": int(row[0]),
                    "job_id": str(row[1]),
                    "event_type": str(row[2]),
                    "type": str(row[2]),
                    "payload": dict(row[3]),
                    "created_at": row[4].isoformat(),
                },
            )
            for row in rows
        ]

    @staticmethod
    def _new_job_id() -> str:
        import uuid

        return f"job:{uuid.uuid4().hex}"

    @staticmethod
    def _enum_value(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _lease_value(lease: Any, *names: str) -> str | None:
        if lease is None:
            return None
        for name in names:
            value = getattr(lease, name, None)
            if value:
                return str(value)
        return None

    @staticmethod
    def _runs_without_worker_lease(job: JobRecord) -> bool:
        return job.compat.get("record_only") is True or job.compat.get("inline_execution") is True

    @staticmethod
    def _json(value: Any) -> str:
        import json

        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _append_compat_logs(self, work: Any, job_id: str, logs: list[Any]) -> None:
        if not logs:
            return
        record = work.jobs.get_job(self.context, job_id)
        if record is None:
            return
        metadata = dict(record.get("metadata") or {})
        contract = dict(metadata.get("compat_contract") or {})
        existing = [self._compat_log(item) for item in contract.get("logs") or []]
        existing.extend(self._compat_log(item) for item in logs)
        contract["logs"] = existing[-500:]
        metadata["compat_contract"] = contract
        work.connection.execute(
            "UPDATE omnix_jobs SET metadata = %s::jsonb WHERE id = %s AND workspace_id = %s",
            (self._json(metadata), job_id, self.context.workspace_id),
        )

    @staticmethod
    def _compat_log(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        return {"level": "info", "message": str(value)}

    def _record(self, value: dict[str, Any]) -> JobRecord:
        metadata = dict(value.get("metadata") or {})
        contract = dict(metadata.get("compat_contract") or {})
        stages = [JobStage.model_validate(item) for item in contract.get("stages") or []]
        progress = JobProgress.model_validate(value.get("progress") or {})
        error_value = value.get("error")
        error = None
        if error_value:
            error_payload = (
                dict(error_value)
                if isinstance(error_value, dict)
                else {"code": "job_failed", "message": str(error_value)}
            )
            error_payload.setdefault("code", "job_failed")
            error_payload.setdefault(
                "message",
                str(
                    error_payload.get("detail")
                    or error_payload.get("code")
                    or "Job failed"
                ),
            )
            error = JobError.model_validate(error_payload)
        lease = None
        if value.get("lease_token"):
            lease = _model(
                JobLease,
                {
                    "worker_id": value.get("lease_owner"),
                    "owner_id": value.get("lease_owner"),
                    "lease_token": value.get("lease_token"),
                    "token": value.get("lease_token"),
                    "claimed_at": (
                        value.get("started_at")
                        or value.get("updated_at")
                        or value.get("created_at")
                    ),
                    "expires_at": value.get("lease_expires_at"),
                },
            )
        cancel = _model(CancelState, dict(contract.get("cancel") or {}))
        resource_class = value["resource_class"]
        status = "canceled" if value["status"] == "cancelled" else value["status"]
        return _model(
            JobRecord,
            {
                "id": value["id"],
                "owner_id": value.get("owner_user_id"),
                "module": value["module"],
                "type": value["job_type"],
                "job_type": value["job_type"],
                "status": JobStatus(status),
                "resource_class": resource_class,
                "priority": value["priority"],
                "stages": stages,
                "progress": progress,
                "logs": [self._compat_log(item) for item in contract.get("logs") or []],
                "input_ref": contract.get("input_ref"),
                "input_payload": value.get("input_payload") or {},
                "output_refs": value.get("output_refs") or [],
                "error": error,
                "lease": lease,
                "created_at": value["created_at"],
                "updated_at": value["updated_at"],
                "started_at": value.get("started_at"),
                "completed_at": value.get("completed_at"),
                "cancel": cancel,
                "compat": dict(contract.get("compat") or {}),
            },
        )
