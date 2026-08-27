"""PostgreSQL-backed deterministic WorkflowRuntime."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import os
import threading
import uuid
from typing import Any, Callable

from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.models import AssistantToolRequest
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.outbox_repository import PostgresOutboxRepository
from app.persistence.unit_of_work import unit_of_work

from .capabilities import default_capability_registry
from .interfaces import WorkflowRuntime
from .workflows import (
    WORKFLOW_END,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowRunSnapshot,
    WorkflowScheduleSnapshot,
    WorkflowStepDefinition,
)


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
        self.worker_id = f"workflow:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        self._supervisor_started = False
        self._supervisor_lock = threading.Lock()
        self._supervisor_stop = threading.Event()

    def _append_event(
        self,
        connection,
        event: WorkflowEvent,
    ) -> WorkflowEvent:
        locked = connection.execute(
            """
            SELECT revision
              FROM omnix_workflow_runs
             WHERE workspace_id = %s AND run_id = %s
             FOR UPDATE
            """,
            (self.context.workspace_id, event.run_id),
        ).fetchone()
        if locked is None:
            raise KeyError(event.run_id)
        row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1
              FROM omnix_workflow_run_events
             WHERE workspace_id = %s AND run_id = %s
            """,
            (self.context.workspace_id, event.run_id),
        ).fetchone()
        stored = event.model_copy(update={"sequence": int(row[0])})
        connection.execute(
            """
            INSERT INTO omnix_workflow_run_events (
                workspace_id, run_id, sequence, event_id,
                event_type, payload, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                self.context.workspace_id,
                stored.run_id,
                stored.sequence,
                stored.event_id,
                stored.event_type,
                _json(stored.payload),
                stored.created_at,
            ),
        )
        PostgresOutboxRepository(connection).append(
            self.context,
            aggregate_type="workflow_run",
            aggregate_id=stored.run_id,
            event_type=stored.event_type,
            payload=stored.model_dump(mode="json"),
            ordering_key=f"workflow:{stored.run_id}",
            event_key=f"workflow:{stored.event_id}",
        )
        return stored

    def register(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self._validate_definition_capabilities(definition)
        with unit_of_work(self.database) as work:
            inserted = work.connection.execute(
                """
                INSERT INTO omnix_workflow_definitions (
                    workspace_id, workflow_id, version, name, definition, active
                ) VALUES (%s, %s, %s, %s, %s::jsonb, TRUE)
                ON CONFLICT (workspace_id, workflow_id, version) DO NOTHING
                RETURNING workflow_id
                """,
                (
                    self.context.workspace_id,
                    definition.id,
                    definition.version,
                    definition.name,
                    _json(definition),
                ),
            ).fetchone()
            if inserted is None:
                row = work.connection.execute(
                    """
                    SELECT definition
                      FROM omnix_workflow_definitions
                     WHERE workspace_id = %s AND workflow_id = %s AND version = %s
                    """,
                    (self.context.workspace_id, definition.id, definition.version),
                ).fetchone()
                if row is None:
                    raise WorkflowRuntimeError("workflow_version_conflict")
                existing = WorkflowDefinition.model_validate(row[0])
                if existing != definition:
                    raise WorkflowRuntimeError(
                        f"workflow_version_immutable:{definition.id}:v{definition.version}"
                    )
                work.rollback()
                return existing
            work.commit()
        return definition

    @staticmethod
    def _validate_definition_capabilities(definition: WorkflowDefinition) -> None:
        registry = default_capability_registry()
        for step in definition.steps:
            if step.kind != "capability":
                continue
            capability = registry.get(str(step.capability_id or ""))
            if capability is None:
                raise WorkflowRuntimeError(
                    f"workflow_capability_unknown:{step.capability_id}"
                )
            if not capability.enabled:
                raise WorkflowRuntimeError(
                    f"workflow_capability_disabled:{capability.id}"
                )
            if capability.execution_zone != "broker":
                raise WorkflowRuntimeError(
                    f"workflow_capability_zone_unsupported:{capability.id}:{capability.execution_zone}"
                )

    def list_definitions(self) -> list[WorkflowDefinition]:
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT DISTINCT ON (workflow_id) definition
                  FROM omnix_workflow_definitions
                 WHERE workspace_id = %s AND active
                 ORDER BY workflow_id, version DESC
                """,
                (self.context.workspace_id,),
            ).fetchall()
            work.rollback()
        return [WorkflowDefinition.model_validate(row[0]) for row in rows]

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
        self._ensure_supervisor()
        definition = self._definition(workflow_id)
        if definition is None:
            raise KeyError(workflow_id)
        return self._start_definition(definition, input_payload)

    def _start_definition(
        self,
        definition: WorkflowDefinition,
        input_payload: dict[str, object],
    ) -> str:
        run_id = uuid.uuid4().hex
        idempotency_key = str(input_payload.get("idempotency_key") or "").strip() or None
        with unit_of_work(self.database) as work:
            inserted = work.connection.execute(
                """
                INSERT INTO omnix_workflow_runs (
                    workspace_id, run_id, workflow_id, workflow_version,
                    input_payload, status, current_step_id, idempotency_key
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (workspace_id, idempotency_key) DO NOTHING
                RETURNING run_id
                """,
                (
                    self.context.workspace_id,
                    run_id,
                    definition.id,
                    definition.version,
                    _json(input_payload),
                    "running" if definition.steps else "completed",
                    definition.steps[0].id if definition.steps else None,
                    idempotency_key,
                ),
            ).fetchone()
            if inserted is None:
                if not idempotency_key:
                    raise WorkflowRuntimeError("workflow_run_insert_conflict")
                existing = work.connection.execute(
                    """
                    SELECT run_id, workflow_id, workflow_version
                      FROM omnix_workflow_runs
                     WHERE workspace_id = %s AND idempotency_key = %s
                    """,
                    (self.context.workspace_id, idempotency_key),
                ).fetchone()
                if existing is None:
                    raise WorkflowRuntimeError("workflow_idempotency_conflict")
                if (
                    str(existing[1]) != definition.id
                    or int(existing[2]) != definition.version
                ):
                    raise WorkflowRuntimeError(
                        f"workflow_idempotency_key_reused:{idempotency_key}"
                    )
                work.rollback()
                return str(existing[0])
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

    def stream_events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[WorkflowEvent]:
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT event_id, sequence, event_type, payload, created_at
                  FROM omnix_workflow_run_events
                 WHERE workspace_id = %s AND run_id = %s
                   AND sequence > %s
                 ORDER BY sequence
                 LIMIT 5000
                """,
                (
                    self.context.workspace_id,
                    run_id,
                    max(0, int(after_sequence)),
                ),
            ).fetchall()
            work.rollback()
        return [
            WorkflowEvent(
                event_id=str(row[0]),
                run_id=run_id,
                sequence=int(row[1]),
                event_type=str(row[2]),
                payload=dict(row[3] or {}),
                created_at=row[4],
            )
            for row in rows
        ]

    def list_runs(
        self,
        *,
        workflow_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        bounded = max(1, min(int(limit), 1000))
        with unit_of_work(self.database) as work:
            if workflow_id is None:
                rows = work.connection.execute(
                    """
                    SELECT run_id
                      FROM omnix_workflow_runs
                     WHERE workspace_id = %s
                     ORDER BY created_at DESC, run_id DESC
                     LIMIT %s
                    """,
                    (self.context.workspace_id, bounded),
                ).fetchall()
            else:
                rows = work.connection.execute(
                    """
                    SELECT run_id
                      FROM omnix_workflow_runs
                     WHERE workspace_id = %s AND workflow_id = %s
                     ORDER BY created_at DESC, run_id DESC
                     LIMIT %s
                    """,
                    (self.context.workspace_id, workflow_id, bounded),
                ).fetchall()
            work.rollback()
        result: list[dict[str, object]] = []
        for row in rows:
            state = self.get_status(str(row[0]))
            if state is not None:
                result.append(state)
        return result

    def schedule(
        self,
        workflow_id: str,
        input_payload: dict[str, object],
        *,
        run_at: datetime,
        interval_seconds: int | None = None,
        version: int | None = None,
        schedule_id: str | None = None,
    ) -> str:
        self._ensure_supervisor()
        if run_at.tzinfo is None or run_at.utcoffset() is None:
            raise WorkflowRuntimeError("workflow_schedule_run_at_must_be_timezone_aware")
        if interval_seconds is not None and int(interval_seconds) < 60:
            raise WorkflowRuntimeError("workflow_schedule_interval_minimum_60_seconds")
        if "idempotency_key" in input_payload:
            raise WorkflowRuntimeError("workflow_schedule_input_reserves_idempotency_key")
        definition = self._definition(workflow_id, version=version)
        if definition is None:
            raise KeyError(workflow_id)
        issued_id = str(schedule_id or uuid.uuid4().hex).strip()
        if not issued_id:
            raise WorkflowRuntimeError("workflow_schedule_id_required")
        normalized_run_at = run_at.astimezone(timezone.utc)
        interval = int(interval_seconds) if interval_seconds is not None else None
        with unit_of_work(self.database) as work:
            inserted = work.connection.execute(
                """
                INSERT INTO omnix_workflow_schedules (
                    workspace_id, schedule_id, workflow_id, workflow_version,
                    input_payload, interval_seconds, next_run_at, enabled
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, TRUE)
                ON CONFLICT (workspace_id, schedule_id) DO NOTHING
                RETURNING schedule_id
                """,
                (
                    self.context.workspace_id,
                    issued_id,
                    definition.id,
                    definition.version,
                    _json(input_payload),
                    interval,
                    normalized_run_at,
                ),
            ).fetchone()
            if inserted is None:
                existing = work.connection.execute(
                    """
                    SELECT workflow_id, workflow_version, input_payload,
                           interval_seconds, next_run_at, enabled
                      FROM omnix_workflow_schedules
                     WHERE workspace_id = %s AND schedule_id = %s
                    """,
                    (self.context.workspace_id, issued_id),
                ).fetchone()
                if existing is None:
                    raise WorkflowRuntimeError("workflow_schedule_conflict")
                same = (
                    str(existing[0]) == definition.id
                    and int(existing[1]) == definition.version
                    and dict(existing[2] or {}) == dict(input_payload)
                    and (
                        int(existing[3]) if existing[3] is not None else None
                    ) == interval
                    and existing[4] == normalized_run_at
                    and bool(existing[5])
                )
                if not same:
                    raise WorkflowRuntimeError(
                        f"workflow_schedule_id_reused:{issued_id}"
                    )
                work.rollback()
                return issued_id
            work.commit()
        return issued_id

    def list_schedules(self) -> list[WorkflowScheduleSnapshot]:
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT schedule_id, workflow_id, workflow_version, input_payload,
                       interval_seconds, next_run_at, enabled, last_enqueued_at
                  FROM omnix_workflow_schedules
                 WHERE workspace_id = %s
                 ORDER BY created_at, schedule_id
                """,
                (self.context.workspace_id,),
            ).fetchall()
            work.rollback()
        return [
            WorkflowScheduleSnapshot(
                schedule_id=str(row[0]),
                workflow_id=str(row[1]),
                workflow_version=int(row[2]),
                input_payload=dict(row[3] or {}),
                interval_seconds=int(row[4]) if row[4] is not None else None,
                next_run_at=row[5],
                enabled=bool(row[6]),
                last_enqueued_at=row[7],
            )
            for row in rows
        ]

    def cancel_schedule(self, schedule_id: str) -> None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_schedules
                   SET enabled = FALSE, next_run_at = NULL,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND schedule_id = %s
                RETURNING schedule_id
                """,
                (self.context.workspace_id, schedule_id),
            ).fetchone()
            if row is None:
                raise KeyError(schedule_id)
            work.connection.execute(
                """
                UPDATE omnix_workflow_schedule_fires
                   SET status = 'cancelled',
                       last_error = 'schedule_cancelled_before_dispatch',
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND schedule_id = %s
                   AND status = 'pending'
                """,
                (self.context.workspace_id, schedule_id),
            )
            work.commit()

    def pause(self, run_id: str) -> None:
        self._ensure_supervisor()
        state = self.get_status(run_id)
        if state is None:
            raise KeyError(run_id)
        if state["status"] in {"completed", "failed", "cancelled"}:
            return
        self._set_status(run_id, "paused")

    def resume(self, run_id: str) -> None:
        self._ensure_supervisor()
        state = self.get_status(run_id)
        if state is None:
            raise KeyError(run_id)
        if state["status"] in {"completed", "failed", "cancelled"}:
            return
        self._set_status(run_id, "running")
        self._advance(run_id)

    def cancel(self, run_id: str) -> None:
        self._ensure_supervisor()
        state = self.get_status(run_id)
        if state is None:
            raise KeyError(run_id)
        if state["status"] in {"completed", "failed", "cancelled"}:
            return
        self._set_status(run_id, "cancelled")

    def approve(self, run_id: str, step_id: str) -> None:
        self._ensure_supervisor()
        self._resolve_approval(run_id, step_id, approved=True)
        self._advance(run_id)

    def reject(self, run_id: str, step_id: str) -> None:
        self._ensure_supervisor()
        self._resolve_approval(run_id, step_id, approved=False)

    def _resolve_approval(self, run_id: str, step_id: str, *, approved: bool) -> None:
        with unit_of_work(self.database) as work:
            if approved:
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
            else:
                row = work.connection.execute(
                    """
                    UPDATE omnix_workflow_step_runs
                       SET status = 'failed', last_error = 'approval_rejected',
                           completed_at = CURRENT_TIMESTAMP
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
                       SET status = 'cancelled', last_error = 'approval_rejected',
                           revision = revision + 1, updated_at = CURRENT_TIMESTAMP,
                           completed_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND run_id = %s
                    """,
                    (self.context.workspace_id, run_id),
                )
            work.commit()

    def get_status(self, run_id: str) -> dict[str, object] | None:
        self._ensure_supervisor()
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
        self._ensure_supervisor()
        while True:
            state = self.get_status(run_id)
            if state is None or state["status"] in {
                "paused", "cancelled", "completed", "failed", "waiting_for_approval"
            }:
                return
            definition = self._definition(
                str(state["workflow_id"]),
                version=int(state["workflow_version"]),
            )
            if definition is None:
                self._set_status(run_id, "failed", error="workflow_definition_missing")
                return
            current_step_id = str(state.get("current_step_id") or "")
            if not current_step_id:
                self._finish(run_id)
                return
            step = next(
                (item for item in definition.steps if item.id == current_step_id),
                None,
            )
            if step is None:
                self._set_status(run_id, "failed", error="workflow_current_step_missing")
                return
            step_row = self._step_state(run_id, step.id)
            if step_row is None:
                self._set_status(run_id, "failed", error="workflow_step_state_missing")
                return

            step_status = str(step_row["status"])
            if step_status == "completed":
                result = dict(step_row.get("result") or {})
                self._transition(
                    run_id,
                    self._next_target(definition, step, result),
                )
                continue
            if step_status == "running":
                # The owner heartbeat determines whether this is active or an
                # abandoned unknown-outcome step. Never double-claim it.
                return
            if step_status in {"failed", "skipped"}:
                self._set_status(
                    run_id,
                    "failed",
                    error=f"workflow_step_not_runnable:{step.id}:{step_status}",
                )
                return

            approval_required = self._step_requires_approval(step)
            if approval_required and step_status != "approved":
                if step_status == "pending":
                    self._set_waiting_for_approval(run_id, step.id)
                elif step_status == "waiting_for_approval":
                    self._set_status(run_id, "waiting_for_approval")
                else:
                    self._set_status(
                        run_id,
                        "failed",
                        error=f"workflow_approval_state_invalid:{step.id}:{step_status}",
                    )
                return

            claimed = self._claim_step(run_id, step.id)
            if claimed is None:
                return
            attempts = claimed
            try:
                context = self._context(run_id, dict(state["input_payload"]))
                result = self._execute_with_timeout(
                    run_id,
                    step,
                    context,
                    approved=approval_required,
                )
            except Exception as exc:
                message = str(exc)[:1000]
                unknown_outcome = message.startswith("step_timeout_outcome_unknown")
                retry_safe = self._step_retry_safe(step)
                latest = self.get_status(run_id)
                if latest is not None and latest["status"] == "cancelled":
                    return
                if (
                    not unknown_outcome
                    and retry_safe
                    and attempts <= step.retry_limit
                    and self._set_step_retry(run_id, step.id, message)
                ):
                    continue
                self._set_step_failed(run_id, step.id, message)
                self._set_status(run_id, "failed", error=message)
                return

            if not self._set_step_completed(run_id, step.id, result):
                return
            self._transition(
                run_id,
                self._next_target(definition, step, result),
            )

    @staticmethod
    def _step_requires_approval(step: WorkflowStepDefinition) -> bool:
        if step.kind == "approval" or step.requires_approval:
            return True
        if step.kind != "capability":
            return False
        capability = default_capability_registry().get(str(step.capability_id or ""))
        return bool(
            capability is not None
            and (
                capability.approval_policy != "allow_automatic"
                or capability.requires_confirmation
            )
        )

    @staticmethod
    def _step_retry_safe(step: WorkflowStepDefinition) -> bool:
        if step.kind != "capability":
            return True
        capability = default_capability_registry().get(str(step.capability_id or ""))
        return bool(capability is not None and capability.effect == "read")

    def _execute_with_timeout(
        self,
        run_id: str,
        step: WorkflowStepDefinition,
        context: dict[str, Any],
        *,
        approved: bool,
    ) -> dict[str, Any]:
        if step.timeout_seconds is None:
            return self._execute_step(run_id, step, context, approved=approved)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"workflow-{step.id[:16]}")
        future = executor.submit(self._execute_step, run_id, step, context, approved=approved)
        try:
            return future.result(timeout=step.timeout_seconds)
        except FutureTimeout as exc:
            future.cancel()
            raise WorkflowRuntimeError(
                f"step_timeout_outcome_unknown:{step.id}:{step.timeout_seconds}s"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _execute_step(
        self,
        run_id: str,
        step: WorkflowStepDefinition,
        context: dict[str, Any],
        *,
        approved: bool,
    ) -> dict[str, Any]:
        if step.kind == "condition":
            return {
                "condition": step.condition,
                "matched": self._condition(step.condition, context),
            }
        if step.kind == "approval":
            return {"approved": approved}
        namespace = str(step.capability_id).split(".", 1)[0]
        request = AssistantToolRequest(
            tool_id=namespace,
            action_id=str(step.capability_id),
            session_id=f"workflow:{run_id}",
            proposal_id=f"workflow:{run_id}:{step.id}",
            input=self._render_input(step.input_template, context),
            approved=approved,
        )
        payload = self.capability_executor(f"workflow:{run_id}", request)
        execution = payload.execution_result
        if execution.error:
            raise WorkflowRuntimeError(execution.error)
        return execution.model_dump(mode="json")

    def _context(self, run_id: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT step_id, result
                  FROM omnix_workflow_step_runs
                 WHERE workspace_id = %s AND run_id = %s AND result IS NOT NULL
                 ORDER BY ordinal
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
            work.rollback()
        return {
            "input": input_payload,
            "steps": {str(row[0]): dict(row[1] or {}) for row in rows},
        }

    @classmethod
    def _render_input(cls, template: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {key: cls._render_value(value, context) for key, value in template.items()}

    @classmethod
    def _render_value(cls, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            return cls._lookup(context, value[1:])
        if isinstance(value, list):
            return [cls._render_value(item, context) for item in value]
        if isinstance(value, dict):
            return {key: cls._render_value(item, context) for key, item in value.items()}
        return value

    @staticmethod
    def _lookup(context: dict[str, Any], path: str) -> Any:
        current: Any = context
        for part in path.split("."):
            if not part:
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @classmethod
    def _condition(cls, expression: str | None, context: dict[str, Any]) -> bool:
        if not expression:
            return True
        if "!=" in expression:
            left, right = [part.strip() for part in expression.split("!=", 1)]
            return str(cls._lookup(context, left)).casefold() != right.strip("'\"").casefold()
        if "==" in expression:
            left, right = [part.strip() for part in expression.split("==", 1)]
            return str(cls._lookup(context, left)).casefold() == right.strip("'\"").casefold()
        return bool(cls._lookup(context, expression.strip()))

    @staticmethod
    def _next_target(
        definition: WorkflowDefinition,
        step: WorkflowStepDefinition,
        result: dict[str, Any],
    ) -> str | None:
        if step.kind == "condition":
            explicit = step.on_true_step_id if bool(result.get("matched")) else step.on_false_step_id
            if explicit:
                return None if explicit == WORKFLOW_END else explicit
        if step.next_step_id:
            return None if step.next_step_id == WORKFLOW_END else step.next_step_id
        index = next(index for index, item in enumerate(definition.steps) if item.id == step.id)
        return definition.steps[index + 1].id if index + 1 < len(definition.steps) else None

    def _step_state(self, run_id: str, step_id: str) -> dict[str, Any] | None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                SELECT status, attempts, result, worker_id, lease_expires_at
                  FROM omnix_workflow_step_runs
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                """,
                (self.context.workspace_id, run_id, step_id),
            ).fetchone()
            work.rollback()
        return (
            {
                "status": str(row[0]),
                "attempts": int(row[1]),
                "result": dict(row[2] or {}),
                "worker_id": str(row[3]) if row[3] else None,
                "lease_expires_at": row[4],
            }
            if row
            else None
        )

    def _claim_step(self, run_id: str, step_id: str) -> int | None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'running', attempts = attempts + 1,
                       started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                       last_error = NULL, worker_id = %s,
                       lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                   AND status IN ('pending','approved')
                RETURNING attempts
                """,
                (self.worker_id, self.context.workspace_id, run_id, step_id),
            ).fetchone()
            work.commit()
        return int(row[0]) if row else None

    def _set_waiting_for_approval(self, run_id: str, step_id: str) -> None:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'waiting_for_approval'
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                   AND status = 'pending'
                RETURNING step_id
                """,
                (self.context.workspace_id, run_id, step_id),
            ).fetchone()
            if row is not None:
                work.connection.execute(
                    """
                    UPDATE omnix_workflow_runs
                       SET status = 'waiting_for_approval', revision = revision + 1,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND run_id = %s
                       AND current_step_id = %s
                    """,
                    (self.context.workspace_id, run_id, step_id),
                )
            work.commit()

    def _set_step_retry(self, run_id: str, step_id: str, error: str) -> bool:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'pending', last_error = %s, worker_id = NULL,
                       lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                   AND status = 'running' AND worker_id = %s
                RETURNING step_id
                """,
                (
                    error,
                    self.context.workspace_id,
                    run_id,
                    step_id,
                    self.worker_id,
                ),
            ).fetchone()
            work.commit()
        return row is not None

    def _set_step_failed(self, run_id: str, step_id: str, error: str) -> bool:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'failed', last_error = %s,
                       completed_at = CURRENT_TIMESTAMP, worker_id = NULL,
                       lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                   AND status = 'running' AND worker_id = %s
                RETURNING step_id
                """,
                (
                    error,
                    self.context.workspace_id,
                    run_id,
                    step_id,
                    self.worker_id,
                ),
            ).fetchone()
            work.commit()
        return row is not None

    def _set_step_completed(
        self,
        run_id: str,
        step_id: str,
        result: dict[str, Any],
    ) -> bool:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'completed', result = %s::jsonb, last_error = NULL,
                       completed_at = CURRENT_TIMESTAMP, worker_id = NULL,
                       lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                   AND status = 'running' AND worker_id = %s
                RETURNING step_id
                """,
                (
                    _json(result),
                    self.context.workspace_id,
                    run_id,
                    step_id,
                    self.worker_id,
                ),
            ).fetchone()
            work.commit()
        return row is not None

    def _transition(self, run_id: str, target: str | None) -> None:
        if target is None:
            self._finish(run_id)
            return
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET current_step_id = %s, status = 'running',
                       revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s
                   AND status = 'running'
                RETURNING run_id
                """,
                (target, self.context.workspace_id, run_id),
            ).fetchone()
            work.commit()
        if row is None:
            return

    def _finish(self, run_id: str) -> None:
        with unit_of_work(self.database) as work:
            work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'skipped', completed_at = CURRENT_TIMESTAMP,
                       worker_id = NULL, lease_expires_at = NULL,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s AND status IN ('pending','approved')
                """,
                (self.context.workspace_id, run_id),
            )
            work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET current_step_id = NULL, status = 'completed',
                       revision = revision + 1, updated_at = CURRENT_TIMESTAMP,
                       completed_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s
                   AND status NOT IN ('failed','cancelled','completed')
                """,
                (self.context.workspace_id, run_id),
            )
            work.commit()

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

    def _ensure_supervisor(self) -> None:
        if self._supervisor_started:
            return
        with self._supervisor_lock:
            if self._supervisor_started:
                return
            self._supervisor_started = True
            threading.Thread(
                target=self._supervisor_loop,
                name="omnix-workflow-supervisor",
                daemon=True,
            ).start()

    def _supervisor_loop(self) -> None:
        while not self._supervisor_stop.is_set():
            try:
                self._supervise_once()
            except Exception:
                pass
            self._supervisor_stop.wait(30.0)

    def _supervise_once(self) -> None:
        self._enqueue_due_schedule_fires()
        self._dispatch_pending_schedule_fires()
        error = "step_outcome_unknown_after_worker_loss"
        resumable: list[str] = []
        with unit_of_work(self.database) as work:
            work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND worker_id = %s
                   AND status = 'running'
                """,
                (self.context.workspace_id, self.worker_id),
            )
            stale = work.connection.execute(
                """
                SELECT step.run_id, step.step_id
                  FROM omnix_workflow_step_runs AS step
                  JOIN omnix_workflow_runs AS run
                    ON run.workspace_id = step.workspace_id
                   AND run.run_id = step.run_id
                 WHERE step.workspace_id = %s
                   AND run.status = 'running'
                   AND run.current_step_id = step.step_id
                   AND step.status = 'running'
                   AND step.lease_expires_at <= CURRENT_TIMESTAMP
                 FOR UPDATE OF step SKIP LOCKED
                """,
                (self.context.workspace_id,),
            ).fetchall()
            for run_id, step_id in stale:
                claimed = work.connection.execute(
                    """
                    UPDATE omnix_workflow_step_runs
                       SET status = 'failed', last_error = %s,
                           completed_at = CURRENT_TIMESTAMP,
                           worker_id = NULL, lease_expires_at = NULL,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                       AND status = 'running'
                       AND lease_expires_at <= CURRENT_TIMESTAMP
                    RETURNING step_id
                    """,
                    (
                        error,
                        self.context.workspace_id,
                        str(run_id),
                        str(step_id),
                    ),
                ).fetchone()
                if claimed is None:
                    continue
                work.connection.execute(
                    """
                    UPDATE omnix_workflow_runs
                       SET status = 'failed', last_error = %s,
                           revision = revision + 1,
                           updated_at = CURRENT_TIMESTAMP,
                           completed_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND run_id = %s
                       AND status = 'running'
                    """,
                    (error, self.context.workspace_id, str(run_id)),
                )
            resumable = [
                str(row[0])
                for row in work.connection.execute(
                    """
                    SELECT DISTINCT run.run_id
                      FROM omnix_workflow_runs AS run
                      JOIN omnix_workflow_step_runs AS step
                        ON step.workspace_id = run.workspace_id
                       AND step.run_id = run.run_id
                       AND step.step_id = run.current_step_id
                     WHERE run.workspace_id = %s
                       AND run.status = 'running'
                       AND step.status IN ('pending','approved','completed')
                     ORDER BY run.run_id
                    """,
                    (self.context.workspace_id,),
                ).fetchall()
            ]
            work.commit()
        for run_id in resumable:
            try:
                self._advance(run_id)
            except Exception:
                # The run remains durable; the next supervisor pass retries only
                # safe boundary states. In-flight side effects are never replayed.
                continue

    def _enqueue_due_schedule_fires(self) -> None:
        now = datetime.now(timezone.utc)
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT schedule_id, next_run_at, interval_seconds
                  FROM omnix_workflow_schedules
                 WHERE workspace_id = %s AND enabled
                   AND next_run_at IS NOT NULL
                   AND next_run_at <= CURRENT_TIMESTAMP
                 ORDER BY next_run_at, schedule_id
                 FOR UPDATE SKIP LOCKED
                 LIMIT 50
                """,
                (self.context.workspace_id,),
            ).fetchall()
            for schedule_id, scheduled_for, interval_seconds in rows:
                work.connection.execute(
                    """
                    INSERT INTO omnix_workflow_schedule_fires (
                        workspace_id, schedule_id, scheduled_for, status
                    ) VALUES (%s, %s, %s, 'pending')
                    ON CONFLICT (workspace_id, schedule_id, scheduled_for)
                    DO NOTHING
                    """,
                    (
                        self.context.workspace_id,
                        str(schedule_id),
                        scheduled_for,
                    ),
                )
                if interval_seconds is None:
                    next_run_at = None
                    enabled = False
                else:
                    interval = int(interval_seconds)
                    elapsed = max(
                        0.0,
                        (now - scheduled_for).total_seconds(),
                    )
                    intervals_to_advance = int(elapsed // interval) + 1
                    next_run_at = scheduled_for + timedelta(
                        seconds=interval * intervals_to_advance
                    )
                    enabled = True
                work.connection.execute(
                    """
                    UPDATE omnix_workflow_schedules
                       SET last_enqueued_at = %s, next_run_at = %s,
                           enabled = %s, updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND schedule_id = %s
                    """,
                    (
                        scheduled_for,
                        next_run_at,
                        enabled,
                        self.context.workspace_id,
                        str(schedule_id),
                    ),
                )
            work.commit()

    def _dispatch_pending_schedule_fires(self) -> None:
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT fire.schedule_id, fire.scheduled_for,
                       schedule.workflow_id, schedule.workflow_version,
                       schedule.input_payload
                  FROM omnix_workflow_schedule_fires AS fire
                  JOIN omnix_workflow_schedules AS schedule
                    ON schedule.workspace_id = fire.workspace_id
                   AND schedule.schedule_id = fire.schedule_id
                 WHERE fire.workspace_id = %s AND fire.status = 'pending'
                 ORDER BY fire.created_at, fire.schedule_id, fire.scheduled_for
                 LIMIT 50
                """,
                (self.context.workspace_id,),
            ).fetchall()
            work.rollback()
        for schedule_id, scheduled_for, workflow_id, version, input_payload in rows:
            definition = self._definition(
                str(workflow_id),
                version=int(version),
            )
            if definition is None:
                with unit_of_work(self.database) as work:
                    work.connection.execute(
                        """
                        UPDATE omnix_workflow_schedule_fires
                           SET status = 'failed',
                               last_error = 'workflow_definition_missing',
                               updated_at = CURRENT_TIMESTAMP
                         WHERE workspace_id = %s AND schedule_id = %s
                           AND scheduled_for = %s AND status = 'pending'
                        """,
                        (
                            self.context.workspace_id,
                            str(schedule_id),
                            scheduled_for,
                        ),
                    )
                    work.commit()
                continue
            payload = dict(input_payload or {})
            payload["idempotency_key"] = (
                f"workflow-schedule:{schedule_id}:"
                f"{scheduled_for.astimezone(timezone.utc).isoformat()}"
            )
            try:
                run_id = self._start_definition(definition, payload)
            except Exception:
                # Keep the fire pending. A later supervisor pass retries the
                # durable dispatch; deterministic run idempotency prevents
                # duplicate workflow execution if the first attempt committed.
                continue
            with unit_of_work(self.database) as work:
                work.connection.execute(
                    """
                    UPDATE omnix_workflow_schedule_fires
                       SET status = 'started', run_id = %s, last_error = NULL,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND schedule_id = %s
                       AND scheduled_for = %s AND status = 'pending'
                    """,
                    (
                        run_id,
                        self.context.workspace_id,
                        str(schedule_id),
                        scheduled_for,
                    ),
                )
                work.commit()

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


@lru_cache(maxsize=1)
def default_workflow_runtime() -> PostgresWorkflowRuntime:
    return PostgresWorkflowRuntime()
