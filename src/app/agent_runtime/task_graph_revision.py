"""TaskGraph steering/replanning semantics.

Revisions may reuse completed work only when both the node authority envelope and
its incoming dependency contract are identical. Removed or changed authority is
never inherited implicitly.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from .task_graph import TaskGraph, TaskNodeRunState, task_node_fingerprint


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
