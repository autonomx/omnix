"""Crash recovery for the durable coding-quality review stage.

The generic AgentRun recovery path intentionally restarts runnable parent runs.
A coding parent that is waiting on independent reviewers is different: its coarse
AgentRunStatus is ``waiting_for_children`` while the durable quality controller is
``reviewing``. If a worker dies after a reviewer terminalizes but before its
verdict is consumed, generic recovery alone cannot make progress.

This module reconciles exactly that boundary. It is deliberately idempotent:
review result ids and repair command keys are deterministic, reviewer child ids
are already deterministic in ``AgentRunService``, and all decisions are bound to
the current TaskRevision + WorkspaceState + ReviewSnapshot.
"""
from __future__ import annotations

from typing import Any

from app.persistence.unit_of_work import unit_of_work

from .coding_quality import (
    missing_final_validations,
    quality_attempt_limit,
    repair_prompt,
    required_review_count,
    review_is_acceptable,
)
from .coding_quality_repository import PostgresCodingQualityRepository
from .contracts import AgentEvent, AgentRunCommand
from .repository import PostgresAgentRunRepository


_TERMINAL = {"completed", "failed", "cancelled"}


def orphaned_quality_review_run_ids(connection: Any, workspace_id: str) -> list[str]:
    """Return review-stage parents whose owning lease is absent or expired."""

    rows = connection.execute(
        """
        SELECT run.run_id
          FROM omnix_agent_runs AS run
          JOIN omnix_agent_coding_quality_state AS quality
            ON quality.workspace_id = run.workspace_id
           AND quality.run_id = run.run_id
          LEFT JOIN omnix_agent_worker_leases AS lease
            ON lease.workspace_id = run.workspace_id
           AND lease.run_id = run.run_id
         WHERE run.workspace_id = %s
           AND run.status = 'waiting_for_children'
           AND run.desired_state = 'running'
           AND quality.stage = 'reviewing'
           AND (lease.run_id IS NULL OR lease.lease_expires_at <= CURRENT_TIMESTAMP)
         ORDER BY run.created_at, run.run_id
        """,
        (workspace_id,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def reconcile_orphaned_quality_reviews(service: Any) -> list[str]:
    """Reconcile terminal/missing reviewers for expired review-stage parents.

    The service argument is intentionally structural rather than imported to
    avoid a circular dependency on the quality-aware AgentRunService facade.
    Returns parent run ids for which a durable reconciliation action occurred.
    """

    with unit_of_work(service.database) as work:
        run_ids = orphaned_quality_review_run_ids(
            work.connection,
            service.context.workspace_id,
        )
        work.rollback()

    reconciled: list[str] = []
    launch_actions: list[tuple[str, str, int]] = []
    for run_id in run_ids:
        action = _reconcile_one(service, run_id)
        if action is None:
            continue
        reconciled.append(run_id)
        if action[0] == "launch_reviews":
            launch_actions.append((run_id, str(action[1]), int(action[2])))

    # Reviewer launch opens its own transactions/runtime sessions, so perform it
    # after releasing every reconciliation row lock. Deterministic reviewer ids
    # make duplicate supervisor races harmless.
    for parent_run_id, snapshot_id, count in launch_actions:
        service._launch_reviewer_children(parent_run_id, snapshot_id, count)
    return reconciled


def _reconcile_one(service: Any, run_id: str) -> tuple[str, str, int] | tuple[str] | None:
    with unit_of_work(service.database) as work:
        locked = work.connection.execute(
            """
            SELECT run_id
              FROM omnix_agent_runs
             WHERE workspace_id = %s AND run_id = %s
             FOR UPDATE
            """,
            (service.context.workspace_id, run_id),
        ).fetchone()
        if locked is None:
            work.rollback()
            return None

        repository = PostgresAgentRunRepository(work.connection, service.context)
        parent = repository.get_run(run_id)
        quality = PostgresCodingQualityRepository(work.connection, service.context)
        stage = quality.get_stage(run_id)
        if (
            parent is None
            or parent.status != "waiting_for_children"
            or parent.desired_state != "running"
            or stage is None
            or stage.get("stage") != "reviewing"
            or not service._quality_enabled(parent.spec)
        ):
            work.rollback()
            return None

        revision = service._current_revision(repository, run_id)
        state_id = str(stage.get("workspace_state_id") or "")
        attempt = max(1, int(stage.get("attempt") or 1))
        if revision is None or not state_id:
            _fail_closed(
                repository,
                parent,
                "quality_review_recovery_missing_revision_or_workspace_state",
            )
            work.commit()
            return ("failed",)

        state = quality.get_workspace_state(run_id, state_id)
        snapshot = quality.latest_review_snapshot(
            run_id,
            task_revision_id=revision.revision_id,
            workspace_state_id=state_id,
        )
        if state is None or snapshot is None:
            _fail_closed(
                repository,
                parent,
                "quality_review_snapshot_missing_after_recovery",
            )
            work.commit()
            return ("failed",)
        if (
            snapshot.task_revision_id != revision.revision_id
            or snapshot.workspace_state_id != state_id
        ):
            _fail_closed(
                repository,
                parent,
                "quality_review_snapshot_stale_after_recovery",
            )
            work.commit()
            return ("failed",)

        required = required_review_count(parent.spec, state)
        matching_children = [
            child
            for child in repository.list_children(run_id)
            if child.spec.profile == "coding-reviewer"
            and service._review_snapshot_id_from_child(child) == snapshot.snapshot_id
        ]

        # Persist any terminal verdict whose callback was lost with the worker.
        existing_results = quality.list_review_results(
            run_id,
            task_revision_id=revision.revision_id,
        )
        existing_keys = {
            (result.reviewer_run_id, result.review_snapshot_id)
            for result in existing_results
        }
        for child in matching_children:
            key = (child.run_id, snapshot.snapshot_id)
            if child.status not in _TERMINAL or key in existing_keys:
                continue
            result = service._review_result_from_child(repository, child, snapshot)
            quality.add_review_result(result)
            repository.append_event(
                AgentEvent(
                    run_id=run_id,
                    event_type="quality.review_completed",
                    payload={
                        "reviewer_run_id": child.run_id,
                        "review_snapshot_id": snapshot.snapshot_id,
                        "verdict": result.verdict,
                        "findings": [item.model_dump(mode="json") for item in result.findings],
                        "missing_tests": list(result.missing_tests),
                        "task_revision_id": result.task_revision_id,
                        "workspace_state_id": result.workspace_state_id,
                        "recovered": True,
                    },
                )
            )
            existing_keys.add(key)

        # A crash may happen after the snapshot is persisted but before every
        # deterministic reviewer child is launched. Pass the full required
        # count back to the launcher: it iterates deterministic reviewer indexes
        # and skips existing ids, which correctly fills holes such as a missing
        # reviewer #1 when reviewer #0 already exists in critical mode.
        if len(matching_children) < required:
            work.commit()
            return ("launch_reviews", snapshot.snapshot_id, required)
        if any(child.status not in _TERMINAL for child in matching_children):
            work.commit()
            return ("waiting",)

        results = quality.list_review_results(
            run_id,
            task_revision_id=revision.revision_id,
        )
        current_results = [
            result
            for result in results
            if result.workspace_state_id == state_id
            and result.review_snapshot_id == snapshot.snapshot_id
        ]
        approvals = [
            result
            for result in current_results
            if review_is_acceptable(result, revision)
        ]
        if len(approvals) >= required:
            service._set_quality_stage(
                repository,
                run_id=run_id,
                stage="acceptance",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state_id,
                reason="recovered_terminal_reviewer_approval",
            )
            latest = repository.get_run(run_id) or parent
            if latest.status == "waiting_for_children":
                latest = repository.update_state(
                    run_id,
                    expected_revision=latest.revision,
                    status="running",
                    worker_id=service.worker_id,
                )
            # Reaching review required fresh self-review and validation for this
            # exact state. Final acceptance is deterministic and remains Omnix's
            # authority; it may still fail closed on non-review acceptance rules.
            service._finalize_acceptance(repository, latest)
            work.commit()
            return ("accepted",)

        if attempt >= quality_attempt_limit():
            _fail_closed(
                repository,
                parent,
                "quality_review_recovery_attempt_limit_exhausted",
            )
            work.commit()
            return ("failed",)

        latest_review = next(
            (result for result in reversed(current_results) if result.verdict != "approve"),
            current_results[-1] if current_results else None,
        )
        validations = quality.list_validation_results(
            run_id,
            task_revision_id=revision.revision_id,
        )
        missing = missing_final_validations(
            revision,
            validations,
            workspace_state_id=state_id,
        )
        next_attempt = attempt + 1
        prompt = repair_prompt(
            revision,
            latest_review,
            missing,
            attempt=next_attempt,
        )
        prompt += (
            "\nThis repair was durably recovered after the prior quality worker "
            "stopped before consuming the independent review verdict."
        )
        service._set_quality_stage(
            repository,
            run_id=run_id,
            stage="repairing",
            attempt=next_attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=state_id,
            reason="recovered_terminal_reviewer_requires_repair",
        )
        repository.append_event(
            AgentEvent(
                run_id=run_id,
                event_type="quality.repair_requested",
                payload={
                    "attempt": next_attempt,
                    "failures": ["quality_independent_review_missing_or_not_approved"],
                    "task_revision_id": revision.revision_id,
                    "workspace_state_id": state_id,
                    "recovered": True,
                },
            )
        )
        command_key = (
            f"quality-recovery-repair:{run_id}:{revision.revision_id}:"
            f"{state_id}:{next_attempt}"
        )
        repository.enqueue_command(
            AgentRunCommand(
                run_id=run_id,
                command_type="resume",
                payload={"message": prompt},
                idempotency_key=command_key,
            )
        )
        latest = repository.get_run(run_id) or parent
        repository.update_state(
            run_id,
            expected_revision=latest.revision,
            status="running",
            desired_state="running",
            last_error=None,
        )
        # Make the now-runnable parent immediately eligible for the existing
        # generic orphan recovery path in this same supervisor iteration.
        work.connection.execute(
            """
            DELETE FROM omnix_agent_worker_leases
             WHERE workspace_id = %s AND run_id = %s
            """,
            (service.context.workspace_id, run_id),
        )
        work.commit()
        return ("repair",)


def _fail_closed(repository: PostgresAgentRunRepository, parent: Any, reason: str) -> None:
    latest = repository.get_run(parent.run_id) or parent
    repository.update_state(
        parent.run_id,
        expected_revision=latest.revision,
        status="failed",
        desired_state="cancelled",
        last_error=reason[:2000],
    )
