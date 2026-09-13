"""Crash-safe reconciliation for the durable independent-review stage.

Reviewer reconciliation is intentionally broader than orphan recovery now. Every
supervisor pass may inspect review-stage parents because review attempt/result
identity is deterministic and idempotent. This closes both crash windows and the
normal runtime/protocol retry path without teaching a failed first edit or a dead
reviewer how to recover.
"""
from __future__ import annotations

import os
import threading
from typing import Any

from app.persistence.unit_of_work import unit_of_work

from .coding_quality_repository import PostgresCodingQualityRepository
from .debug_logging import log_agent_activity
from .repository import AgentLeaseConflict, PostgresAgentRunRepository
from .review_orchestration import (
    reconcile_review_progress_in_repository,
    review_snapshot_id_from_child,
)
from .review_runtime import latest_reviewer_text, review_payload_is_protocol_valid

_TERMINAL = {"completed", "failed", "cancelled"}


def _lease_heartbeat_interval_seconds() -> float:
    raw = str(os.environ.get("OMNIX_AGENT_LEASE_HEARTBEAT_INTERVAL_SECONDS", "20") or "20").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 20.0
    return max(5.0, min(value, 60.0))


def _lease_heartbeat_ttl_seconds() -> int:
    raw = str(os.environ.get("OMNIX_AGENT_LEASE_HEARTBEAT_TTL_SECONDS", "90") or "90").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 90
    interval = _lease_heartbeat_interval_seconds()
    return max(int(interval * 3), min(max(value, 30), 300))


def _owned_active_run_ids(service: Any) -> list[str]:
    """Read lease-renewal targets without taking the service runtime lock."""

    with unit_of_work(service.database) as work:
        rows = work.connection.execute(
            """
            SELECT run_id
              FROM omnix_agent_runs
             WHERE workspace_id = %s AND worker_id = %s
               AND status NOT IN ('completed','failed','cancelled')
             ORDER BY created_at, run_id
            """,
            (service.context.workspace_id, service.worker_id),
        ).fetchall()
        work.rollback()
    return [str(row[0]) for row in rows]


def _renew_owned_leases(service: Any) -> None:
    """Renew worker leases independently from progress/review supervision.

    Review snapshot materialization and other exact-state quality work can be
    intentionally expensive and may run while the main supervisor is blocked on
    the service runtime lock. Lease renewal is pure liveness bookkeeping, so it
    must not share that critical path. Ownership rules remain unchanged:
    ``heartbeat`` still calls ``renew_lease`` and therefore fails if the lease
    expired or another worker acquired it.
    """

    ttl_seconds = _lease_heartbeat_ttl_seconds()
    try:
        run_ids = _owned_active_run_ids(service)
    except Exception as exc:
        log_agent_activity(
            "service.lease_heartbeat.discovery_failed",
            category="recovery",
            level="error",
            fields={"worker_id": getattr(service, "worker_id", None)},
            error=exc,
            include_traceback=True,
        )
        return

    for run_id in run_ids:
        try:
            service.heartbeat(run_id, ttl_seconds=ttl_seconds)
        except AgentLeaseConflict as exc:
            # The independent heartbeat never reacquires ownership. If another
            # worker won the lease (or this owner genuinely let it expire), stop
            # the stale local runtime immediately and leave recovery to the
            # durable ownership protocol.
            log_agent_activity(
                "service.lease_heartbeat.lease_lost",
                category="recovery",
                level="warning",
                run_id=run_id,
                fields={"worker_id": getattr(service, "worker_id", None)},
                error=exc,
            )
            try:
                service.runtime.close_run(run_id)
            except Exception:
                pass
        except Exception as exc:
            # A transient database failure is not ownership loss. The next
            # independent heartbeat and the existing supervisor are both safe
            # retry paths.
            log_agent_activity(
                "service.lease_heartbeat.failed",
                category="recovery",
                level="error",
                run_id=run_id,
                fields={"worker_id": getattr(service, "worker_id", None)},
                error=exc,
                include_traceback=True,
            )


