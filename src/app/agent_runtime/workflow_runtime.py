"""PostgreSQL-backed deterministic WorkflowRuntime."""
from __future__ import annotations

from functools import lru_cache
import json
import uuid
from typing import Any, Callable

from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.models import AssistantToolRequest
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .interfaces import WorkflowRuntime
from .workflows import WorkflowDefinition, WorkflowRunSnapshot, WorkflowStepDefinition


class WorkflowRuntimeError(RuntimeError):
    pass


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class PostgresWorkflowRuntime(WorkflowRuntime):
    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        capability_executor: Callable[[str, AssistantToolRequest], Any] = hermes_assistant_tool_execute_payload,
    ) -> None:
        self.database = database or default_database()
        self.context = bootstrap_local_tenant(self.database)
        self.capability_executor = capability_executor

    def register(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        with unit_of_work(self.database) as work:
            work.connection.execute(
                """
                INSERT INTO omnix_workflow_definitions (
                    workspace_id, workflow_id, version, name, definition, active
                ) VALUES (%s, %s, %s, %s, %s::jsonb, TRUE)
                ON CONFLICT (workspace_id, workflow_id, version) DO UPDATE
                   SET name = EXCLUDED.name, definition = EXCLUDED.definition
                """,
                (
                    self.context.workspace_id,
                    definition.id,
                    definition.version,
                    definition.name,
                    _json(definition),
                ),
            )
            work.commit()
        return definition

    def lookup(self, name_or_id: str) -> str | None:
        value = str(name_or_id or "").strip().casefold()
        if not value:
            return None
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                SELECT workflow_id
                  FROM omnix_workflow_definitions
                 WHERE workspace_id = %s AND active
                   AND (lower(workflow_id) = %s OR lower(name) = %s OR lower(name) LIKE %s)
                 ORDER BY version DESC
                 LIMIT 1
                """,
                (self.context.workspace_id, value, value, f"%{value}%"),
            ).fetchone()
            work.rollback()
        return str(row[0]) if row else None

    def start(self, workflow_id: str, input_payload: dict[str, object]) -> str:
        definition = self._definition(workflow_id)
        if definition is None:
            raise KeyError(workflow_id)
        run_id = uuid.uuid4().hex
        idempotency_key = str(input_payload.get("idempotency_key") or "").strip() or None
        with unit_of_work(self.database) as work:
            if idempotency_key:
                existing = work.connection.execute(
                    "SELECT run_id FROM omnix_workflow_runs WHERE workspace_id = %s AND idempotency_key = %s",
                    (self.context.workspace_id, idempotency_key),
                ).fetchone()
                if existing:
                    work.rollback()
                    return str(existing[0])
            work.connection.execute(
                """
                INSERT INTO omnix_workflow_runs (
                    workspace_id, run_id, workflow_id, workflow_version,
                    input_payload, status, current_step_id, idempotency_key
                ) VALUES (%s, %s, %s, %s, %s::jsonb, 'queued', %s, %s)
                """,
                (
                    self.context.workspace_id,
                    run_id,
                    definition.id,
                    definition.version,
                    _json(input_payload),
                    definition.steps[0].id if definition.steps else None,
                    idempotency_key,
                ),
            )
            for ordinal, step in enumerate(definition.steps):
                work.connection.execute(
                    """
                    INSERT INTO omnix_workflow_step_runs (
                        workspace_id, run_id, step_id, ordinal, status
                    ) VALUES (%s, %s, %s, %s, 'pending')
                    """,
                    (self.context.workspace_id, run_id, step.id, ordinal),
                )
            work.commit()
        self._advance(run_id)
        return run_id

    def pause(self, run_id: str) -> None:
        self._set_status(run_id, "paused")

    def resume(self, run_id: str) -> None:
        self._set_status(run_id, "running")
        self._advance(run_id)

    def cancel(self, run_id: str) -> None:
        self._set_status(run_id, "cancelled")

    def approve(self, run_id: str, step_id: str) -> None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'approved'
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                   AND status = 'waiting_for_approval'
                RETURNING step_id
                """,
                (self.context.workspace_id, run_id, step_id),
            ).fetchone()
            if row is None:
                raise WorkflowRuntimeError("workflow step is not waiting for approval")
            work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET status = 'running', revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (self.context.workspace_id, run_id),
            )
            work.commit()
        self._advance(run_id)

    def get_status(self, run_id: str) -> dict[str, object] | None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                SELECT workflow_id, workflow_version, status, current_step_id,
                       input_payload, revision
                  FROM omnix_workflow_runs
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (self.context.workspace_id, run_id),
            ).fetchone()
            work.rollback()
        if row is None:
            return None
        return WorkflowRunSnapshot(
            run_id=run_id,
            workflow_id=str(row[0]),
            workflow_version=int(row[1]),
            status=str(row[2]),
            current_step_id=str(row[3]) if row[3] else None,
            input_payload=dict(row[4] or {}),
            revision=int(row[5]),
        ).model_dump(mode="json")

    def _advance(self, run_id: str) -> None:
        while True:
            state = self.get_status(run_id)
            if state is None or state["status"] in {"paused", "cancelled", "completed", "failed", "waiting_for_approval"}:
                return
            definition = self._definition(str(state["workflow_id"]), version=int(state["workflow_version"]))
            if definition is None:
                self._set_status(run_id, "failed", error="workflow_definition_missing")
                return
            step_row = self._current_step(run_id)
            if step_row is None:
                self._set_status(run_id, "completed")
                return
            step = next(item for item in definition.steps if item.id == step_row["step_id"])
            if step.requires_approval and step_row["status"] not in {"approved", "running"}:
                self._set_step_status(run_id, step.id, "waiting_for_approval")
                self._set_status(run_id, "waiting_for_approval")
                return
            try:
                result = self._execute_step(run_id, step, state["input_payload"], approved=step_row["status"] == "approved")
            except Exception as exc:
                attempts = int(step_row["attempts"]) + 1
                if attempts <= step.retry_limit:
                    self._set_step_status(run_id, step.id, "pending", error=str(exc), attempts=attempts)
                    continue
                self._set_step_status(run_id, step.id, "failed", error=str(exc), attempts=attempts)
                self._set_status(run_id, "failed", error=str(exc))
                return
            self._set_step_status(run_id, step.id, "completed", result=result, attempts=int(step_row["attempts"]) + 1)
            self._select_next(run_id)

    def _execute_step(
        self,
        run_id: str,
        step: WorkflowStepDefinition,
        input_payload: dict[str, Any],
        *,
        approved: bool,
    ) -> dict[str, Any]:
        if step.kind == "condition":
            return {"condition": step.condition, "matched": self._condition(step.condition, input_payload)}
        if step.kind == "approval":
            return {"approved": approved}
        if not step.capability_id:
            raise WorkflowRuntimeError("capability step has no capability_id")
        namespace = step.capability_id.split(".", 1)[0]
        request = AssistantToolRequest(
            tool_id=namespace,
            action_id=step.capability_id,
            session_id=f"workflow:{run_id}",
            proposal_id=f"workflow:{run_id}:{step.id}",
            input=self._render_input(step.input_template, input_payload),
            approved=approved,
        )
        payload = self.capability_executor(f"workflow:{run_id}", request)
        execution = payload.execution_result
        if execution.error:
            raise WorkflowRuntimeError(execution.error)
        return execution.model_dump(mode="json")

    @staticmethod
    def _render_input(template: dict[str, Any], input_payload: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in template.items():
            if isinstance(value, str) and value.startswith("$input."):
                result[key] = input_payload.get(value.removeprefix("$input."))
            else:
                result[key] = value
        return result

    @staticmethod
    def _condition(expression: str | None, input_payload: dict[str, Any]) -> bool:
        if not expression:
            return True
        if "==" not in expression:
            return bool(input_payload.get(expression.removeprefix("input.")))
        left, right = [part.strip() for part in expression.split("==", 1)]
        value = input_payload.get(left.removeprefix("input."))
        return str(value).casefold() == right.strip("'\"").casefold()

    def _definition(self, workflow_id: str, *, version: int | None = None) -> WorkflowDefinition | None:
        with unit_of_work(self.database) as work:
            if version is None:
                row = work.connection.execute(
                    """
                    SELECT definition FROM omnix_workflow_definitions
                     WHERE workspace_id = %s AND workflow_id = %s AND active
                     ORDER BY version DESC LIMIT 1
                    """,
                    (self.context.workspace_id, workflow_id),
                ).fetchone()
            else:
                row = work.connection.execute(
                    """
                    SELECT definition FROM omnix_workflow_definitions
                     WHERE workspace_id = %s AND workflow_id = %s AND version = %s
                    """,
                    (self.context.workspace_id, workflow_id, version),
                ).fetchone()
            work.rollback()
        return WorkflowDefinition.model_validate(row[0]) if row else None

    def _current_step(self, run_id: str) -> dict[str, Any] | None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                SELECT step_id, status, attempts FROM omnix_workflow_step_runs
                 WHERE workspace_id = %s AND run_id = %s
                   AND status NOT IN ('completed','skipped')
                 ORDER BY ordinal LIMIT 1
                """,
                (self.context.workspace_id, run_id),
            ).fetchone()
            work.rollback()
        return {"step_id": str(row[0]), "status": str(row[1]), "attempts": int(row[2])} if row else None

    def _set_status(self, run_id: str, status: str, *, error: str | None = None) -> None:
        terminal = status in {"completed", "failed", "cancelled"}
        with unit_of_work(self.database) as work:
            work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET status = %s, last_error = %s, revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP,
                       completed_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE completed_at END
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (status, error, terminal, self.context.workspace_id, run_id),
            )
            work.commit()

    def _set_step_status(
        self,
        run_id: str,
        step_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        attempts: int | None = None,
    ) -> None:
        with unit_of_work(self.database) as work:
            work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = %s, result = COALESCE(%s::jsonb, result),
                       last_error = %s, attempts = COALESCE(%s, attempts),
                       started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                       completed_at = CASE WHEN %s IN ('completed','failed','skipped') THEN CURRENT_TIMESTAMP ELSE completed_at END
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                """,
                (
                    status,
                    _json(result) if result is not None else None,
                    error,
                    attempts,
                    status,
                    self.context.workspace_id,
                    run_id,
                    step_id,
                ),
            )
            work.commit()

    def _select_next(self, run_id: str) -> None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                SELECT step_id FROM omnix_workflow_step_runs
                 WHERE workspace_id = %s AND run_id = %s AND status NOT IN ('completed','skipped')
                 ORDER BY ordinal LIMIT 1
                """,
                (self.context.workspace_id, run_id),
            ).fetchone()
            work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET current_step_id = %s, status = %s, revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (
                    str(row[0]) if row else None,
                    "running" if row else "completed",
                    self.context.workspace_id,
                    run_id,
                ),
            )
            work.commit()


@lru_cache(maxsize=1)
def default_workflow_runtime() -> PostgresWorkflowRuntime:
    return PostgresWorkflowRuntime()
