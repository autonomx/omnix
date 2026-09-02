from __future__ import annotations

from app.agent_runtime.contracts import ModelRef
from app.agent_runtime.task_graph import (
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeRunState,
    task_node_fingerprint,
)
from app.agent_runtime.task_graph_revision import (
    merge_task_graph_continuation,
    plan_graph_revision,
)


MODEL = ModelRef(provider_id="test", model_id="test-model")


def _research_node(
    node_id: str,
    *,
    external: list[str] | None = None,
) -> TaskNode:
    return TaskNode(
        id=node_id,
        kind="agent",
        profile_id="research",
        objective=f"Research {node_id}",
        required_external_capabilities=list(
            external if external is not None else ["research.web_search"]
        ),
        model=MODEL,
        cacheable=True,
    )


def _state(node: TaskNode, status: str) -> TaskNodeRunState:
    return TaskNodeRunState(
        node_id=node.id,
        status=status,
        fingerprint=task_node_fingerprint(node),
    )


def test_revision_reuses_completed_and_retains_unchanged_running_nodes() -> None:
    a = _research_node("a")
    b = _research_node("b")
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[a, b],
    )
    revised = previous.model_copy(
        update={"revision": 2, "user_request_digest": "two"}
    )

    plan = plan_graph_revision(
        previous,
        revised,
        [_state(a, "completed"), _state(b, "running")],
    )

    assert plan.reusable_completed_node_ids == ["a"]
    assert plan.retained_running_node_ids == ["b"]
    assert plan.invalidated_node_ids == []


def test_revision_invalidates_changed_authority_and_detects_reduction() -> None:
    old = _research_node(
        "research",
        external=["research.web_search", "weather.current"],
    )
    new = _research_node(
        "research",
        external=["research.web_search"],
    )
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[old],
    )
    revised = TaskGraph(
        graph_id="graph-1",
        revision=2,
        user_request_digest="two",
        nodes=[new],
    )

    plan = plan_graph_revision(
        previous,
        revised,
        [_state(old, "running")],
    )

    assert plan.reusable_completed_node_ids == []
    assert plan.retained_running_node_ids == []
    assert plan.invalidated_node_ids == ["research"]
    assert plan.authority_reduced_node_ids == ["research"]


def test_revision_detects_removed_and_added_nodes() -> None:
    old = _research_node("old")
    new = _research_node("new")
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[old],
    )
    revised = TaskGraph(
        graph_id="graph-1",
        revision=2,
        user_request_digest="two",
        nodes=[new],
    )

    plan = plan_graph_revision(previous, revised, [_state(old, "completed")])

    assert plan.removed_node_ids == ["old"]
    assert plan.added_node_ids == ["new"]
    assert plan.reusable_completed_node_ids == []


def test_incoming_dependency_change_invalidates_completed_node() -> None:
    source = _research_node("source")
    target = _research_node("target")
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[source, target],
        edges=[],
    )
    revised = TaskGraph(
        graph_id="graph-1",
        revision=2,
        user_request_digest="two",
        nodes=[source, target],
        edges=[
            TaskEdge(
                source="source",
                target="target",
                kind="data",
                target_input="prior",
            )
        ],
    )

    plan = plan_graph_revision(
        previous,
        revised,
        [_state(source, "completed"), _state(target, "completed")],
    )

    assert "source" in plan.reusable_completed_node_ids
    assert "target" in plan.invalidated_node_ids
    assert "target" not in plan.reusable_completed_node_ids


def test_context_dependent_continuation_binds_prior_result_by_data_edge() -> None:
    previous_node = _research_node("previous")
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[previous_node],
        output_contract={"result_node": "previous"},
    )
    addition_node = _research_node("addition")
    addition = TaskGraph(
        user_request_digest="two",
        nodes=[addition_node],
        output_contract={"result_node": "addition"},
    )

    merged = merge_task_graph_continuation(
        previous,
        addition,
        context_dependent=True,
    )

    assert merged.graph_id == "graph-1"
    assert merged.revision == 2
    assert any(
        edge.source == "previous"
        and edge.target == "r2-addition"
        and edge.kind == "data"
        and edge.target_input == "prior_graph_result"
        for edge in merged.edges
    )
    final_result = merged.output_contract["result_node"]
    assert final_result == "synthesize-results-r2"
    synthesis = next(node for node in merged.nodes if node.id == final_result)
    assert synthesis.kind == "synthesis"
    assert any(
        edge.source == "join-results-r2"
        and edge.target == final_result
        and edge.kind == "data"
        for edge in merged.edges
    )


def test_continuation_finishes_in_synthesis_node() -> None:
    model = ModelRef(provider_id="test", model_id="test-model")
    previous_node = TaskNode(
        id="research-1",
        kind="agent",
        profile_id="research",
        objective="Research prior.",
        model=model,
    )
    previous = TaskGraph(
        user_request_digest="prior",
        nodes=[previous_node],
        output_contract={"result_node": previous_node.id},
    )
    added_node = TaskNode(
        id="email-1",
        kind="agent",
        profile_id="personal-assistant",
        objective="Email added result.",
        model=model,
    )
    addition = TaskGraph(
        user_request_digest="addition",
        nodes=[added_node],
        output_contract={"result_node": added_node.id},
        reference_context="current chat context",
    )

    revised = merge_task_graph_continuation(
        previous,
        addition,
        context_dependent=True,
    )

    result_id = revised.output_contract["result_node"]
    result_node = next(node for node in revised.nodes if node.id == result_id)
    assert result_node.kind == "synthesis"
    assert result_node.required_local_capabilities == []
    assert result_node.required_external_capabilities == []
    assert revised.reference_context == "current chat context"
