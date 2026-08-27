from __future__ import annotations

import uuid
from typing import Any

from .execution_repositories import PostgresJobRepository as _BaseJobRepository
from .execution_repositories import _job, _json
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
    """Job repository with explicitly qualified durable queue operations."""

    def create_job_once(
        self,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Create one deterministic job identity or reconcile a stronger queued signal."""

        row = self.connection.execute(
            f"""
            INSERT INTO omnix_jobs AS jobs (
                id, workspace_id, owner_user_id, module, job_type,
                resource_class, priority, input_payload, max_attempts,
                available_at, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::jsonb
            )
            ON CONFLICT (id) DO NOTHING
            RETURNING {_QUALIFIED_JOB_COLUMNS}
            """,
            (
                payload["id"],
                context.workspace_id,
                payload.get("owner_user_id") or context.user_id,
                payload["module"],
                payload["job_type"],
                payload["resource_class"],
                int(payload.get("priority", 0)),
                _json(payload.get("input_payload") or {}),
                max(1, int(payload.get("max_attempts", 3))),
                payload.get("available_at"),
                _json(payload.get("metadata") or {}),
            ),
        ).fetchone()
        if row is not None:
            result = _job(row)
            self._event(context, result["id"], "job.created", {"status": "queued"})
            return result, True
        updated = self.connection.execute(
            f"""
            UPDATE omnix_jobs AS jobs
               SET priority = GREATEST(jobs.priority, %s),
                   input_payload = %s::jsonb,
                   metadata = %s::jsonb,
                   max_attempts = GREATEST(jobs.max_attempts, %s),
                   updated_at = CURRENT_TIMESTAMP
             WHERE jobs.id = %s AND jobs.workspace_id = %s
               AND jobs.status IN ('queued', 'waiting', 'retrying')
            RETURNING {_QUALIFIED_JOB_COLUMNS}
            """,
            (
                int(payload.get("priority", 0)),
                _json(payload.get("input_payload") or {}),
                _json(payload.get("metadata") or {}),
                max(1, int(payload.get("max_attempts", 3))),
                payload["id"],
                context.workspace_id,
            ),
        ).fetchone()
        if updated is not None:
            result = _job(updated)
            self._event(
                context,
                result["id"],
                "job.signal_reconciled",
                {"priority": result["priority"], "status": result["status"]},
            )
            return result, False
        existing = self.get_job(context, str(payload["id"]))
        if existing is None:
            raise RuntimeError(f"deterministic_job_identity_conflict:{payload['id']}")
        return existing, False

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
                   AND queued.attempt_count < queued.max_attempts
                   AND NOT (
                       queued.job_type = 'assistant.deep_research'
                       AND COALESCE(queued.input_payload ->> 'awaiting_plan_approval', 'false') = 'true'
                   )
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
            ON CONFLICT (job_id, attempt) DO UPDATE
               SET worker_id = EXCLUDED.worker_id,
                   lease_token = EXCLUDED.lease_token,
                   status = 'leased',
                   started_at = CURRENT_TIMESTAMP,
                   completed_at = NULL,
                   error = NULL
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
