"""Persist and hydrate the engineering fields added to canonical TaskRevision."""
from __future__ import annotations

import json
from typing import Any

from app.persistence.tenant import TenantContext

from .contracts import TaskConstraint, TaskRequirement, TaskRevision, ValidationSpec


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, list):
        value = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _retire_stale_quality_commands(
    connection: Any,
    context: TenantContext,
    revision: TaskRevision,
) -> bool:
    """Consume pending internal quality resumes from superseded task revisions.

    A quality-stage transition and its resume prompt are committed together, so
    a crash can legitimately leave the resume command pending. If the user then
    steers the run to a new TaskRevision before that command is replayed, the old
    prompt is no longer authoritative. Retire only Omnix-internal quality resumes
    and only when ``revision`` is the current latest revision; user commands and
    recovery commands without quality identity remain untouched.

    Returns whether ``revision`` is the current latest revision so the caller can
    invalidate other revision-bound authority in the same transaction without a
    second race-prone latest-revision lookup.
    """

    row = connection.execute(
        """
        SELECT revision_id
          FROM omnix_agent_task_revisions
         WHERE workspace_id = %s AND run_id = %s
         ORDER BY sequence DESC
         LIMIT 1
        """,
        (context.workspace_id, revision.run_id),
    ).fetchone()
    if row is None or str(row[0]) != revision.revision_id:
        return False
    connection.execute(
        """
        UPDATE omnix_agent_run_commands
           SET status = 'consumed', consumed_at = CURRENT_TIMESTAMP
         WHERE workspace_id = %s
           AND run_id = %s
           AND status = 'pending'
           AND command_type = 'resume'
           AND payload ? 'quality_stage'
           AND (payload ->> 'task_revision_id') IS DISTINCT FROM %s
        """,
        (context.workspace_id, revision.run_id, revision.revision_id),
    )
    return True


def _stale_superseded_planning_state(
    connection: Any,
    context: TenantContext,
    revision: TaskRevision,
) -> None:
    """Invalidate durable planning authority when user steering creates a revision.

    Planning state intentionally keeps the old ``task_revision_id`` and active
    plan lineage for auditability. The next plan inspection sees the mismatch and
    establishes a fresh baseline/state for the new authoritative TaskRevision.
    """

    connection.execute(
        """
        UPDATE omnix_agent_planning_state
           SET status = 'stale', updated_at = CURRENT_TIMESTAMP
         WHERE workspace_id = %s
           AND run_id = %s
           AND task_revision_id IS DISTINCT FROM %s
        """,
        (context.workspace_id, revision.run_id, revision.revision_id),
    )


def persist_task_revision_contract(connection: Any, context: TenantContext, revision: TaskRevision) -> None:
    connection.execute(
        """
        UPDATE omnix_agent_task_revisions
           SET requirements = %s::jsonb,
               constraints = %s::jsonb,
               validation_plan = %s::jsonb
         WHERE workspace_id = %s AND run_id = %s AND revision_id = %s
        """,
        (
            _json(revision.requirements),
            _json(revision.constraints),
            _json(revision.validation_plan),
            context.workspace_id,
            revision.run_id,
            revision.revision_id,
        ),
    )
    if _retire_stale_quality_commands(connection, context, revision):
        _stale_superseded_planning_state(connection, context, revision)


def hydrate_task_revision(connection: Any, context: TenantContext, revision: TaskRevision) -> TaskRevision:
    row = connection.execute(
        """
        SELECT requirements, constraints, validation_plan
          FROM omnix_agent_task_revisions
         WHERE workspace_id = %s AND run_id = %s AND revision_id = %s
        """,
        (context.workspace_id, revision.run_id, revision.revision_id),
    ).fetchone()
    if row is None:
        return revision
    payload = revision.model_dump(mode="python")
    payload.update(
        {
            "requirements": [TaskRequirement.model_validate(item) for item in list(row[0] or [])],
            "constraints": [TaskConstraint.model_validate(item) for item in list(row[1] or [])],
            "validation_plan": [ValidationSpec.model_validate(item) for item in list(row[2] or [])],
        }
    )
    return TaskRevision.model_validate(payload)


def hydrate_task_revisions(connection: Any, context: TenantContext, revisions: list[TaskRevision]) -> list[TaskRevision]:
    return [hydrate_task_revision(connection, context, revision) for revision in revisions]
