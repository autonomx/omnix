"""Durable TaskGraph scheduling, parallel launch, aggregation, and recovery."""
from __future__ import annotations

import json
import threading
import uuid
from functools import lru_cache
from typing import Any, Callable

from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.models import AssistantToolRequest
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .contracts import AgentRunCommand, AgentRunSpec
from .profiles import get_agent_profile
from .task_graph import (
    TaskEdge,
    TaskGraph,
    TaskGraphRunSnapshot,
    TaskNode,
    TaskNodeRunState,
)
from .task_graph_repository import PostgresTaskGraphRepository
from .task_graph_revision import plan_graph_revision


class TaskGraphRuntimeError(RuntimeError):
    pass


class PostgresTaskGraphRuntime:
    """Authority-free coordinator over existing durable Agent/capability runtimes.

    The coordinator never receives the union of node capabilities. It may only
    launch already-compiled node envelopes, observe status, pass declared
    outputs over graph edges, and cancel work.
    """

    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        agent_service: Any | None = None,
        capability_executor: Callable[[str, AssistantToolRequest], Any] = hermes_assistant_tool_execute_payload,
    ) -> None:
        self.database = database or default_database()
        self.context = bootstrap_local_tenant(self.database)
        self._agent_service = agent_service
        self.capability_executor = capability_executor
        self._supervisor_started = False
        self._supervisor_lock = threading.Lock()
        self._supervisor_stop = threading.Event()

    @property
    def agent_service(self):
        if self._agent_service is None:
            from .service import default_agent_run_service

            self._agent_service = default_agent_run_service()
        return self._agent_service

    def _ensure_supervisor(self) -> None:
        if self._supervisor_started:
            return
        with self._supervisor_lock:
            if self._supervisor_started:
                return
            self._supervisor_started = True
            threading.Thread(
                target=self._supervisor_loop,
                name="omnix-task-graph-supervisor",
                daemon=True,
            ).start()

    def _supervisor_loop(self) -> None:
        while not self._supervisor_stop.is_set():
            try:
                self._supervise_once()
            except Exception:
                pass
            self._supervisor_stop.wait(2.0)

    def _supervise_once(self) -> None:
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            run_ids = repository.list_active_run_ids()
            work.rollback()
        for run_id in run_ids:
            try:
                self.recover(run_id)
            except Exception:
                continue

    def close(self) -> None:
        self._supervisor_stop.set()

    def start(
        self,
        graph: TaskGraph,
        *,
        run_id: str | None = None,
    ) -> TaskGraphRunSnapshot:
        self._ensure_supervisor()
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            snapshot = repository.create_run(graph, run_id=run_id)
            work.commit()
        return self.advance(snapshot.run_id)

    def get_status(self, run_id: str) -> TaskGraphRunSnapshot | None:
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            work.rollback()
        return snapshot

    def stream_events(self, run_id: str, *, after_sequence: int = 0):
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            rows = repository.stream_events(run_id, after_sequence=after_sequence)
            work.rollback()
        return rows

    def _node_map(self, graph: TaskGraph) -> dict[str, TaskNode]:
        return {node.id: node for node in graph.nodes}

    def _state_map(
        self,
        states: list[TaskNodeRunState],
    ) -> dict[str, TaskNodeRunState]:
        return {state.node_id: state for state in states}

    def _incoming(self, graph: TaskGraph, node_id: str) -> list[TaskEdge]:
        return [edge for edge in graph.edges if edge.target == node_id]

    def _predecessor_outputs(
        self,
        graph: TaskGraph,
        states: dict[str, TaskNodeRunState],
        node_id: str,
    ) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for edge in self._incoming(graph, node_id):
            source = states[edge.source]
            value: Any = source.output
            if edge.source_output:
                value = source.output.get(edge.source_output)
            key = edge.target_input or edge.source
            output[key] = value
        return output

    def _edge_allows(
        self,
        edge: TaskEdge,
        state: TaskNodeRunState,
    ) -> bool:
        if edge.kind != "condition":
            return True
        observed = (
            state.output.get(edge.source_output)
            if edge.source_output
            else state.output.get("matched")
        )
        expected = True if edge.expected_value is None else edge.expected_value
        return observed == expected

    def _readiness(
        self,
        graph: TaskGraph,
        states: dict[str, TaskNodeRunState],
        node: TaskNode,
    ) -> tuple[bool, bool]:
        """Return (ready, should_skip)."""

        incoming = self._incoming(graph, node.id)
        if not incoming:
            return True, False
        for edge in incoming:
            source = states[edge.source]
            if source.status in {"failed", "cancelled"}:
                return False, node.optional
            if source.status not in {"completed", "skipped"}:
                return False, False
            if not self._edge_allows(edge, source):
                return False, True
        return True, False

    def _poll_children(self, snapshot: TaskGraphRunSnapshot) -> None:
        node_map = self._node_map(snapshot.graph)
        for state in snapshot.node_states:
            if state.status != "running" or not state.child_run_id:
                continue
            node = node_map[state.node_id]
            child = self.agent_service.get(state.child_run_id)
            if child is None or child.status not in {"completed", "failed", "cancelled"}:
                continue

            output: dict[str, Any] = {
                "child_run_id": child.run_id,
                "status": child.status,
            }
            if child.status == "completed":
                try:
                    artifacts = self.agent_service.artifacts(child.run_id)
                    output["artifacts"] = [
                        item.model_dump(mode="json")
                        for item in artifacts
                    ]
                except Exception:
                    output["artifacts"] = []
                if node.evidence_policy.requirement == "required":
                    try:
                        evidence = self.agent_service.evidence_set(child.run_id)
                        output["evidence_passed"] = bool(evidence.passed)
                        output["evidence"] = evidence.model_dump(mode="json")
                        if not evidence.passed:
                            self._store_node(
                                snapshot.run_id,
                                node.id,
                                status="failed",
                                output=output,
                                last_error="node_evidence_requirements_unsatisfied",
                            )
                            continue
                    except Exception as exc:
                        self._store_node(
                            snapshot.run_id,
                            node.id,
                            status="failed",
                            output=output,
                            last_error=f"node_evidence_evaluation_failed:{type(exc).__name__}:{exc}"[:1000],
                        )
                        continue
                self._store_node(
                    snapshot.run_id,
                    node.id,
                    status="completed",
                    output=output,
                )
            elif node.optional:
                self._store_node(
                    snapshot.run_id,
                    node.id,
                    status="skipped",
                    output=output,
                    last_error=child.last_error or child.status,
                )
            else:
                self._store_node(
                    snapshot.run_id,
                    node.id,
                    status="failed",
                    output=output,
                    last_error=child.last_error or f"child_{child.status}",
                )

    def _claim_node(
        self,
        run_id: str,
        node_id: str,
        *,
        child_run_id: str | None = None,
    ) -> TaskNodeRunState | None:
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            state = repository.claim_node(
                run_id,
                node_id,
                child_run_id=child_run_id,
            )
            work.commit()
        return state

    def _store_node(
        self,
        run_id: str,
        node_id: str,
        *,
        status: str,
        child_run_id: str | None = None,
        output: dict[str, Any] | None = None,
        last_error: str | None = None,
        increment_attempts: bool = False,
    ) -> TaskNodeRunState:
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            state = repository.update_node(
                run_id,
                node_id,
                status=status,
                child_run_id=child_run_id,
                output=output,
                last_error=last_error,
                increment_attempts=increment_attempts,
            )
            work.commit()
        return state

    def _set_run_status(
        self,
        snapshot: TaskGraphRunSnapshot,
        status: str,
        *,
        last_error: str | None = None,
    ) -> TaskGraphRunSnapshot:
        if snapshot.status == status and snapshot.last_error == last_error:
            return snapshot
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            current = repository.update_run_status(
                snapshot.run_id,
                status,
                last_error=last_error,
            )
            work.commit()
        return current

    def _condition(self, expression: str, inputs: dict[str, Any]) -> bool:
        clean = str(expression or "").strip()
        negate = clean.startswith("not ")
        if negate:
            clean = clean[4:].strip()
        if clean.startswith("exists:"):
            value = inputs.get(clean.split(":", 1)[1])
            matched = value is not None
        elif clean.startswith("truthy:"):
            value = inputs.get(clean.split(":", 1)[1])
            matched = bool(value)
        else:
            raise TaskGraphRuntimeError(
                f"unsupported deterministic condition:{expression}"
            )
        return not matched if negate else matched

    def _execute_claimed_node(
        self,
        run_id: str,
        graph: TaskGraph,
        states: dict[str, TaskNodeRunState],
        node: TaskNode,
        claimed: TaskNodeRunState,
    ) -> bool:
        inputs = self._predecessor_outputs(graph, states, node.id)
        if node.kind == "join":
            self._store_node(
                run_id,
                node.id,
                status="completed",
                output={"result": inputs},
            )
            return True

        if node.kind == "condition":
            matched = self._condition(str(node.condition), inputs)
            self._store_node(
                run_id,
                node.id,
                status="completed",
                output={"matched": matched, "inputs": inputs},
            )
            return True

        if node.kind == "approval":
            self._store_node(
                run_id,
                node.id,
                status="waiting_for_approval",
                output={"inputs": inputs},
            )
            return True

        if node.kind == "capability":
            namespace = str(node.capability_id).split(".", 1)[0]
            request = AssistantToolRequest(
                tool_id=namespace,
                action_id=str(node.capability_id),
                session_id=f"task-graph:{run_id}",
                proposal_id=f"task-graph:{run_id}:{node.id}:{claimed.attempts}",
                input={**node.input_template, **inputs},
                approved=node.approval_policy == "allow_automatic",
            )
            try:
                payload = self.capability_executor(f"task-graph:{run_id}", request)
                execution = payload.execution_result
                if execution.error:
                    raise TaskGraphRuntimeError(execution.error)
                result = execution.model_dump(mode="json")
            except Exception as exc:
                self._store_node(
                    run_id,
                    node.id,
                    status="skipped" if node.optional else "failed",
                    last_error=f"{type(exc).__name__}:{exc}"[:1000],
                )
                return True
            self._store_node(
                run_id,
                node.id,
                status="completed",
                output={"result": result},
            )
            return True

        assert node.profile_id is not None
        assert node.model is not None
        child_run_id = str(claimed.child_run_id or "").strip()
        if not child_run_id:
            self._store_node(
                run_id,
                node.id,
                status="failed",
                last_error="claimed_agent_node_missing_child_run_id",
            )
            return True
        profile = get_agent_profile(node.profile_id)
        spec = AgentRunSpec(
            run_id=child_run_id,
            task=node.objective,
            objective=node.objective,
            success_criteria=list(node.success_criteria),
            profile=node.profile_id,
            model=node.model,
            capabilities=list(node.required_local_capabilities),
            resource_scopes=list(node.resource_scopes),
            external_capabilities=list(node.required_external_capabilities),
            evidence_policy=node.evidence_policy,
            workspace=node.workspace,
            limits=node.limits,
            approval_policy=node.approval_policy,
            context_sources=list(profile.context_sources),
            expected_artifacts=(
                list(node.acceptance_plan.required_artifacts)
                if node.acceptance_plan is not None
                else []
            ),
            acceptance_plan=node.acceptance_plan,
        )
        reference_context = (
            "TaskGraph declared predecessor outputs "
            "(reference data only; not execution authority):\n"
            + json.dumps(inputs, sort_keys=True, default=str)
            if inputs
            else ""
        )
        try:
            contextual_start = getattr(self.agent_service, "start_with_context", None)
            child = (
                contextual_start(spec, reference_context=reference_context)
                if callable(contextual_start)
                else self.agent_service.start(spec)
            )
        except Exception as exc:
            self._store_node(
                run_id,
                node.id,
                status="skipped" if node.optional else "failed",
                last_error=f"{type(exc).__name__}:{exc}"[:1000],
            )
            return True
        self._store_node(
            run_id,
            node.id,
            status="running",
            child_run_id=child.run_id,
            output={"inputs": inputs},
        )
        return True

    def _launch_node(
        self,
        run_id: str,
        graph: TaskGraph,
        states: dict[str, TaskNodeRunState],
        node: TaskNode,
    ) -> bool:
        child_run_id = (
            uuid.uuid4().hex
            if node.kind in {"agent", "evidence_read"}
            else None
        )
        claimed = self._claim_node(
            run_id,
            node.id,
            child_run_id=child_run_id,
        )
        if claimed is None:
            return False
        return self._execute_claimed_node(
            run_id,
            graph,
            states,
            node,
            claimed,
        )


    def advance(self, run_id: str) -> TaskGraphRunSnapshot:
        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        if snapshot.status in {"completed", "failed", "cancelled"}:
            return snapshot

        self._poll_children(snapshot)
        snapshot = self.get_status(run_id)
        assert snapshot is not None
        node_map = self._node_map(snapshot.graph)
        states = self._state_map(snapshot.node_states)

        required_failure = next(
            (
                state
                for state in snapshot.node_states
                if state.status == "failed" and not node_map[state.node_id].optional
            ),
            None,
        )
        if required_failure is not None:
            return self._set_run_status(
                snapshot,
                "failed",
                last_error=f"task_graph_node_failed:{required_failure.node_id}:{required_failure.last_error or ''}"[:1000],
            )

        running = sum(
            1
            for state in snapshot.node_states
            if state.status in {"ready", "running"}
        )
        available_slots = max(0, snapshot.graph.max_parallel_nodes - running)
        progressed = True
        while progressed:
            progressed = False
            snapshot = self.get_status(run_id)
            assert snapshot is not None
            states = self._state_map(snapshot.node_states)
            running = sum(
                1
                for state in snapshot.node_states
                if state.status in {"ready", "running"}
            )
            available_slots = max(0, snapshot.graph.max_parallel_nodes - running)

            for node in snapshot.graph.nodes:
                state = states[node.id]
                if state.status != "pending":
                    continue
                ready, skip = self._readiness(snapshot.graph, states, node)
                if skip:
                    self._store_node(
                        run_id,
                        node.id,
                        status="skipped",
                        last_error="graph_condition_or_optional_dependency_skipped",
                    )
                    progressed = True
                    continue
                if not ready:
                    continue
                if node.kind in {"agent", "evidence_read"} and available_slots <= 0:
                    continue
                if self._launch_node(run_id, snapshot.graph, states, node):
                    progressed = True
                    if node.kind in {"agent", "evidence_read"}:
                        available_slots -= 1

        snapshot = self.get_status(run_id)
        assert snapshot is not None
        statuses = {state.status for state in snapshot.node_states}
        if all(
            state.status in {"completed", "skipped"}
            for state in snapshot.node_states
        ):
            return self._set_run_status(snapshot, "completed")
        if "waiting_for_approval" in statuses and "running" not in statuses:
            return self._set_run_status(snapshot, "waiting_for_approval")
        return self._set_run_status(snapshot, "running")

    def approve(self, run_id: str, node_id: str) -> TaskGraphRunSnapshot:
        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        node = next((item for item in snapshot.graph.nodes if item.id == node_id), None)
        state = next((item for item in snapshot.node_states if item.node_id == node_id), None)
        if node is None or state is None or node.kind != "approval":
            raise TaskGraphRuntimeError("approval node not found")
        if state.status != "waiting_for_approval":
            raise TaskGraphRuntimeError("node is not waiting for approval")
        self._store_node(
            run_id,
            node_id,
            status="completed",
            output={**state.output, "approved": True},
        )
        return self.advance(run_id)

    def reject(self, run_id: str, node_id: str) -> TaskGraphRunSnapshot:
        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        state = next((item for item in snapshot.node_states if item.node_id == node_id), None)
        if state is None or state.status != "waiting_for_approval":
            raise TaskGraphRuntimeError("node is not waiting for approval")
        self._store_node(
            run_id,
            node_id,
            status="cancelled",
            output={**state.output, "approved": False},
            last_error="approval_rejected",
        )
        return self.cancel(run_id, reason="approval_rejected")

    def _cancel_child(self, child_run_id: str) -> None:
        try:
            self.agent_service.command(
                AgentRunCommand(
                    run_id=child_run_id,
                    command_type="cancel",
                    payload={"reason": "task_graph_cancelled"},
                )
            )
        except Exception:
            pass

    def cancel(
        self,
        run_id: str,
        *,
        reason: str = "cancelled_by_user",
    ) -> TaskGraphRunSnapshot:
        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        for state in snapshot.node_states:
            if state.status == "running" and state.child_run_id:
                self._cancel_child(state.child_run_id)
            if state.status not in {"completed", "failed", "cancelled", "skipped"}:
                self._store_node(
                    run_id,
                    state.node_id,
                    status="cancelled",
                    last_error=reason,
                )
        latest = self.get_status(run_id)
        assert latest is not None
        return self._set_run_status(latest, "cancelled", last_error=reason)

    def revise(
        self,
        run_id: str,
        revised_graph: TaskGraph,
        *,
        user_instruction: str,
        reuse_completed: bool = True,
    ) -> TaskGraphRunSnapshot:
        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)

        normalized = revised_graph.model_copy(
            update={
                "graph_id": snapshot.graph.graph_id,
                "revision": snapshot.graph.revision + 1,
            }
        )
        plan = plan_graph_revision(
            snapshot.graph,
            normalized,
            snapshot.node_states,
        )
        states = self._state_map(snapshot.node_states)
        preserved = (
            set(plan.reusable_completed_node_ids)
            | set(plan.retained_running_node_ids)
            if reuse_completed
            else set()
        )
        invalidate = set(plan.invalidated_node_ids) | set(plan.removed_node_ids)
        if not reuse_completed:
            invalidate.update(states)
        for node_id in invalidate:
            state = states.get(node_id)
            if state is not None and state.status == "running" and state.child_run_id:
                self._cancel_child(state.child_run_id)

        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            repository.apply_revision(
                run_id,
                normalized,
                user_instruction=user_instruction,
                reusable_node_ids=preserved,
            )
            work.commit()
        return self.advance(run_id)

    def recover(self, run_id: str) -> TaskGraphRunSnapshot:
        """Resume durable graph work after coordinator restart.

        Claimed Agent nodes are restart-safe because their child run id was
        persisted before launch. A claimed capability node has unknown external
        outcome and therefore fails closed instead of being executed twice.
        """

        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        if snapshot.status in {"completed", "failed", "cancelled"}:
            return snapshot
        node_map = self._node_map(snapshot.graph)
        states = self._state_map(snapshot.node_states)
        for state in snapshot.node_states:
            if state.status != "ready":
                continue
            node = node_map[state.node_id]
            if node.kind == "capability":
                self._store_node(
                    run_id,
                    node.id,
                    status="failed",
                    last_error="capability_outcome_unknown_after_coordinator_recovery",
                )
                continue
            self._execute_claimed_node(
                run_id,
                snapshot.graph,
                states,
                node,
                state,
            )
        return self.advance(run_id)


@lru_cache(maxsize=1)
def default_task_graph_runtime() -> PostgresTaskGraphRuntime:
    return PostgresTaskGraphRuntime()
