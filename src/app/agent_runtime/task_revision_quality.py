"""Persist and hydrate the engineering fields added to canonical TaskRevision."""
from __future__ import annotations

import json
from typing import Any

from app.persistence.tenant import TenantContext

from .contracts import TaskRevision


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, list):
        value = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


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
    return revision.model_copy(
        update={
            "requirements": list(row[0] or []),
            "constraints": list(row[1] or []),
            "validation_plan": list(row[2] or []),
        }
    )


def hydrate_task_revisions(connection: Any, context: TenantContext, revisions: list[TaskRevision]) -> list[TaskRevision]:
    return [hydrate_task_revision(connection, context, revision) for revision in revisions]
