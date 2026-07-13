from __future__ import annotations

import uuid
from typing import Any

from .execution_repositories import PostgresJobRepository as _BaseJobRepository
from .execution_repositories import _job
from .tenant import TenantContext


_QUALIFIED_JOB_COLUMNS = """
jobs.id, jobs.workspace_id, jobs.owner_user_id, jobs.module, jobs.job_type,
jobs.status, jobs.resource_class, jobs.priority, jobs.input_payload,
jobs.output_refs, jobs.progress, jobs.error, jobs.attempt_count,
jobs.max_attempts, jobs.available_at, jobs.lease_owner, jobs.lease_token,
jobs.lease_expires_at, jobs.cancel_requested_at, jobs.started_at,
jobs.completed_at, jobs.created_at, jobs.updated_at, jobs.metadata
"""


class PostgresJobRepository(_BaseJobRepository):
    """Job repository with an explicitly qualified SKIP LOCKED claim query."""

    def claim_next(
        self,
        context: TenantContext,
        *,
        worker_id: str,
        resource_classes: list[str],
        lease_seconds: int = 30,
    ) -> dict[str, Any] | None:
        self.release_expired_leases(context)
        if not resource_classes:
            return None
        lease_seconds = max(1, min(int(lease_seconds), 3600))
        token = uuid.uuid4().hex
        row = self.connection.execute(
            f"""
            WITH candidate AS (
                SELECT queued.id
                  FROM omnix_jobs AS queued
                 WHERE queued.workspace_id = %s
                   AND queued.status IN ('queued', 'retrying', 'waiting')
                   AND queued.available_at <= CURRENT_TIMESTAMP
                   AND queued.resource_class = ANY(%s)
                 ORDER BY queued.priority DESC, queued.created_at ASC, queued.id ASC
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1
            )
            UPDATE omnix_jobs AS jobs
               SET status = 'leased',
                   lease_owner = %s,
                   lease_token = %s,
                   lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                   attempt_count = jobs.attempt_count + 1,
                   started_at = COALESCE(jobs.started_at, CURRENT_TIMESTAMP),
                   updated_at = CURRENT_TIMESTAMP,
                   error = NULL
              FROM candidate
             WHERE jobs.id = candidate.id
            RETURNING {_QUALIFIED_JOB_COLUMNS}
            """,
            (
                context.workspace_id,
                resource_classes,
                worker_id,
                token,
                lease_seconds,
            ),
        ).fetchone()
        if row is None:
            return None
        result = _job(row)
        self.connection.execute(
            """
            INSERT INTO omnix_job_attempts
                (job_id, attempt, worker_id, lease_token, status)
            VALUES (%s, %s, %s, %s, 'leased')
            """,
            (result["id"], result["attempt_count"], worker_id, token),
        )
        self._event(
            context,
            result["id"],
            "job.claimed",
            {"worker_id": worker_id, "attempt": result["attempt_count"]},
        )
        return result
