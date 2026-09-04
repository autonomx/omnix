from __future__ import annotations

from app.agent_runtime.contracts import ModelRef, WorkspaceSpec
from app.agent_runtime.task_graph import (
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeRunState,
    task_node_fingerprint,
)
from app.agent_runtime.task_graph_revision import (
    merge_task_graph_additive_revision,
    merge_task_graph_continuation,
    plan_graph_revision,
    task_graph_preserves_execution_contract,
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


def test_additive_reparse_cannot_drop_prior_execution_contract() -> None:
    workspace = WorkspaceSpec(
        root="/tmp/omnix",
        repository="/tmp/omnix",
        base_ref="HEAD",
    )
    coding = TaskNode(
        id="coding-1",
        kind="agent",
        profile_id="coding",
        objective="Inspect configuration.",
        semantic_action_intents=["workspace_read"],
        workspace=workspace,
        model=MODEL,
    )
    research = _research_node("research-2")
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[coding, research],
        edges=[
            TaskEdge(
                source=coding.id,
                target=research.id,
                kind="data",
                source_output="result",
                target_input=f"{coding.id}.result",
            )
        ],
    )
    lossy = TaskGraph(
        graph_id="other",
        revision=1,
        user_request_digest="two",
        nodes=[
            TaskNode(
                id="coding-1",
                kind="agent",
                profile_id="coding",
                objective="Run only the focused test.",
                semantic_action_intents=["workspace_execute"],
                workspace=workspace,
                model=MODEL,
            )
        ],
    )

    assert task_graph_preserves_execution_contract(previous, lossy) is False


def test_execution_contract_guard_preserves_same_profile_segment_multiplicity() -> None:
    workspace = WorkspaceSpec(
        root="/tmp/omnix",
        repository="/tmp/omnix",
        base_ref="HEAD",
    )
    first_read = TaskNode(
        id="coding-1",
        kind="agent",
        profile_id="coding",
        objective="Inspect configuration A.",
        semantic_targets=["workspace"],
        semantic_action_intents=["workspace_read"],
        required_local_capabilities=["workspace.read"],
        workspace=workspace,
        model=MODEL,
    )
    research = _research_node("research-2")
    second_read = first_read.model_copy(
        update={"id": "coding-3", "objective": "Inspect configuration B."}
    )
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[first_read, research, second_read],
        edges=[
            TaskEdge(source=first_read.id, target=research.id, kind="data"),
            TaskEdge(source=research.id, target=second_read.id, kind="data"),
        ],
    )
    collapsed = TaskGraph(
        graph_id="graph-2",
        revision=1,
        user_request_digest="two",
        nodes=[first_read, research],
    )
    resegmented = TaskGraph(
        graph_id="graph-3",
        revision=1,
        user_request_digest="three",
        nodes=[
            first_read.model_copy(update={"id": "coding-a"}),
            research.model_copy(update={"id": "research-b"}),
            second_read.model_copy(update={"id": "coding-c"}),
        ],
    )

    assert task_graph_preserves_execution_contract(previous, collapsed) is False
    assert task_graph_preserves_execution_contract(previous, resegmented) is True


def test_additive_revision_appends_later_execution_after_prior_frontier() -> None:
    workspace = WorkspaceSpec(
        root="/tmp/omnix",
        repository="/tmp/omnix",
        base_ref="HEAD",
    )
    coding = TaskNode(
        id="coding-1",
        kind="agent",
        profile_id="coding",
        objective="Inspect configuration.",
        semantic_action_intents=["workspace_read"],
        workspace=workspace,
        model=MODEL,
    )
    research = _research_node("research-2")
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[coding, research],
        edges=[
            TaskEdge(
                source=coding.id,
                target=research.id,
                kind="data",
                source_output="result",
                target_input=f"{coding.id}.result",
            )
        ],
        output_contract={"result_node": research.id},
    )
    addition_node = TaskNode(
        id="coding-1",
        kind="agent",
        profile_id="coding",
        objective="Run the focused configuration test.",
        semantic_action_intents=["workspace_execute"],
        workspace=workspace,
        model=MODEL,
    )
    addition = TaskGraph(
        user_request_digest="two",
        nodes=[addition_node],
        output_contract={"result_node": addition_node.id},
    )

    revised = merge_task_graph_additive_revision(
        previous,
        addition,
        context_dependent=False,
    )

    added_id = "r2-coding-1"
    assert {node.id for node in revised.nodes} >= {
        "coding-1",
        "research-2",
        added_id,
        "join-results",
        "synthesize-results",
    }
    assert any(
        edge.source == "research-2"
        and edge.target == added_id
        and edge.kind == "data"
        for edge in revised.edges
    )
    assert revised.output_contract["result_node"] == "synthesize-results"


