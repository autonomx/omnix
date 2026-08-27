from __future__ import annotations

import json
import uuid
from typing import Any

from .errors import EntityNotFound, PersistenceError
from .tenant import TenantContext


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _job(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "workspace_id": str(row[1]),
        "owner_user_id": str(row[2]) if row[2] is not None else None,
        "module": str(row[3]),
        "job_type": str(row[4]),
        "status": str(row[5]),
        "resource_class": str(row[6]),
        "priority": int(row[7]),
        "input_payload": dict(row[8]),
        "output_refs": list(row[9]),
        "progress": dict(row[10]),
        "error": dict(row[11]) if row[11] is not None else None,
        "attempt_count": int(row[12]),
        "max_attempts": int(row[13]),
        "available_at": row[14].isoformat(),
        "lease_owner": str(row[15]) if row[15] is not None else None,
        "lease_token": str(row[16]) if row[16] is not None else None,
        "lease_expires_at": row[17].isoformat() if row[17] is not None else None,
        "cancel_requested_at": row[18].isoformat() if row[18] is not None else None,
        "started_at": row[19].isoformat() if row[19] is not None else None,
        "completed_at": row[20].isoformat() if row[20] is not None else None,
        "created_at": row[21].isoformat(),
        "updated_at": row[22].isoformat(),
        "metadata": dict(row[23]),
    }


_JOB_COLUMNS = """
id, workspace_id, owner_user_id, module, job_type, status, resource_class,
priority, input_payload, output_refs, progress, error, attempt_count,
max_attempts, available_at, lease_owner, lease_token, lease_expires_at,
cancel_requested_at, started_at, completed_at, created_at, updated_at, metadata
"""


class JobClaimConflict(PersistenceError):
    pass


class PostgresJobRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_job(self, context: TenantContext, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_jobs (
                id, workspace_id, owner_user_id, module, job_type,
                resource_class, priority, input_payload, max_attempts,
                available_at, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::jsonb
            ) RETURNING {_JOB_COLUMNS}
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
        result = _job(row)
        self._event(context, result["id"], "job.created", {"status": "queued"})
        return result

    def get_job(self, context: TenantContext, job_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_JOB_COLUMNS} FROM omnix_jobs "
            "WHERE id = %s AND workspace_id = %s",
            (job_id, context.workspace_id),
        ).fetchone()
        return _job(row) if row is not None else None

    def list_jobs(
        self,
        context: TenantContext,
        *,
        limit: int = 100,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["workspace_id = %s"]
        params: list[Any] = [context.workspace_id]
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        params.append(max(1, min(int(limit), 500)))
        rows = self.connection.execute(
            f"SELECT {_JOB_COLUMNS} FROM omnix_jobs WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, id DESC LIMIT %s",
            tuple(params),
        ).fetchall()
        return [_job(row) for row in rows]

    def release_expired_leases(self, context: TenantContext) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = CASE
                       WHEN attempt_count < max_attempts THEN 'retrying'
                       ELSE 'failed'
                   END,
                   available_at = CASE
                       WHEN attempt_count < max_attempts THEN CURRENT_TIMESTAMP
                       ELSE available_at
                   END,
                   error = jsonb_build_object('code', 'lease_expired'),
                   lease_owner = NULL,
                   lease_token = NULL,
                   lease_expires_at = NULL,
                   updated_at = CURRENT_TIMESTAMP,
                   completed_at = CASE
                       WHEN attempt_count >= max_attempts THEN CURRENT_TIMESTAMP
                       ELSE completed_at
                   END
             WHERE workspace_id = %s
               AND status IN ('leased', 'running', 'cancel_requested')
               AND lease_expires_at <= CURRENT_TIMESTAMP
            RETURNING {_JOB_COLUMNS}
            """,
            (context.workspace_id,),
        ).fetchall()
        results = [_job(row) for row in rows]
        for result in results:
            self._event(
                context,
                result["id"],
                "job.lease_expired",
                {"status": result["status"], "attempt": result["attempt_count"]},
            )
            if result["status"] == "failed":
                self.connection.execute(
                    """
                    INSERT INTO omnix_dead_letters (workspace_id, job_id, reason, payload)
                    VALUES (%s, %s, 'lease_expired', %s::jsonb)
                    """,
                    (context.workspace_id, result["id"], _json(result["error"] or {})),
                )
        return results

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
                SELECT id
                  FROM omnix_jobs
                 WHERE workspace_id = %s
                   AND status IN ('queued', 'retrying', 'waiting')
                   AND available_at <= CURRENT_TIMESTAMP
                   AND resource_class = ANY(%s)
                   AND attempt_count < max_attempts
                   AND NOT (
                       job_type = 'assistant.deep_research'
                       AND COALESCE(input_payload ->> 'awaiting_plan_approval', 'false') = 'true'
                   )
                 ORDER BY priority DESC, created_at ASC, id ASC
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1
            )
            UPDATE omnix_jobs AS jobs
               SET status = 'leased',
                   lease_owner = %s,
                   lease_token = %s,
                   lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                   attempt_count = attempt_count + 1,
                   started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                   updated_at = CURRENT_TIMESTAMP,
                   error = NULL
              FROM candidate
             WHERE jobs.id = candidate.id
            RETURNING {_JOB_COLUMNS}
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

    def renew_lease(
        self,
        context: TenantContext,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 30,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND lease_owner = %s AND lease_token = %s
               AND status IN ('leased', 'running', 'cancel_requested')
               AND lease_expires_at > CURRENT_TIMESTAMP
            RETURNING {_JOB_COLUMNS}
            """,
            (
                max(1, min(int(lease_seconds), 3600)),
                job_id,
                context.workspace_id,
                worker_id,
                lease_token,
            ),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"job lease cannot be renewed: {job_id}")
        return _job(row)

    def mark_running(
        self,
        context: TenantContext,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = 'running', updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND lease_owner = %s AND lease_token = %s
               AND status = 'leased' AND lease_expires_at > CURRENT_TIMESTAMP
            RETURNING {_JOB_COLUMNS}
            """,
            (job_id, context.workspace_id, worker_id, lease_token),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"job cannot enter running state: {job_id}")
        result = _job(row)
        self.connection.execute(
            "UPDATE omnix_job_attempts SET status = 'running' "
            "WHERE job_id = %s AND attempt = %s AND lease_token = %s",
            (job_id, result["attempt_count"], lease_token),
        )
        self._event(context, job_id, "job.running", {"worker_id": worker_id})
        return result

    def update_progress(
        self,
        context: TenantContext,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        progress: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a worker checkpoint without changing job state or ownership."""

        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET progress = %s::jsonb,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND lease_owner = %s AND lease_token = %s
               AND status IN ('leased', 'running', 'cancel_requested')
               AND lease_expires_at > CURRENT_TIMESTAMP
            RETURNING {_JOB_COLUMNS}
            """,
            (
                _json(progress),
                job_id,
                context.workspace_id,
                worker_id,
                lease_token,
            ),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"job progress update rejected: {job_id}")
        return _job(row)

    def mark_record_only_running(
        self,
        context: TenantContext,
        *,
        job_id: str,
    ) -> dict[str, Any]:
        """Start a synchronously executed audit record without a worker lease."""
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = 'running',
                   started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND status = 'queued'
               AND (
                   metadata #>> '{{compat_contract,compat,record_only}}' = 'true'
                   OR metadata #>> '{{compat_contract,compat,inline_execution}}' = 'true'
               )
            RETURNING {_JOB_COLUMNS}
            """,
            (job_id, context.workspace_id),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"record-only job cannot enter running state: {job_id}")
        result = _job(row)
        self._event(context, job_id, "job.running", {"execution": "foreground_record"})
        return result

    def complete_record_only(
        self,
        context: TenantContext,
        *,
        job_id: str,
        output_refs: list[dict[str, Any]] | list[str],
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete a foreground audit record that is never worker-claimed."""
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = 'completed', output_refs = %s::jsonb,
                   progress = %s::jsonb, error = NULL,
                   completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND status IN ('queued', 'running')
               AND (
                   metadata #>> '{{compat_contract,compat,record_only}}' = 'true'
                   OR metadata #>> '{{compat_contract,compat,inline_execution}}' = 'true'
               )
            RETURNING {_JOB_COLUMNS}
            """,
            (
                _json(output_refs),
                _json(progress or {"current": 1, "total": 1, "message": "completed"}),
                job_id,
                context.workspace_id,
            ),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"record-only job completion rejected: {job_id}")
        result = _job(row)
        self._event(context, job_id, "job.completed", {"execution": "foreground_record"})
        return result

    def fail_record_only(
        self,
        context: TenantContext,
        *,
        job_id: str,
        error: dict[str, Any],
    ) -> dict[str, Any]:
        """Fail a foreground audit record without scheduling worker retries."""
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = 'failed', error = %s::jsonb,
                   completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND status IN ('queued', 'running')
               AND (
                   metadata #>> '{{compat_contract,compat,record_only}}' = 'true'
                   OR metadata #>> '{{compat_contract,compat,inline_execution}}' = 'true'
               )
            RETURNING {_JOB_COLUMNS}
            """,
            (_json(error), job_id, context.workspace_id),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"record-only job failure rejected: {job_id}")
        result = _job(row)
        self._event(
            context,
            job_id,
            "job.failed",
            {"execution": "foreground_record", "error": error},
        )
        return result

    def complete(
        self,
        context: TenantContext,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        output_refs: list[dict[str, Any]] | list[str],
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = 'completed', output_refs = %s::jsonb,
                   progress = %s::jsonb, error = NULL,
                   lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                   completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND lease_owner = %s AND lease_token = %s
               AND status IN ('leased', 'running', 'cancel_requested')
               AND lease_expires_at > CURRENT_TIMESTAMP
            RETURNING {_JOB_COLUMNS}
            """,
            (
                _json(output_refs),
                _json(progress or {"current": 1, "total": 1, "message": "completed"}),
                job_id,
                context.workspace_id,
                worker_id,
                lease_token,
            ),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"job completion rejected: {job_id}")
        result = _job(row)
        self.connection.execute(
            """
            UPDATE omnix_job_attempts
               SET status = 'completed', completed_at = CURRENT_TIMESTAMP
             WHERE job_id = %s AND attempt = %s AND lease_token = %s
            """,
            (job_id, result["attempt_count"], lease_token),
        )
        self._event(context, job_id, "job.completed", {"attempt": result["attempt_count"]})
        return result

    def fail(
        self,
        context: TenantContext,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        error: dict[str, Any],
        retry_delay_seconds: int = 0,
    ) -> dict[str, Any]:
        current = self.get_job(context, job_id)
        if current is None:
            raise EntityNotFound(job_id)
        retry = current["attempt_count"] < current["max_attempts"]
        status = "retrying" if retry else "failed"
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = %s, error = %s::jsonb,
                   available_at = CASE WHEN %s THEN CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
                                       ELSE available_at END,
                   lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                   completed_at = CASE WHEN %s THEN NULL ELSE CURRENT_TIMESTAMP END,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
               AND lease_owner = %s AND lease_token = %s
               AND status IN ('leased', 'running', 'cancel_requested')
            RETURNING {_JOB_COLUMNS}
            """,
            (
                status,
                _json(error),
                retry,
                max(0, int(retry_delay_seconds)),
                retry,
                job_id,
                context.workspace_id,
                worker_id,
                lease_token,
            ),
        ).fetchone()
        if row is None:
            raise JobClaimConflict(f"job failure rejected: {job_id}")
        result = _job(row)
        self.connection.execute(
            """
            UPDATE omnix_job_attempts
               SET status = %s, completed_at = CURRENT_TIMESTAMP, error = %s::jsonb
             WHERE job_id = %s AND attempt = %s AND lease_token = %s
            """,
            (status, _json(error), job_id, result["attempt_count"], lease_token),
        )
        self._event(
            context,
            job_id,
            "job.retry_scheduled" if retry else "job.failed",
            {"attempt": result["attempt_count"], "error": error},
        )
        if not retry:
            self.connection.execute(
                """
                INSERT INTO omnix_dead_letters (workspace_id, job_id, reason, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (context.workspace_id, job_id, str(error.get("code") or "failed"), _json(error)),
            )
        return result

    def request_cancel(self, context: TenantContext, job_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_jobs
               SET status = CASE
                       WHEN status IN ('queued', 'retrying', 'waiting') THEN 'canceled'
                       WHEN status IN ('leased', 'running') THEN 'cancel_requested'
                       ELSE status
                   END,
                   cancel_requested_at = COALESCE(cancel_requested_at, CURRENT_TIMESTAMP),
                   completed_at = CASE
                       WHEN status IN ('queued', 'retrying', 'waiting') THEN CURRENT_TIMESTAMP
                       ELSE completed_at
                   END,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s AND workspace_id = %s
            RETURNING {_JOB_COLUMNS}
            """,
            (job_id, context.workspace_id),
        ).fetchone()
        if row is None:
            raise EntityNotFound(job_id)
        result = _job(row)
        self._event(context, job_id, "job.cancel_requested", {"status": result["status"]})
        return result

    def _event(
        self,
        context: TenantContext,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        row = self.connection.execute(
            """
            INSERT INTO omnix_job_events (workspace_id, job_id, event_type, payload)
            VALUES (%s, %s, %s, %s::jsonb) RETURNING id
            """,
            (context.workspace_id, job_id, event_type, _json(payload)),
        ).fetchone()
        return int(row[0])


class PostgresOutboxRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def append(
        self,
        context: TenantContext,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        ordering_key: str | None = None,
    ) -> int:
        row = self.connection.execute(
            """
            INSERT INTO omnix_outbox_events
                (workspace_id, aggregate_type, aggregate_id, event_type,
                 ordering_key, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb) RETURNING id
            """,
            (
                context.workspace_id,
                aggregate_type,
                aggregate_id,
                event_type,
                ordering_key,
                _json(payload),
            ),
        ).fetchone()
        return int(row[0])

    def claim_batch(
        self,
        *,
        consumer_id: str,
        limit: int = 100,
        lease_seconds: int = 30,
    ) -> list[dict[str, Any]]:
        token = uuid.uuid4().hex
        rows = self.connection.execute(
            """
            WITH candidates AS (
                SELECT id
                  FROM omnix_outbox_events
                 WHERE (
                       status IN ('pending', 'retrying')
                       AND available_at <= CURRENT_TIMESTAMP
                 ) OR (
                       status = 'claimed' AND claim_expires_at <= CURRENT_TIMESTAMP
                 )
                 ORDER BY id ASC
                 FOR UPDATE SKIP LOCKED
                 LIMIT %s
            )
            UPDATE omnix_outbox_events AS events
               SET status = 'claimed', claimed_by = %s, claim_token = %s,
                   claim_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                   attempt_count = attempt_count + 1
              FROM candidates
             WHERE events.id = candidates.id
            RETURNING events.id, events.workspace_id, events.aggregate_type,
                      events.aggregate_id, events.event_type, events.ordering_key,
                      events.payload, events.attempt_count, events.claim_token,
                      events.claim_expires_at, events.created_at
            """,
            (max(1, min(int(limit), 500)), consumer_id, token, max(1, lease_seconds)),
        ).fetchall()
        return [
            {
                "id": int(row[0]),
                "workspace_id": str(row[1]),
                "aggregate_type": str(row[2]),
                "aggregate_id": str(row[3]),
                "event_type": str(row[4]),
                "ordering_key": str(row[5]) if row[5] is not None else None,
                "payload": dict(row[6]),
                "attempt_count": int(row[7]),
                "claim_token": str(row[8]),
                "claim_expires_at": row[9].isoformat(),
                "created_at": row[10].isoformat(),
            }
            for row in rows
        ]

    def mark_published(self, *, event_id: int, claim_token: str) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE omnix_outbox_events
               SET status = 'published', published_at = CURRENT_TIMESTAMP,
                   claimed_by = NULL, claim_token = NULL, claim_expires_at = NULL,
                   last_error = NULL
             WHERE id = %s AND status = 'claimed' AND claim_token = %s
            """,
            (event_id, claim_token),
        )
        return cursor.rowcount == 1

    def mark_retry(
        self,
        *,
        event_id: int,
        claim_token: str,
        error: str,
        retry_delay_seconds: int = 0,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE omnix_outbox_events
               SET status = 'retrying',
                   available_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                   claimed_by = NULL, claim_token = NULL, claim_expires_at = NULL,
                   last_error = %s
             WHERE id = %s AND status = 'claimed' AND claim_token = %s
            """,
            (max(0, int(retry_delay_seconds)), error[:2000], event_id, claim_token),
        )
        return cursor.rowcount == 1


class PostgresForegroundSubmissionRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def claim(
        self,
        context: TenantContext,
        *,
        session_id: str,
        submission_id: str,
        lease_seconds: int = 30,
    ) -> dict[str, Any]:
        token = uuid.uuid4().hex
        lease_seconds = max(1, min(int(lease_seconds), 600))
        inserted = self.connection.execute(
            """
            INSERT INTO omnix_rpg_foreground_submissions
                (workspace_id, session_id, submission_id, claim_token, lease_expires_at)
            VALUES (%s, %s, %s, %s,
                    CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'))
            ON CONFLICT DO NOTHING
            RETURNING workspace_id, session_id, submission_id, status, claim_token,
                      job_id, interaction_id, response, error, lease_expires_at,
                      execution_started_at, created_at, updated_at
            """,
            (context.workspace_id, session_id, submission_id, token, lease_seconds),
        ).fetchone()
        owner = inserted is not None
        if inserted is None:
            reclaimed = self.connection.execute(
                """
                UPDATE omnix_rpg_foreground_submissions
                   SET claim_token = %s,
                       lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                       updated_at = CURRENT_TIMESTAMP, error = NULL
                 WHERE workspace_id = %s AND session_id = %s AND submission_id = %s
                   AND status = 'claimed' AND execution_started_at IS NULL
                   AND lease_expires_at <= CURRENT_TIMESTAMP
                RETURNING workspace_id, session_id, submission_id, status, claim_token,
                          job_id, interaction_id, response, error, lease_expires_at,
                          execution_started_at, created_at, updated_at
                """,
                (
                    token,
                    lease_seconds,
                    context.workspace_id,
                    session_id,
                    submission_id,
                ),
            ).fetchone()
            if reclaimed is not None:
                inserted = reclaimed
                owner = True
        row = inserted or self.connection.execute(
            """
            SELECT workspace_id, session_id, submission_id, status, claim_token,
                   job_id, interaction_id, response, error, lease_expires_at,
                   execution_started_at, created_at, updated_at
              FROM omnix_rpg_foreground_submissions
             WHERE workspace_id = %s AND session_id = %s AND submission_id = %s
            """,
            (context.workspace_id, session_id, submission_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("foreground submission claim was not persisted")
        return self._record(row, owner=owner, owner_token=token if owner else None)

    def attach_job(
        self,
        context: TenantContext,
        *,
        session_id: str,
        submission_id: str,
        claim_token: str,
        job_id: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE omnix_rpg_foreground_submissions
               SET job_id = %s, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND session_id = %s AND submission_id = %s
               AND claim_token = %s AND status = 'claimed'
               AND execution_started_at IS NULL
               AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (
                job_id,
                context.workspace_id,
                session_id,
                submission_id,
                claim_token,
            ),
        )
        return cursor.rowcount == 1

    def start_execution(
        self,
        context: TenantContext,
        *,
        session_id: str,
        submission_id: str,
        claim_token: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE omnix_rpg_foreground_submissions
               SET execution_started_at = COALESCE(execution_started_at, CURRENT_TIMESTAMP),
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND session_id = %s AND submission_id = %s
               AND claim_token = %s AND status = 'claimed'
               AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (context.workspace_id, session_id, submission_id, claim_token),
        )
        return cursor.rowcount == 1

    def complete(
        self,
        context: TenantContext,
        *,
        session_id: str,
        submission_id: str,
        claim_token: str,
        interaction_id: str,
        response: dict[str, Any],
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE omnix_rpg_foreground_submissions
               SET status = 'completed', interaction_id = %s,
                   response = %s::jsonb, error = NULL,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND session_id = %s AND submission_id = %s
               AND claim_token = %s AND status = 'claimed'
               AND execution_started_at IS NOT NULL
            """,
            (
                interaction_id,
                _json(response),
                context.workspace_id,
                session_id,
                submission_id,
                claim_token,
            ),
        )
        return cursor.rowcount == 1

    def fail(
        self,
        context: TenantContext,
        *,
        session_id: str,
        submission_id: str,
        claim_token: str,
        error: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE omnix_rpg_foreground_submissions
               SET status = 'failed', error = %s, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND session_id = %s AND submission_id = %s
               AND claim_token = %s AND status = 'claimed'
            """,
            (error[:2000], context.workspace_id, session_id, submission_id, claim_token),
        )
        return cursor.rowcount == 1

    @staticmethod
    def _record(row: Any, *, owner: bool, owner_token: str | None) -> dict[str, Any]:
        return {
            "workspace_id": str(row[0]),
            "session_id": str(row[1]),
            "submission_id": str(row[2]),
            "status": str(row[3]),
            "owner": owner,
            "claim_token": owner_token,
            "job_id": str(row[5]) if row[5] is not None else None,
            "interaction_id": str(row[6]) if row[6] is not None else None,
            "response": dict(row[7]) if row[7] is not None else None,
            "error": str(row[8]) if row[8] is not None else None,
            "lease_expires_at": row[9].isoformat(),
            "execution_started_at": row[10].isoformat() if row[10] is not None else None,
            "created_at": row[11].isoformat(),
            "updated_at": row[12].isoformat(),
        }
