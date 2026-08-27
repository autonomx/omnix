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


class PostgresJobStoreAdapter(_PostgresJobStoreAdapter):
    """Preserve the current JobStore API over PostgreSQL authority."""

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
