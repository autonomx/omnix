"""TaskGraph steering/replanning semantics.

Revisions may reuse completed work only when both the node authority envelope and
its incoming dependency contract are identical. Removed or changed authority is
never inherited implicitly.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from .task_graph import TaskEdge, TaskGraph, TaskNode, TaskNodeRunState, task_node_fingerprint


class TaskGraphRevisionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reusable_completed_node_ids: list[str] = Field(default_factory=list)
    retained_running_node_ids: list[str] = Field(default_factory=list)
    invalidated_node_ids: list[str] = Field(default_factory=list)
    removed_node_ids: list[str] = Field(default_factory=list)
    added_node_ids: list[str] = Field(default_factory=list)
    authority_reduced_node_ids: list[str] = Field(default_factory=list)


def task_node_revision_fingerprint(graph: TaskGraph, node_id: str) -> str:
    node = next(item for item in graph.nodes if item.id == node_id)
    incoming = sorted(
        [
            edge.model_dump(mode="json")
            for edge in graph.edges
            if edge.target == node_id
        ],
        key=lambda row: json.dumps(row, sort_keys=True),
    )
    payload = {
        "node": task_node_fingerprint(node),
        "incoming": incoming,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _authority_set(graph: TaskGraph, node_id: str) -> set[str]:
    node = next(item for item in graph.nodes if item.id == node_id)
    return set(node.required_local_capabilities) | set(node.required_external_capabilities)


def plan_graph_revision(
    previous: TaskGraph,
    revised: TaskGraph,
    node_states: list[TaskNodeRunState],
) -> TaskGraphRevisionPlan:
    if revised.revision != previous.revision + 1:
        raise ValueError("task graph revision must advance exactly once")

    old_nodes = {node.id: node for node in previous.nodes}
    new_nodes = {node.id: node for node in revised.nodes}
    states = {state.node_id: state for state in node_states}

    removed = sorted(set(old_nodes) - set(new_nodes))
    added = sorted(set(new_nodes) - set(old_nodes))
    reusable: list[str] = []
    retained_running: list[str] = []
    invalidated: list[str] = []
    reduced: list[str] = []

    for node_id in sorted(set(old_nodes) & set(new_nodes)):
        old_authority = _authority_set(previous, node_id)
        new_authority = _authority_set(revised, node_id)
        if new_authority < old_authority:
            reduced.append(node_id)

        same_contract = (
            task_node_revision_fingerprint(previous, node_id)
            == task_node_revision_fingerprint(revised, node_id)
        )
        state = states.get(node_id)
        if same_contract and state is not None and state.status == "completed":
            reusable.append(node_id)
        elif (
            same_contract
            and state is not None
            and state.status in {"running", "waiting_for_approval"}
        ):
            retained_running.append(node_id)
        elif not same_contract:
            invalidated.append(node_id)

    return TaskGraphRevisionPlan(
        reusable_completed_node_ids=reusable,
        retained_running_node_ids=retained_running,
        invalidated_node_ids=invalidated,
        removed_node_ids=removed,
        added_node_ids=added,
        authority_reduced_node_ids=reduced,
    )



def merge_task_graph_continuation(
    previous: TaskGraph,
    addition: TaskGraph,
    *,
    context_dependent: bool,
) -> TaskGraph:
    """Add graph work and preserve a user-facing synthesis result."""

    revision = previous.revision + 1
    prefix = f"r{revision}-"
    id_map = {node.id: f"{prefix}{node.id}" for node in addition.nodes}
    renamed_nodes = [
        node.model_copy(update={"id": id_map[node.id]})
        for node in addition.nodes
    ]
    renamed_edges = [
        edge.model_copy(
            update={
                "source": id_map[edge.source],
                "target": id_map[edge.target],
            }
        )
        for edge in addition.edges
    ]

    previous_result = str(
        previous.output_contract.get("result_node")
        or previous.nodes[-1].id
    )
    addition_result_raw = str(
        addition.output_contract.get("result_node")
        or addition.nodes[-1].id
    )
    addition_result = id_map[addition_result_raw]

    if context_dependent:
        addition_incoming = {edge.target for edge in renamed_edges}
        roots = [
            node.id
            for node in renamed_nodes
            if node.id not in addition_incoming
        ]
        for root in roots:
            renamed_edges.append(
                TaskEdge(
                    source=previous_result,
                    target=root,
                    kind="data",
                    source_output="result",
                    target_input="prior_graph_result",
                )
            )

    final_join_id = f"join-results-r{revision}"
    final_join = TaskNode(
        id=final_join_id,
        kind="join",
        objective="Aggregate prior and added graph results without new authority.",
        output_keys=["result"],
    )
    final_edges = [
        TaskEdge(
            source=previous_result,
            target=final_join_id,
            kind="data",
            source_output="result",
            target_input="previous_result",
        ),
        TaskEdge(
            source=addition_result,
            target=final_join_id,
            kind="data",
            source_output="result",
            target_input="addition_result",
        ),
    ]

    synthesis_model = next(
        (
            node.model
            for node in reversed(addition.nodes)
            if node.model is not None
        ),
        None,
    ) or next(
        (
            node.model
            for node in reversed(previous.nodes)
            if node.model is not None
        ),
        None,
    )
    if synthesis_model is None:
        raise ValueError("TaskGraph continuation requires a synthesis model")

    synthesis_id = f"synthesize-results-r{revision}"
    synthesis = TaskNode(
        id=synthesis_id,
        kind="synthesis",
        objective=(
            "Synthesize the prior TaskGraph result and the newly completed "
            "continuation into one final user-facing answer. Use only "
            "predecessor results as reference data and acquire no new authority."
        ),
        semantic_targets=["conversation"],
        semantic_action_intents=[],
        success_criteria=[
            SuccessCriterion(
                id=f"synthesis-complete-r{revision}",
                description=(
                    "Return one faithful final answer covering the retained "
                    "objective and the latest continuation."
                ),
            )
        ],
        model=synthesis_model,
        cacheable=False,
        estimated_cost=0.25,
    )
    final_edges.append(
        TaskEdge(
            source=final_join_id,
            target=synthesis_id,
            kind="data",
            source_output="result",
            target_input="graph_results",
        )
    )
    return TaskGraph(
        graph_id=previous.graph_id,
        revision=revision,
        user_request_digest=addition.user_request_digest,
        nodes=[
            *previous.nodes,
            *renamed_nodes,
            final_join,
            synthesis,
        ],
        edges=[
            *previous.edges,
            *renamed_edges,
            *final_edges,
        ],
        output_contract={"result_node": synthesis_id},
        reference_context=(
            addition.reference_context
            or previous.reference_context
        ),
        max_parallel_nodes=max(
            previous.max_parallel_nodes,
            addition.max_parallel_nodes,
        ),
    )
