"""Durable TaskGraph scheduling, parallel launch, aggregation, and recovery."""
from __future__ import annotations

import json
import logging
import threading
import uuid
from functools import lru_cache
from typing import Any, Callable

from app.assistant_tools.models import AssistantToolRequest
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .contracts import AgentRunCommand, AgentRunSpec, ModelRef
from .evidence import merge_evidence_requirements
from .profiles import get_agent_profile
from .task_graph import (
    TaskEdge,
    TaskGraph,
    TaskGraphRunSnapshot,
    TaskNode,
    TaskNodeRunState,
    task_node_fingerprint,
)
from .task_graph_optimizer import (
    EvidenceAcquisitionBatch,
    TaskGraphOptimizationPlan,
    optimize_task_graph,
)
from .task_graph_repository import PostgresTaskGraphRepository
from .task_graph_revision import plan_graph_revision


logger = logging.getLogger(__name__)


class TaskGraphRuntimeError(RuntimeError):
    pass


_AGENT_NODE_KINDS = {"agent", "evidence_read", "synthesis"}


def _default_capability_executor(
    session_id: str,
    request: AssistantToolRequest,
) -> Any:
    # Keep assistant-tool adapters out of the Agent Runtime import graph. The
    # eager Hermes import formed a cycle through config_store -> registry ->
    # app.agent_runtime while persistence startup was importing Chat.
    from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload

    return hermes_assistant_tool_execute_payload(session_id, request)


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
        capability_executor: Callable[[str, AssistantToolRequest], Any] | None = None,
        model_overrides: dict[str, ModelRef] | None = None,
    ) -> None:
        self.database = database or default_database()
        self.context = bootstrap_local_tenant(self.database)
        self._agent_service = agent_service
        self.capability_executor = capability_executor or _default_capability_executor
        self.model_overrides = dict(model_overrides or {})
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
                logger.exception("TaskGraph supervisor iteration failed")
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
                logger.exception(
                    "TaskGraph recovery failed for run %s",
                    run_id,
                )

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
        self._ensure_supervisor()
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
            if (
                state.status not in {"running", "waiting_for_approval"}
                or not state.child_run_id
            ):
                continue
            node = node_map[state.node_id]
            child = self.agent_service.get(state.child_run_id)
            if child is None:
                continue
            if child.status == "waiting_for_approval":
                if state.status != "waiting_for_approval":
                    try:
                        approvals = self.agent_service.approvals(
                            child.run_id,
                            state="pending",
                        )
                        pending = [
                            item.model_dump(mode="json")
                            for item in approvals
                        ]
                    except Exception:
                        pending = []
                    self._store_node(
                        snapshot.run_id,
                        node.id,
                        status="waiting_for_approval",
                        output={
                            **state.output,
                            "child_run_id": child.run_id,
                            "status": child.status,
                            "pending_approvals": pending,
                        },
                        expected_state=state,
                        expected_statuses=("running",),
                        graph_revision=snapshot.graph.revision,
                    )
                continue
            if (
                state.status == "waiting_for_approval"
                and child.status not in {"completed", "failed", "cancelled"}
            ):
                self._store_node(
                    snapshot.run_id,
                    node.id,
                    status="running",
                    output={
                        **state.output,
                        "child_run_id": child.run_id,
                        "status": child.status,
                        "pending_approvals": [],
                    },
                    expected_state=state,
                    expected_statuses=("waiting_for_approval",),
                    graph_revision=snapshot.graph.revision,
                )
                continue
            if child.status not in {"completed", "failed", "cancelled"}:
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
                final_result = self._child_result(child.run_id)
                output["result"] = (
                    final_result
                    if final_result is not None
                    else {
                        "child_run_id": child.run_id,
                        "status": child.status,
                        "artifacts": output["artifacts"],
                    }
                )
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
                                expected_state=state,
                                expected_statuses=("running",),
                                graph_revision=snapshot.graph.revision,
                            )
                            continue
                    except Exception as exc:
                        self._store_node(
                            snapshot.run_id,
                            node.id,
                            status="failed",
                            output=output,
                            last_error=f"node_evidence_evaluation_failed:{type(exc).__name__}:{exc}"[:1000],
                            expected_state=state,
                            expected_statuses=("running",),
                            graph_revision=snapshot.graph.revision,
                        )
                        continue
                self._store_node(
                    snapshot.run_id,
                    node.id,
                    status="completed",
                    output=output,
                    expected_state=state,
                    expected_statuses=("running",),
                    graph_revision=snapshot.graph.revision,
                )
            elif node.optional:
                self._store_node(
                    snapshot.run_id,
                    node.id,
                    status="skipped",
                    output=output,
                    last_error=child.last_error or child.status,
                    expected_state=state,
                    expected_statuses=("running",),
                    graph_revision=snapshot.graph.revision,
                )
            else:
                self._store_node(
                    snapshot.run_id,
                    node.id,
                    status="failed",
                    output=output,
                    last_error=child.last_error or f"child_{child.status}",
                    expected_state=state,
                    expected_statuses=("running",),
                    graph_revision=snapshot.graph.revision,
                )

    def _claim_node(
        self,
        run_id: str,
        graph: TaskGraph,
        node: TaskNode,
        *,
        child_run_id: str | None = None,
        claim_output: dict[str, Any] | None = None,
    ) -> TaskNodeRunState | None:
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            state = repository.claim_node(
                run_id,
                node.id,
                child_run_id=child_run_id,
                claim_output=claim_output,
                expected_fingerprint=task_node_fingerprint(node),
                expected_graph_revision=graph.revision,
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
        expected_state: TaskNodeRunState | None = None,
        expected_statuses: tuple[str, ...] | list[str] | None = None,
        graph_revision: int | None = None,
    ) -> TaskNodeRunState | None:
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
                expected_fingerprint=(
                    expected_state.fingerprint
                    if expected_state is not None
                    else None
                ),
                expected_child_run_id=(
                    expected_state.child_run_id
                    if expected_state is not None
                    else None
                ),
                match_child_run_id=expected_state is not None,
                expected_statuses=expected_statuses,
                expected_graph_revision=graph_revision,
            )
            work.commit()
        return state

    def _child_result(self, child_run_id: str) -> str | None:
        """Return the latest visible terminal model message for graph dataflow."""

        try:
            events = self.agent_service.events(child_run_id, after_sequence=0)
        except Exception:
            return None
        for event in reversed(list(events)):
            if event.event_type != "model.message":
                continue
            if str(event.payload.get("phase") or "") != "message_end":
                continue
            text = str(event.payload.get("text") or "").strip()
            if text:
                return text
        return None

    @staticmethod
    def _batch_policy_signature(node: TaskNode) -> str:
        policy = node.evidence_policy.model_dump(
            mode="json",
            exclude={"requirements"},
        )
        payload = {
            "profile": node.profile_id,
            "local": node.required_local_capabilities,
            "external": node.required_external_capabilities,
            "resource_scopes": [
                scope.model_dump(mode="json")
                for scope in node.resource_scopes
            ],
            "workspace": (
                node.workspace.model_dump(mode="json")
                if node.workspace is not None
                else None
            ),
            "limits": node.limits.model_dump(mode="json"),
            "approval": node.approval_policy,
            "optional": node.optional,
            "policy": policy,
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    def _batch_candidates(
        self,
        graph: TaskGraph,
        states: dict[str, TaskNodeRunState],
        node: TaskNode,
        plan: TaskGraphOptimizationPlan,
    ) -> tuple[EvidenceAcquisitionBatch | None, list[TaskNode]]:
        if node.kind != "evidence_read":
            return None, []
        node_requirement_ids = {
            requirement.id for requirement in node.evidence_policy.requirements
        }
        if not node_requirement_ids:
            return None, []

        selected_batch = next(
            (
                batch
                for batch in plan.evidence_batches
                if node.id in batch.node_ids
                and node_requirement_ids <= set(batch.requirement_ids)
            ),
            None,
        )
        if selected_batch is None:
            return None, []

        node_map = self._node_map(graph)
        signature = self._batch_policy_signature(node)
        selected_model = plan.model_selections.get(node.id) or node.model
        reference_inputs = json.dumps(
            self._predecessor_outputs(graph, states, node.id),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        candidates: list[TaskNode] = []
        for candidate_id in selected_batch.node_ids:
            candidate = node_map.get(candidate_id)
            state = states.get(candidate_id)
            if candidate is None or state is None:
                continue
            if candidate.kind != "evidence_read" or state.status != "pending":
                continue
            ready, skip = self._readiness(graph, states, candidate)
            if not ready or skip:
                continue
            requirement_ids = {
                requirement.id
                for requirement in candidate.evidence_policy.requirements
            }
            if not requirement_ids or not requirement_ids <= set(
                selected_batch.requirement_ids
            ):
                continue
            if self._batch_policy_signature(candidate) != signature:
                continue
            candidate_model = (
                plan.model_selections.get(candidate.id) or candidate.model
            )
            if candidate_model != selected_model:
                continue
            candidate_inputs = json.dumps(
                self._predecessor_outputs(graph, states, candidate.id),
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            if candidate_inputs != reference_inputs:
                continue
            candidates.append(candidate)

        priority = {
            node_id: index
            for index, node_id in enumerate(plan.cost_priority)
        }
        candidates.sort(
            key=lambda candidate: (
                priority.get(candidate.id, 10_000),
                candidate.id,
            )
        )
        return selected_batch, candidates

    def _claim_evidence_batch(
        self,
        run_id: str,
        graph: TaskGraph,
        nodes: list[TaskNode],
        *,
        child_run_id: str,
        batch: EvidenceAcquisitionBatch,
    ) -> list[TaskNodeRunState]:
        descriptor = {
            "batch_id": batch.batch_id,
            "node_ids": [node.id for node in nodes],
            "leader_id": nodes[0].id,
        }
        claims: list[TaskNodeRunState] = []
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(
                work.connection,
                self.context,
            )
            for node in nodes:
                claimed = repository.claim_node(
                    run_id,
                    node.id,
                    child_run_id=child_run_id,
                    claim_output={"evidence_batch": descriptor},
                    expected_fingerprint=task_node_fingerprint(node),
                    expected_graph_revision=graph.revision,
                )
                if claimed is None:
                    work.rollback()
                    return []
                claims.append(claimed)
            work.commit()
        return claims

    @staticmethod
    def _merged_evidence_batch_node(
        nodes: list[TaskNode],
        *,
        selected_model: ModelRef | None,
    ) -> TaskNode:
        leader = nodes[0]
        requirements = merge_evidence_requirements(
            [
                requirement
                for node in nodes
                for requirement in node.evidence_policy.requirements
            ]
        )
        policy = leader.evidence_policy.model_copy(
            update={"requirements": requirements}
        )
        objective = (
            "Complete one authority-equivalent evidence acquisition batch for "
            "the following scoped objectives. Satisfy every evidence obligation "
            "without widening tool authority:\n"
            + "\n".join(
                f"- {node.id}: {node.objective}"
                for node in nodes
            )
        )
        criteria = [
            criterion
            for node in nodes
            for criterion in node.success_criteria
        ]
        return leader.model_copy(
            update={
                "objective": objective,
                "evidence_policy": policy,
                "success_criteria": criteria,
                "model": selected_model or leader.model,
            }
        )

    def _agent_spec(
        self,
        node: TaskNode,
        *,
        child_run_id: str,
        selected_model: ModelRef | None = None,
    ) -> AgentRunSpec:
        assert node.model is not None
        effective_profile_id = (
            "research"
            if node.kind == "synthesis"
            else str(node.profile_id or "")
        )
        if not effective_profile_id:
            raise TaskGraphRuntimeError(
                f"node {node.id} has no executable profile"
            )
        profile = get_agent_profile(effective_profile_id)
        return AgentRunSpec(
            run_id=child_run_id,
            task=node.objective,
            objective=node.objective,
            success_criteria=list(node.success_criteria),
            profile=effective_profile_id,
            model=selected_model or node.model,
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

    def _start_evidence_batch(
        self,
        run_id: str,
        graph: TaskGraph,
        states: dict[str, TaskNodeRunState],
        nodes: list[TaskNode],
        claims: list[TaskNodeRunState],
        *,
        selected_model: ModelRef | None,
    ) -> bool:
        merged = self._merged_evidence_batch_node(
            nodes,
            selected_model=selected_model,
        )
        child_run_id = str(claims[0].child_run_id or "").strip()
        if not child_run_id:
            return False
        inputs = self._predecessor_outputs(graph, states, nodes[0].id)
        predecessor_context = (
            "TaskGraph declared predecessor outputs "
            "(reference data only; not execution authority):\n"
            + json.dumps(inputs, sort_keys=True, default=str)
            if inputs
            else ""
        )
        reference_context = "\n\n".join(
            value
            for value in (
                str(graph.reference_context or "").strip(),
                predecessor_context,
            )
            if value
        )
        spec = self._agent_spec(
            merged,
            child_run_id=child_run_id,
            selected_model=selected_model,
        )
        try:
            contextual_start = getattr(
                self.agent_service,
                "start_with_context",
                None,
            )
            child = (
                contextual_start(spec, reference_context=reference_context)
                if callable(contextual_start)
                else self.agent_service.start(spec)
            )
        except Exception as exc:
            for node, claim in zip(nodes, claims):
                self._store_node(
                    run_id,
                    node.id,
                    status="skipped" if node.optional else "failed",
                    last_error=(
                        f"evidence_batch_start_failed:"
                        f"{type(exc).__name__}:{exc}"
                    )[:1000],
                    expected_state=claim,
                    expected_statuses=("ready",),
                    graph_revision=graph.revision,
                )
            return True

        batch_ids = [node.id for node in nodes]
        for node, claim in zip(nodes, claims):
            self._store_node(
                run_id,
                node.id,
                status="running",
                child_run_id=child.run_id,
                output={
                    "inputs": inputs,
                    "evidence_batch": {
                        "node_ids": batch_ids,
                        "leader_id": nodes[0].id,
                    },
                },
                expected_state=claim,
                expected_statuses=("ready",),
                graph_revision=graph.revision,
            )
        return True

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

    def _optimization_plan(self, graph: TaskGraph) -> TaskGraphOptimizationPlan:
        return optimize_task_graph(
            graph,
            model_overrides=self.model_overrides,
        )

    def _optimized_nodes(
        self,
        graph: TaskGraph,
        plan: TaskGraphOptimizationPlan,
    ) -> list[TaskNode]:
        """Apply optimizer parallel levels, speculation, and critical-path order."""

        node_map = self._node_map(graph)
        speculative = set(plan.speculative_read_nodes)
        priority = {
            node_id: index
            for index, node_id in enumerate(plan.cost_priority)
        }
        ordered: list[TaskNode] = []
        seen: set[str] = set()
        for level in plan.parallel_groups:
            for node_id in sorted(
                level,
                key=lambda value: (
                    0 if value in speculative else 1,
                    priority.get(value, 10_000),
                    value,
                ),
            ):
                if node_id in node_map and node_id not in seen:
                    seen.add(node_id)
                    ordered.append(node_map[node_id])
        for node in graph.nodes:
            if node.id not in seen:
                ordered.append(node)
        return ordered

    def _cache_source(
        self,
        node: TaskNode,
        states: dict[str, TaskNodeRunState],
        plan: TaskGraphOptimizationPlan,
    ) -> TaskNodeRunState | None:
        key = plan.cache_keys.get(node.id)
        if key is None:
            return None
        for source_id, source_key in plan.cache_keys.items():
            if source_id == node.id or source_key != key:
                continue
            state = states.get(source_id)
            if state is not None and state.status == "completed":
                return state
        return None

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
        *,
        selected_model: ModelRef | None = None,
    ) -> bool:
        inputs = self._predecessor_outputs(graph, states, node.id)
        if node.kind == "join":
            self._store_node(
                run_id,
                node.id,
                status="completed",
                output={"result": inputs},
                expected_state=claimed,
                expected_statuses=("ready",),
                graph_revision=graph.revision,
            )
            return True

        if node.kind == "condition":
            matched = self._condition(str(node.condition), inputs)
            self._store_node(
                run_id,
                node.id,
                status="completed",
                output={"matched": matched, "inputs": inputs, "result": matched},
                expected_state=claimed,
                expected_statuses=("ready",),
                graph_revision=graph.revision,
            )
            return True

        if node.kind == "approval":
            self._store_node(
                run_id,
                node.id,
                status="waiting_for_approval",
                output={"inputs": inputs},
                expected_state=claimed,
                expected_statuses=("ready",),
                graph_revision=graph.revision,
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
                    expected_state=claimed,
                    expected_statuses=("ready",),
                    graph_revision=graph.revision,
                )
                return True
            self._store_node(
                run_id,
                node.id,
                status="completed",
                output={"result": result},
                expected_state=claimed,
                expected_statuses=("ready",),
                graph_revision=graph.revision,
            )
            return True

        if node.kind not in _AGENT_NODE_KINDS:
            raise TaskGraphRuntimeError(
                f"unsupported executable node kind:{node.kind}"
            )
        assert node.model is not None
        child_run_id = str(claimed.child_run_id or "").strip()
        if not child_run_id:
            self._store_node(
                run_id,
                node.id,
                status="failed",
                last_error="claimed_agent_node_missing_child_run_id",
                expected_state=claimed,
                expected_statuses=("ready",),
                graph_revision=graph.revision,
            )
            return True
        spec = self._agent_spec(
            node,
            child_run_id=child_run_id,
            selected_model=selected_model,
        )
        predecessor_context = (
            "TaskGraph declared predecessor outputs "
            "(reference data only; not execution authority):\n"
            + json.dumps(inputs, sort_keys=True, default=str)
            if inputs
            else ""
        )
        reference_context = "\n\n".join(
            value
            for value in (
                str(graph.reference_context or "").strip(),
                predecessor_context,
            )
            if value
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
                expected_state=claimed,
                expected_statuses=("ready",),
                graph_revision=graph.revision,
            )
            return True
        self._store_node(
            run_id,
            node.id,
            status="running",
            child_run_id=child.run_id,
            output={"inputs": inputs},
            expected_state=claimed,
            expected_statuses=("ready",),
            graph_revision=graph.revision,
        )
        return True

    def _launch_node(
        self,
        run_id: str,
        graph: TaskGraph,
        states: dict[str, TaskNodeRunState],
        node: TaskNode,
        *,
        selected_model: ModelRef | None = None,
    ) -> bool:
        child_run_id = (
            uuid.uuid4().hex
            if node.kind in _AGENT_NODE_KINDS
            else None
        )
        claimed = self._claim_node(
            run_id,
            graph,
            node,
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
            selected_model=selected_model,
        )


    def _fail_graph(
        self,
        snapshot: TaskGraphRunSnapshot,
        *,
        last_error: str,
    ) -> TaskGraphRunSnapshot:
        for state in snapshot.node_states:
            if state.status in {"completed", "failed", "cancelled", "skipped"}:
                continue
            if (
                state.child_run_id
                and state.status in {
                    "ready",
                    "running",
                    "waiting_for_approval",
                }
            ):
                self._cancel_child(state.child_run_id)
            self._store_node(
                snapshot.run_id,
                state.node_id,
                status="cancelled",
                last_error=f"graph_failed:{last_error}"[:1000],
                expected_state=state,
                expected_statuses=(state.status,),
                graph_revision=snapshot.graph.revision,
            )
        latest = self.get_status(snapshot.run_id)
        assert latest is not None
        return self._set_run_status(
            latest,
            "failed",
            last_error=last_error[:1000],
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
            return self._fail_graph(
                snapshot,
                last_error=(
                    f"task_graph_node_failed:{required_failure.node_id}:"
                    f"{required_failure.last_error or ''}"
                ),
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
            optimization = self._optimization_plan(snapshot.graph)

            for node in self._optimized_nodes(snapshot.graph, optimization):
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
                        expected_state=state,
                        expected_statuses=("pending",),
                        graph_revision=snapshot.graph.revision,
                    )
                    progressed = True
                    continue
                if not ready:
                    continue

                cache_source = self._cache_source(
                    node,
                    states,
                    optimization,
                )
                if cache_source is not None:
                    cached_output = {
                        **cache_source.output,
                        "cache_reused_from": cache_source.node_id,
                    }
                    stored = self._store_node(
                        run_id,
                        node.id,
                        status="completed",
                        output=cached_output,
                        expected_state=state,
                        expected_statuses=("pending",),
                        graph_revision=snapshot.graph.revision,
                    )
                    if stored is not None:
                        progressed = True
                    continue

                if node.kind in _AGENT_NODE_KINDS and available_slots <= 0:
                    continue

                if node.kind == "evidence_read":
                    evidence_batch, candidates = self._batch_candidates(
                        snapshot.graph,
                        states,
                        node,
                        optimization,
                    )
                    if (
                        evidence_batch is not None
                        and len(candidates) >= 2
                    ):
                        # Only the optimizer-selected first candidate claims the
                        # whole batch; peers defer rather than racing a duplicate.
                        if candidates[0].id != node.id:
                            continue
                        child_run_id = uuid.uuid4().hex
                        claims = self._claim_evidence_batch(
                            run_id,
                            snapshot.graph,
                            candidates,
                            child_run_id=child_run_id,
                            batch=evidence_batch,
                        )
                        if claims:
                            self._start_evidence_batch(
                                run_id,
                                snapshot.graph,
                                states,
                                candidates,
                                claims,
                                selected_model=(
                                    optimization.model_selections.get(node.id)
                                ),
                            )
                            progressed = True
                            available_slots -= 1
                            continue

                if self._launch_node(
                    run_id,
                    snapshot.graph,
                    states,
                    node,
                    selected_model=optimization.model_selections.get(node.id),
                ):
                    progressed = True
                    if node.kind in _AGENT_NODE_KINDS:
                        available_slots -= 1

        snapshot = self.get_status(run_id)
        assert snapshot is not None
        node_map = self._node_map(snapshot.graph)
        required_failure = next(
            (
                state
                for state in snapshot.node_states
                if state.status == "failed"
                and not node_map[state.node_id].optional
            ),
            None,
        )
        if required_failure is not None:
            return self._fail_graph(
                snapshot,
                last_error=(
                    f"task_graph_node_failed:{required_failure.node_id}:"
                    f"{required_failure.last_error or ''}"
                ),
            )
        statuses = {state.status for state in snapshot.node_states}
        if all(
            state.status in {"completed", "skipped"}
            for state in snapshot.node_states
        ):
            return self._set_run_status(snapshot, "completed")
        if "waiting_for_approval" in statuses:
            # Surface an approval immediately even while independent siblings
            # are still running. The supervisor continues advancing waiting
            # graphs, so this does not pause safe parallel work.
            return self._set_run_status(snapshot, "waiting_for_approval")
        return self._set_run_status(snapshot, "running")

    def _resolve_child_approval_id(
        self,
        state: TaskNodeRunState,
        approval_id: str | None,
    ) -> str:
        if not state.child_run_id:
            raise TaskGraphRuntimeError("node has no child approval run")
        pending = self.agent_service.approvals(
            state.child_run_id,
            state="pending",
        )
        if approval_id:
            if not any(item.approval_id == approval_id for item in pending):
                raise TaskGraphRuntimeError("child approval not found")
            return approval_id
        if len(pending) != 1:
            raise TaskGraphRuntimeError(
                "approval_id is required when a child has multiple pending approvals"
            )
        return pending[0].approval_id

    def approve(
        self,
        run_id: str,
        node_id: str,
        *,
        approval_id: str | None = None,
    ) -> TaskGraphRunSnapshot:
        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        node = next((item for item in snapshot.graph.nodes if item.id == node_id), None)
        state = next((item for item in snapshot.node_states if item.node_id == node_id), None)
        if node is None or state is None or state.status != "waiting_for_approval":
            raise TaskGraphRuntimeError("node is not waiting for approval")
        if node.kind == "approval":
            stored = self._store_node(
                run_id,
                node_id,
                status="completed",
                output={**state.output, "approved": True, "result": True},
                expected_state=state,
                expected_statuses=("waiting_for_approval",),
                graph_revision=snapshot.graph.revision,
            )
            if stored is None:
                raise TaskGraphRuntimeError("approval node changed during approval")
            return self.advance(run_id)

        child_approval_id = self._resolve_child_approval_id(
            state,
            approval_id,
        )
        self.agent_service.command(
            AgentRunCommand(
                run_id=str(state.child_run_id),
                command_type="approve",
                payload={"approval_id": child_approval_id},
            )
        )
        return self.advance(run_id)

    def reject(
        self,
        run_id: str,
        node_id: str,
        *,
        approval_id: str | None = None,
    ) -> TaskGraphRunSnapshot:
        snapshot = self.get_status(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        node = next((item for item in snapshot.graph.nodes if item.id == node_id), None)
        state = next((item for item in snapshot.node_states if item.node_id == node_id), None)
        if node is None or state is None or state.status != "waiting_for_approval":
            raise TaskGraphRuntimeError("node is not waiting for approval")
        if node.kind == "approval":
            stored = self._store_node(
                run_id,
                node_id,
                status="cancelled",
                output={**state.output, "approved": False, "result": False},
                last_error="approval_rejected",
                expected_state=state,
                expected_statuses=("waiting_for_approval",),
                graph_revision=snapshot.graph.revision,
            )
            if stored is None:
                raise TaskGraphRuntimeError("approval node changed during rejection")
            return self.cancel(run_id, reason="approval_rejected")

        child_approval_id = self._resolve_child_approval_id(
            state,
            approval_id,
        )
        self.agent_service.command(
            AgentRunCommand(
                run_id=str(state.child_run_id),
                command_type="reject",
                payload={"approval_id": child_approval_id},
            )
        )
        return self.cancel(run_id, reason="child_approval_rejected")

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
        if snapshot.status in {"completed", "failed", "cancelled"}:
            return snapshot
        for state in snapshot.node_states:
            if (
                state.status in {"ready", "running", "waiting_for_approval"}
                and state.child_run_id
            ):
                self._cancel_child(state.child_run_id)
            if state.status not in {"completed", "failed", "cancelled", "skipped"}:
                self._store_node(
                    run_id,
                    state.node_id,
                    status="cancelled",
                    last_error=reason,
                    expected_state=state,
                    expected_statuses=(state.status,),
                    graph_revision=snapshot.graph.revision,
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
        if snapshot.status in {"completed", "failed", "cancelled"}:
            raise TaskGraphRuntimeError(
                f"cannot revise terminal task graph:{snapshot.status}"
            )

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
        children_to_cancel = [
            state.child_run_id
            for node_id in invalidate
            if (state := states.get(node_id)) is not None
            and state.status in {"ready", "running", "waiting_for_approval"}
            and state.child_run_id
        ]

        # Win the graph-revision CAS before cancelling old children. A losing
        # steering command must never cancel work retained by the winner.
        with unit_of_work(self.database) as work:
            repository = PostgresTaskGraphRepository(work.connection, self.context)
            repository.apply_revision(
                run_id,
                normalized,
                user_instruction=user_instruction,
                reusable_node_ids=preserved,
            )
            work.commit()
        for child_run_id in children_to_cancel:
            self._cancel_child(str(child_run_id))
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
        optimization = self._optimization_plan(snapshot.graph)
        recovered_batches: set[str] = set()
        for state in snapshot.node_states:
            if state.status != "ready":
                continue
            node = node_map[state.node_id]
            batch_descriptor = state.output.get("evidence_batch")
            if isinstance(batch_descriptor, dict):
                leader_id = str(
                    batch_descriptor.get("leader_id") or ""
                ).strip()
                batch_ids = [
                    str(value)
                    for value in batch_descriptor.get("node_ids") or []
                    if str(value) in node_map
                ]
                batch_key = (
                    f"{state.child_run_id or ''}:"
                    + ",".join(sorted(batch_ids))
                )
                if batch_key in recovered_batches:
                    continue
                recovered_batches.add(batch_key)
                batch_nodes = [
                    node_map[node_id]
                    for node_id in batch_ids
                    if states[node_id].status in {"ready", "running"}
                ]
                ready_claims = [
                    states[node_id]
                    for node_id in batch_ids
                    if states[node_id].status == "ready"
                ]
                child = (
                    self.agent_service.get(state.child_run_id)
                    if state.child_run_id
                    else None
                )
                if child is not None:
                    for claim in ready_claims:
                        self._store_node(
                            run_id,
                            claim.node_id,
                            status="running",
                            child_run_id=state.child_run_id,
                            output=claim.output,
                            expected_state=claim,
                            expected_statuses=("ready",),
                            graph_revision=snapshot.graph.revision,
                        )
                    continue
                if (
                    leader_id
                    and batch_nodes
                    and ready_claims
                    and len(ready_claims) == len(batch_nodes)
                ):
                    batch_nodes.sort(
                        key=lambda item: (
                            0 if item.id == leader_id else 1,
                            item.id,
                        )
                    )
                    claims_by_id = {
                        claim.node_id: claim for claim in ready_claims
                    }
                    selected_model = optimization.model_selections.get(
                        batch_nodes[0].id
                    )
                    self._start_evidence_batch(
                        run_id,
                        snapshot.graph,
                        states,
                        batch_nodes,
                        [claims_by_id[item.id] for item in batch_nodes],
                        selected_model=selected_model,
                    )
                    continue
                # A partial batch descriptor cannot be safely reconstructed.
                for claim in ready_claims:
                    self._store_node(
                        run_id,
                        claim.node_id,
                        status="failed",
                        last_error="evidence_batch_recovery_incomplete",
                        expected_state=claim,
                        expected_statuses=("ready",),
                        graph_revision=snapshot.graph.revision,
                    )
                continue

            if state.child_run_id:
                child = self.agent_service.get(state.child_run_id)
                if child is not None:
                    self._store_node(
                        run_id,
                        node.id,
                        status=(
                            "waiting_for_approval"
                            if child.status == "waiting_for_approval"
                            else "running"
                        ),
                        child_run_id=state.child_run_id,
                        output={
                            **state.output,
                            "child_run_id": state.child_run_id,
                            "status": child.status,
                        },
                        expected_state=state,
                        expected_statuses=("ready",),
                        graph_revision=snapshot.graph.revision,
                    )
                    continue

            if node.kind == "capability":
                self._store_node(
                    run_id,
                    node.id,
                    status="failed",
                    last_error="capability_outcome_unknown_after_coordinator_recovery",
                    expected_state=state,
                    expected_statuses=("ready",),
                    graph_revision=snapshot.graph.revision,
                )
                continue
            self._execute_claimed_node(
                run_id,
                snapshot.graph,
                states,
                node,
                state,
                selected_model=optimization.model_selections.get(node.id),
            )
        return self.advance(run_id)


@lru_cache(maxsize=1)
def default_task_graph_runtime() -> PostgresTaskGraphRuntime:
    return PostgresTaskGraphRuntime()
