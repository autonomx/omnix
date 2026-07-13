"""Idempotent PostgreSQL job facade for the foreground runtime."""

from __future__ import annotations

from app.jobs.models import CompleteJobRequest, FailJobRequest, JobRecord, JobStatus

from .job_compat import PostgresJobStoreAdapter as _PostgresJobStoreAdapter


class PostgresJobStoreAdapter(_PostgresJobStoreAdapter):
    """Accept terminal replay after the atomic RPG transaction commits the job."""

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
