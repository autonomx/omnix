"""Full PostgreSQL compatibility facade for the shared job runtime."""

from __future__ import annotations

from typing import Any

from app.jobs.models import (
    CancelJobRequest,
    CompleteJobRequest,
    FailJobRequest,
    JobEventRecord,
    JobProgress,
    JobRecord,
    JobStatus,
)

from .job_compat import PostgresJobStoreAdapter as _PostgresJobStoreAdapter
from .unit_of_work import unit_of_work
from .chat_execution import ChatExecutionTransactions


class PostgresJobStoreAdapter(ChatExecutionTransactions, _PostgresJobStoreAdapter):
    """Preserve the current JobStore API over PostgreSQL authority."""

    def require_chat_execution_owner(self, job_id: str):
        current = self.get_job(job_id)
        if current is None or current.type != "chat.generate":
            return
        owner = getattr(self, "chat_execution_owner", None)
        if owner is None or owner.node_id != current.compat.get("execution_owner"):
            from .execution_repositories import JobClaimConflict
            raise JobClaimConflict("Chat execution belongs to a different gateway")
        with self.database.connection() as connection:
            owner.require_live(connection)

    def iter_recoverable_chat_jobs(self, *, batch_size: int = 100):
        cursor = None
        while True:
            with unit_of_work(self.database) as work:
                records = work.jobs.list_recoverable_chat_jobs(
                    self.context, limit=batch_size,
                    after_created_at=cursor[0] if cursor else None,
                    after_id=cursor[1] if cursor else None,
                )
                work.rollback()
            if not records:
                return
            # Advance using immutable creation order even when recovery changes status.
            cursor = (records[-1]["created_at"], records[-1]["id"])
            for record in records:
                yield self._record(record)

    def recover_chat_job(self, job_id: str) -> JobRecord | None:
        with unit_of_work(self.database) as work:
            record = work.jobs.recover_chat_job(self.context, job_id=job_id)
            if record is None:
                work.rollback()
                return None
            payload = record.get("input_payload") or {}
            metadata = {"generation_status": record["status"]}
            if record["error"]:
                metadata["generation_error"] = record["error"]["message"]
            work.connection.execute(
                "UPDATE omnix_chat_messages SET metadata = metadata || %s::jsonb "
                "WHERE workspace_id = %s AND session_id = %s AND id = %s AND role = 'user'",
                (self._json(metadata), self.context.workspace_id,
                 payload.get("session_id"), payload.get("message_id")),
            )
            work.commit()
        return self._record(record)

    def complete_job(
        self,
        job_id: str,
        request: CompleteJobRequest,
    ) -> JobRecord | None:
        current = self.get_job(job_id)
        if current is None:
            return None
        if current.status == JobStatus.COMPLETED:
            return current
        return super().complete_job(job_id, request)

    def fail_job(
        self,
        job_id: str,
        request: FailJobRequest,
    ) -> JobRecord | None:
        current = self.get_job(job_id)
        if current is None:
            return None
        if current.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
            return current
        return super().fail_job(job_id, request)

    def cancel_job(
        self,
        job_id: str,
        request: CancelJobRequest,
    ) -> JobRecord | None:
        current = self.get_job(job_id)
        if current is None:
            return None
        if current.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
            return current
        return self.request_cancel(job_id, request)

    def update_progress(
        self,
        job_id: str,
        progress: JobProgress | None = None,
        *,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
        stage_id: str | None = None,
        stage_status: JobStatus = JobStatus.RUNNING,
    ) -> JobRecord | None:
        value = progress or JobProgress(
            current=max(0, int(current or 0)),
            total=max(1, int(total or 1)),
            message=message,
        )
        updated = super().update_progress(job_id, value)
        if not stage_id:
            return updated
        record = updated or self.get_job(job_id)
        if record is None:
            return None
        stages = [
            stage.model_copy(
                update={
                    "status": stage_status,
                    "progress": JobProgress(
                        current=1 if stage_status == JobStatus.COMPLETED else 0,
                        total=1,
                        message=message if message is not None else value.message,
                    ),
                }
            )
            if stage.id == stage_id
            else stage
            for stage in record.stages
        ]
        return self.update_job_stages(job_id, stages) or record

    def latest_event_id(self) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(id), 0) FROM omnix_job_events WHERE workspace_id = %s",
                (self.context.workspace_id,),
            ).fetchone()
        return int(row[0])

    def list_events(
        self,
        after_id: int | str = 0,
        limit: int = 100,
    ) -> list[JobEventRecord]:
        job_id = after_id if isinstance(after_id, str) else None
        threshold = 0 if job_id is not None else max(0, int(after_id))
        parameters: list[Any] = [self.context.workspace_id]
        clauses = ["workspace_id = %s"]
        if job_id is not None:
            clauses.append("job_id = %s")
            parameters.append(job_id)
        else:
            clauses.append("id > %s")
            parameters.append(threshold)
        parameters.append(max(1, min(int(limit), 1000)))
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id, job_id, event_type, payload, created_at "
                "FROM omnix_job_events WHERE "
                + " AND ".join(clauses)
                + " ORDER BY id ASC LIMIT %s",
                tuple(parameters),
            ).fetchall()
        return [
            JobEventRecord(
                id=int(row[0]),
                job_id=str(row[1]),
                event_type=str(row[2]),
                payload=dict(row[3]),
                created_at=row[4].isoformat(),
            )
            for row in rows
        ]
