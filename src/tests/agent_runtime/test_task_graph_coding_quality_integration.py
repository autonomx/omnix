from __future__ import annotations

from app.agent_runtime.contracts import (
    AcceptancePlan,
    AgentRunSnapshot,
    ModelRef,
    WorkspaceSpec,
)
from app.agent_runtime.task_graph import (
    TaskGraph,
    TaskGraphRunSnapshot,
    TaskNode,
    TaskNodeRunState,
    task_node_fingerprint,
)
from app.agent_runtime.task_graph_runtime import PostgresTaskGraphRuntime


MODEL = ModelRef(provider_id="test", model_id="quality-model", reasoning_effort="high")


def _coding_node() -> TaskNode:
    return TaskNode(
        id="implement",
        kind="agent",
        profile_id="coding",
        objective="Fix the behavior and add a regression test.",
        semantic_targets=["workspace"],
        semantic_action_intents=["workspace_mutate", "workspace_execute"],
        required_local_capabilities=[
            "workspace.read",
            "workspace.search",
            "workspace.edit",
            "workspace.test",
        ],
        workspace=WorkspaceSpec(
            root="/tmp/omnix-quality-repo",
            repository="/tmp/omnix-quality-repo",
        ),
        model=MODEL,
        acceptance_plan=AcceptancePlan(
            required_artifacts=["diff"],
            require_diff=True,
            checks=["successful_test_command"],
        ),
    )


def test_mutating_task_graph_coding_node_inherits_inner_quality_pipeline() -> None:
    runtime = object.__new__(PostgresTaskGraphRuntime)
    node = _coding_node()
    spec = runtime._agent_spec(node, child_run_id="child-quality")

    # TaskGraph does not recreate completion quality as outer graph nodes. The
    # child RunSpec enters the same coding AgentRunService and therefore carries
    # the normal strict quality controller by default.
    assert spec.profile == "coding"
    assert spec.expected_artifacts == ["diff"]
    assert spec.quality_policy == "strict"
    assert spec.quality_reserve_fraction == 0.25
    assert spec.acceptance_plan is not None
    assert spec.acceptance_plan.require_diff


def test_task_graph_does_not_complete_node_while_quality_controller_reviews() -> None:
    node = _coding_node()
    graph = TaskGraph(
        graph_id="quality-graph",
        user_request_digest="request",
        nodes=[node],
        output_contract={"result_node": node.id},
    )
    state = TaskNodeRunState(
        node_id=node.id,
        status="running",
        child_run_id="child-quality",
        fingerprint=task_node_fingerprint(node),
    )
    snapshot = TaskGraphRunSnapshot(
        run_id="graph-run",
        graph=graph,
        status="running",
        node_states=[state],
    )
    child_spec = object.__new__(PostgresTaskGraphRuntime)._agent_spec(
        node,
        child_run_id="child-quality",
    )
    child = AgentRunSnapshot(
        run_id="child-quality",
        spec=child_spec,
        status="waiting_for_children",
        quality_stage="reviewing",
        quality_attempt=1,
        workspace_state_id="state-final",
    )

    class _AgentService:
        @staticmethod
        def get(run_id: str):
            assert run_id == "child-quality"
            return child

    runtime = object.__new__(PostgresTaskGraphRuntime)
    runtime._agent_service = _AgentService()
    stored: list[tuple[tuple, dict]] = []
    runtime._store_node = lambda *args, **kwargs: stored.append((args, kwargs))

    runtime._poll_children(snapshot)

    # waiting_for_children is deliberately non-terminal. Independent review and
    # repair remain invisible to the outer scheduler until Omnix quality
    # acceptance changes the child run itself to completed.
    assert stored == []


def test_task_graph_only_projects_completion_after_child_quality_completion() -> None:
    node = _coding_node()
    graph = TaskGraph(
        graph_id="quality-graph-complete",
        user_request_digest="request",
        nodes=[node],
        output_contract={"result_node": node.id},
    )
    state = TaskNodeRunState(
        node_id=node.id,
        status="running",
        child_run_id="child-quality",
        fingerprint=task_node_fingerprint(node),
    )
    snapshot = TaskGraphRunSnapshot(
        run_id="graph-run",
        graph=graph,
        status="running",
        node_states=[state],
    )
    child_spec = object.__new__(PostgresTaskGraphRuntime)._agent_spec(
        node,
        child_run_id="child-quality",
    )
    child = AgentRunSnapshot(
        run_id="child-quality",
        spec=child_spec,
        status="completed",
        quality_stage="acceptance",
        quality_attempt=1,
        workspace_state_id="state-final",
    )

    class _AgentService:
        @staticmethod
        def get(_run_id: str):
            return child

        @staticmethod
        def artifacts(_run_id: str):
            return []

        @staticmethod
        def events(_run_id: str, *, after_sequence: int = 0):
            del after_sequence
            return []

    runtime = object.__new__(PostgresTaskGraphRuntime)
    runtime._agent_service = _AgentService()
    stored: list[dict] = []
    runtime._store_node = lambda *args, **kwargs: stored.append(kwargs)

    runtime._poll_children(snapshot)

    assert len(stored) == 1
    assert stored[0]["status"] == "completed"
    assert stored[0]["output"]["status"] == "completed"
