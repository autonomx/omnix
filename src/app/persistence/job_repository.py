from __future__ import annotations

import uuid
from typing import Any

from .execution_repositories import JobClaimConflict
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
_ACTIVE_CHAT_JOBS = """
jobs.job_type = 'chat.generate'
AND jobs.status IN ('queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested')
AND jobs.metadata #>> '{compat_contract,compat,inline_execution}' = 'true'
"""
_NO_LIVE_CHAT_OWNER = """
NOT EXISTS (
    SELECT 1 FROM omnix_runtime_nodes AS owner
     WHERE owner.id = jobs.metadata #>> '{compat_contract,compat,execution_owner}'
       AND owner.node_type = 'gateway'
       AND owner.metadata ->> 'workspace_id' = jobs.workspace_id
       AND owner.status IN ('active', 'draining')
       AND owner.lease_expires_at > clock_timestamp()
)
"""


class PostgresJobRepository(_BaseJobRepository):
    """Job repository with explicitly qualified durable queue operations."""

    def list_recoverable_chat_jobs(self, context: TenantContext, *, limit: int = 100,
                                  after_created_at: str | None = None,
                                  after_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"""SELECT {_QUALIFIED_JOB_COLUMNS} FROM omnix_jobs AS jobs
                 WHERE jobs.workspace_id = %s AND {_ACTIVE_CHAT_JOBS}
                   AND {_NO_LIVE_CHAT_OWNER}
                   AND (%s::timestamptz IS NULL OR (jobs.created_at, jobs.id) > (%s::timestamptz, %s))
                 ORDER BY jobs.created_at, jobs.id LIMIT %s""",
            (context.workspace_id, after_created_at, after_created_at, after_id,
             max(1, min(int(limit), 500))),
        ).fetchall()
        return [_job(row) for row in rows]

    def recover_chat_job(self, context: TenantContext, *, job_id: str) -> dict[str, Any] | None:
        """Recheck owner/status when transitioning, so only one recovery can win."""
        error = {"code": "chat_generation_failed", "retryable": True,
                 "message": "Gateway execution owner stopped or expired before Chat generation completed."}
        row = self.connection.execute(
            f"""UPDATE omnix_jobs AS jobs
                   SET status = CASE WHEN jobs.status = 'cancel_requested' THEN 'canceled' ELSE 'failed' END,
                       error = CASE WHEN jobs.status = 'cancel_requested' THEN NULL ELSE %s::jsonb END,
                       lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                       completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP,
                       metadata = CASE WHEN jobs.status = 'cancel_requested' THEN
                           jsonb_set(jobs.metadata, '{{compat_contract,cancel}}',
                               COALESCE(jobs.metadata #> '{{compat_contract,cancel}}', '{{}}'::jsonb) ||
                               jsonb_build_object('requested', TRUE, 'acknowledged_at', CURRENT_TIMESTAMP), TRUE)
                           ELSE jobs.metadata END
                 WHERE jobs.id = %s AND jobs.workspace_id = %s
                   AND {_ACTIVE_CHAT_JOBS} AND {_NO_LIVE_CHAT_OWNER}
                 RETURNING {_QUALIFIED_JOB_COLUMNS}""",
            (_json(error), job_id, context.workspace_id),
        ).fetchone()
        if row is None:
            return None
        result = _job(row)
        self.connection.execute(
            "UPDATE omnix_job_attempts SET status = %s, completed_at = CURRENT_TIMESTAMP "
            "WHERE job_id = %s AND status IN ('leased', 'running')",
            (result["status"], job_id),
        )
        self._event(context, job_id, f"job.{result['status']}", {
            "recovery": True,
            "execution_owner": (result.get("metadata") or {}).get("compat_contract", {}).get("compat", {}).get("execution_owner"),
        })
        return result

    def cancel_active_job(
        self, context: TenantContext, *, job_id: str,
    ) -> dict[str, Any]:
        """Finalize cancellation for a leased job whose work must stop now.

        The worker may still be unwinding an external provider call. Clearing
        its lease makes every subsequent durable write fail the ownership
        check, while the worker's transaction boundaries prevent partial
        chapter commits.
        """
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs AS jobs
               SET status = 'canceled', lease_owner = NULL, lease_token = NULL,
                   lease_expires_at = NULL, cancel_requested_at = COALESCE(
                       cancel_requested_at, CURRENT_TIMESTAMP),
                   completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
             WHERE jobs.id = %s AND jobs.workspace_id = %s
               AND jobs.status IN ('leased', 'running', 'cancel_requested')
            RETURNING {_QUALIFIED_JOB_COLUMNS}
            """, (job_id, context.workspace_id),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"active job cancellation rejected: {job_id}")
        result = _job(row)
        self.connection.execute(
            """UPDATE omnix_job_attempts
                  SET status = 'canceled', completed_at = CURRENT_TIMESTAMP
                WHERE job_id = %s AND status IN ('leased', 'running')""",
            (job_id,),
        )
        self._event(context, job_id, "job.canceled", {
            "attempt": result["attempt_count"], "immediate": True,
        })
        return result

    def acknowledge_cancel(
        self, context: TenantContext, *, job_id: str, worker_id: str, lease_token: str,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs AS jobs
               SET status = 'canceled', lease_owner = NULL, lease_token = NULL,
                   lease_expires_at = NULL, completed_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
             WHERE jobs.id = %s AND jobs.workspace_id = %s
               AND jobs.lease_owner = %s AND jobs.lease_token = %s
               AND jobs.status = 'cancel_requested'
            RETURNING {_QUALIFIED_JOB_COLUMNS}
            """, (job_id, context.workspace_id, worker_id, lease_token),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"job cancellation acknowledgement rejected: {job_id}")
        result = _job(row)
        self.connection.execute(
            "UPDATE omnix_job_attempts SET status = 'canceled', completed_at = CURRENT_TIMESTAMP "
            "WHERE job_id = %s AND attempt = %s AND lease_token = %s",
            (job_id, result["attempt_count"], lease_token),
        )
        self._event(context, job_id, "job.canceled", {"attempt": result["attempt_count"]})
        return result

    def create_job_once(
        self,
        context: TenantContext,
        payload: dict[str, Any],
        *,
        reconcile_queued: bool = True,
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
        if not reconcile_queued:
            existing = self.get_job(context, str(payload["id"]))
            if existing is None:
                raise RuntimeError(f"deterministic_job_identity_conflict:{payload['id']}")
            return existing, False
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
        job_types: list[str] | None = None,
        lease_seconds: int = 30,
        job_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.release_expired_leases(
            context, job_id=job_id,
            job_type=job_types[0] if job_id and job_types and len(job_types) == 1 else None,
        )
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
                   AND (%s::text IS NULL OR queued.id = %s)
                   AND queued.cancel_requested_at IS NULL
                   AND queued.status IN ('queued', 'retrying', 'waiting')
                   AND queued.available_at <= CURRENT_TIMESTAMP
                   AND queued.resource_class = ANY(%s)
                   AND (%s::text[] IS NULL OR queued.job_type = ANY(%s))
                   AND queued.attempt_count < queued.max_attempts
                   AND NOT (
                       queued.job_type = 'chat.generate'
                       AND COALESCE(queued.metadata #>> '{{compat_contract,compat,inline_execution}}', 'false') = 'true'
                   )
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
                job_id, job_id,
                resource_classes,
                job_types,
                job_types,
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