def _lease_heartbeat_loop(service: Any) -> None:
    stop = getattr(service, "_supervisor_stop", None)
    if stop is None or not hasattr(stop, "wait") or not hasattr(stop, "is_set"):
        return
    interval = _lease_heartbeat_interval_seconds()
    while not stop.is_set():
        _renew_owned_leases(service)
        stop.wait(interval)


def _ensure_independent_lease_heartbeat(service: Any) -> None:
    """Start one liveness-only heartbeat loop for the quality-aware service."""

    if getattr(service, "_quality_lease_heartbeat_started", False):
        return
    stop = getattr(service, "_supervisor_stop", None)
    if stop is None or not hasattr(stop, "wait") or not hasattr(stop, "is_set"):
        return
    service._quality_lease_heartbeat_started = True
    threading.Thread(
        target=_lease_heartbeat_loop,
        args=(service,),
        name="omnix-agent-lease-heartbeat",
        daemon=True,
    ).start()


def orphaned_quality_review_run_ids(connection: Any, workspace_id: str) -> list[str]:
    """Return parents whose durable quality protocol still needs reconciliation.

    Historical callers know this function by its orphan-recovery name, but it is
    now also the normal supervisor reconciliation source. Besides active review
    waits, include a durably-entered acceptance stage so a process crash between
    reviewer approval and final acceptance cannot leave a run stranded forever.
    """

    rows = connection.execute(
        """
        SELECT run.run_id
          FROM omnix_agent_runs AS run
          JOIN omnix_agent_coding_quality_state AS quality
            ON quality.workspace_id = run.workspace_id
           AND quality.run_id = run.run_id
         WHERE run.workspace_id = %s
           AND run.desired_state = 'running'
           AND (
                (run.status = 'waiting_for_children' AND quality.stage = 'reviewing')
                OR
                (run.status = 'running' AND quality.stage = 'acceptance')
           )
         ORDER BY run.created_at, run.run_id
        """,
        (workspace_id,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _promote_protocol_complete_reviewers(service: Any, parent_run_id: str) -> list[str]:
    """Terminalize reviewer executions that already produced a valid verdict.

    A reviewer may have persisted its final structured ``model.message`` and then
    lose the following ``run.settled`` transaction because parent bookkeeping
    raised. Treat the protocol-valid final message as sufficient execution
    evidence to recover the reviewer as completed; otherwise the generic stalled
    run supervisor can incorrectly restart an already-finished reviewer.

    This promotion deliberately happens *before* taking the parent reconciliation
    row lock. That preserves child->parent lock ordering used by runtime callbacks
    and avoids introducing a parent->child deadlock.
    """

    promoted: list[str] = []
    with unit_of_work(service.database) as work:
        repository = PostgresAgentRunRepository(work.connection, service.context)
        parent = repository.get_run(parent_run_id)
        if parent is None or parent.status != "waiting_for_children":
            work.rollback()
            return promoted

        quality = PostgresCodingQualityRepository(work.connection, service.context)
        stage = quality.get_stage(parent_run_id) or {}
        if str(stage.get("stage") or "") != "reviewing":
            work.rollback()
            return promoted
        revision = service._current_revision(repository, parent_run_id)
        state_id = str(stage.get("workspace_state_id") or "")
        if revision is None or not state_id:
            work.rollback()
            return promoted
        snapshot = quality.latest_review_snapshot(
            parent_run_id,
            task_revision_id=revision.revision_id,
            workspace_state_id=state_id,
        )
        if snapshot is None:
            work.rollback()
            return promoted

        for child in repository.list_children(parent_run_id):
            if (
                child.spec.profile != "coding-reviewer"
                or child.status in _TERMINAL
                or review_snapshot_id_from_child(child) != snapshot.snapshot_id
            ):
                continue
            text = latest_reviewer_text(
                repository.list_events(child.run_id, after_sequence=0, limit=5000)
            )
            get_attempt = getattr(quality, "get_review_attempt_by_reviewer", None)
            attempt = get_attempt(child.run_id) if callable(get_attempt) else None
            require_path_claims = bool(
                attempt is not None
                and attempt.protocol_version == "review-v3-subject-attribution"
            )
            if not review_payload_is_protocol_valid(
                text,
                revision,
                require_path_claims=require_path_claims,
            ):
                continue
            repository.update_state(
                child.run_id,
                expected_revision=child.revision,
                status="completed",
                last_error=None,
            )
            promoted.append(child.run_id)

        if promoted:
            work.commit()
        else:
            work.rollback()

    for child_run_id in promoted:
        try:
            service._close_terminal_runtime(child_run_id)
        except Exception:
            pass
    return promoted


def reconcile_orphaned_quality_reviews(service: Any) -> list[str]:
    """Consume terminal reviewer attempts and launch deterministic retries.

    Runtime/protocol failures remain ReviewAttempt evidence and never consume an
    implementation quality attempt. Substantive review findings are reconciled by
    the shared orchestration helper and may request the normal repair loop.
    Protocol-valid reviewer output is promoted to terminal execution before
    reconciliation so a lost settle/bookkeeping transaction cannot resurrect it.
    """

    # Lease liveness must not be serialized behind review snapshot creation,
    # validation, or the service runtime lock. Start the independent loop from
    # the quality-aware supervisor hook before doing reconciliation work.
    _ensure_independent_lease_heartbeat(service)

    with unit_of_work(service.database) as work:
        run_ids = orphaned_quality_review_run_ids(
            work.connection,
            service.context.workspace_id,
        )
        work.rollback()

    reconciled: list[str] = []
    launch_actions: list[tuple[str, str, int]] = []
    for run_id in run_ids:
        _promote_protocol_complete_reviewers(service, run_id)
        with unit_of_work(service.database) as work:
            # Normal reviewer callbacks may be finishing the same parent. Do not
            # wait into the database lock timeout; skip this supervisor pass and
            # let the next idempotent pass reconcile it.
            locked = work.connection.execute(
                """
                SELECT run_id
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND run_id = %s
                 FOR UPDATE SKIP LOCKED
                """,
                (service.context.workspace_id, run_id),
            ).fetchone()
            if locked is None:
                work.rollback()
                continue
            repository = PostgresAgentRunRepository(work.connection, service.context)
            latest = repository.get_run(run_id)
            quality = PostgresCodingQualityRepository(work.connection, service.context)
            stage = quality.get_stage(run_id) or {}
            if (
                latest is not None
                and latest.status == "running"
                and latest.desired_state == "running"
                and str(stage.get("stage") or "") == "acceptance"
            ):
                # Acceptance itself is server-authoritative and idempotent under
                # this parent row lock. Re-enter it after a crash that occurred
                # after the quality stage was durably advanced.
                service._finalize_acceptance(repository, latest)
                action = None
            else:
                action = reconcile_review_progress_in_repository(
                    service,
                    repository,
                    run_id,
                )
            latest = repository.get_run(run_id)
            work.commit()
        reconciled.append(run_id)
        if action is not None and action[0] == "launch_reviews":
            launch_actions.append((run_id, str(action[1]), int(action[2])))
        # A substantive review finding may have queued the durable repair outbox.
        # Dispatch only after releasing the parent row lock/transaction.
        try:
            service._dispatch_pending_quality_commands(run_id)
        except Exception:
            pass
        if latest is not None and latest.status in {"failed", "cancelled", "completed"}:
            try:
                service._close_terminal_runtime(run_id)
            except Exception:
                pass

    for parent_run_id, snapshot_id, count in launch_actions:
        service._launch_reviewer_children(parent_run_id, snapshot_id, count)
    return reconciled