def test_additive_read_only_evidence_blocks_existing_terminal_email() -> None:
    market = TaskNode(
        id="trading-research-1",
        kind="agent",
        profile_id="trading-research",
        objective="Get the current market quote.",
        semantic_action_intents=["market_read"],
        model=MODEL,
    )
    email = TaskNode(
        id="personal-assistant-2",
        kind="agent",
        profile_id="personal-assistant",
        objective="Email the final result.",
        semantic_action_intents=["email_send"],
        model=MODEL,
    )
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[market, email],
        edges=[
            TaskEdge(
                source=market.id,
                target=email.id,
                kind="data",
                source_output="result",
                target_input=f"{market.id}.result",
            )
        ],
        output_contract={"result_node": email.id},
    )
    weather = TaskNode(
        id="research-1",
        kind="agent",
        profile_id="research",
        objective="Get the additional weather observation.",
        semantic_action_intents=["research_read"],
        model=MODEL,
    )
    addition = TaskGraph(
        user_request_digest="two",
        nodes=[weather],
        output_contract={"result_node": weather.id},
    )

    revised = merge_task_graph_additive_revision(
        previous,
        addition,
        context_dependent=True,
    )

    assert any(
        edge.source == "r2-research-1"
        and edge.target == email.id
        and edge.kind == "data"
        for edge in revised.edges
    )
    assert not any(
        edge.source == email.id
        and edge.target == "r2-research-1"
        for edge in revised.edges
    )
    assert revised.output_contract["result_node"] == "synthesize-results"


def test_revision_supports_multiple_segments_with_same_profile() -> None:
    workspace = WorkspaceSpec(
        root="/tmp/omnix",
        repository="/tmp/omnix",
        base_ref="HEAD",
    )
    coding_read = TaskNode(
        id="coding-1",
        kind="agent",
        profile_id="coding",
        objective="Inspect repository configuration.",
        semantic_action_intents=["workspace_read"],
        required_local_capabilities=["workspace.read"],
        workspace=workspace,
        model=MODEL,
    )
    research = _research_node("research-2")
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[coding_read, research],
        edges=[
            TaskEdge(
                source=coding_read.id,
                target=research.id,
                kind="data",
                source_output="result",
                target_input=f"{coding_read.id}.result",
            )
        ],
    )

    coding_execute = TaskNode(
        id="coding-3",
        kind="agent",
        profile_id="coding",
        objective="Run the focused configuration test.",
        semantic_action_intents=["workspace_execute"],
        required_local_capabilities=["workspace.command"],
        workspace=workspace,
        model=MODEL,
    )
    revised = TaskGraph(
        graph_id="graph-1",
        revision=2,
        user_request_digest="two",
        nodes=[coding_read, research, coding_execute],
        edges=[
            *previous.edges,
            TaskEdge(
                source=research.id,
                target=coding_execute.id,
                kind="data",
                source_output="result",
                target_input=f"{research.id}.result",
            ),
        ],
    )

    plan = plan_graph_revision(
        previous,
        revised,
        [_state(coding_read, "completed"), _state(research, "running")],
    )

    assert plan.reusable_completed_node_ids == ["coding-1"]
    assert plan.retained_running_node_ids == ["research-2"]
    assert plan.added_node_ids == ["coding-3"]
    assert plan.invalidated_node_ids == []


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


def test_changed_predecessor_invalidates_all_transitive_descendants() -> None:
    source = _research_node("source")
    middle = _research_node("middle")
    leaf = _research_node("leaf")
    edges = [
        TaskEdge(source="source", target="middle", kind="data", target_input="source"),
        TaskEdge(source="middle", target="leaf", kind="data", target_input="middle"),
    ]
    previous = TaskGraph(
        graph_id="graph-1",
        revision=1,
        user_request_digest="one",
        nodes=[source, middle, leaf],
        edges=edges,
    )
    changed_source = source.model_copy(update={"objective": "Research the revised source."})
    revised = TaskGraph(
        graph_id="graph-1",
        revision=2,
        user_request_digest="two",
        nodes=[changed_source, middle, leaf],
        edges=edges,
    )

    plan = plan_graph_revision(
        previous,
        revised,
        [
            _state(source, "completed"),
            _state(middle, "running"),
            _state(leaf, "completed"),
        ],
    )

    assert plan.invalidated_node_ids == ["leaf", "middle", "source"]
    assert plan.reusable_completed_node_ids == []
    assert plan.retained_running_node_ids == []


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
