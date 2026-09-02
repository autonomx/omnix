from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.contracts import (
    EvidenceCoverage,
    EvidencePolicy,
    EvidenceRequirement,
    EvidenceSourceOption,
    ModelRef,
)
from app.agent_runtime.task_graph import (
    TaskEdge,
    TaskGraph,
    TaskGraphRunSnapshot,
    TaskNode,
    TaskNodeRunState,
    task_node_fingerprint,
)
from app.agent_runtime.task_graph_runtime import PostgresTaskGraphRuntime


MODEL = ModelRef(provider_id="test", model_id="test-model")


class _FakeAgentService:
    def __init__(self) -> None:
        self.spec = None
        self.reference_context = None

    def start_with_context(self, spec, *, reference_context: str):
        self.spec = spec
        self.reference_context = reference_context
        return SimpleNamespace(run_id=spec.run_id)


class _HarnessRuntime(PostgresTaskGraphRuntime):
    def __init__(self, service: _FakeAgentService) -> None:
        self._agent_service = service
        self.model_overrides = {}
        self.stored: list[dict[str, object]] = []

    def _store_node(self, run_id, node_id, **kwargs):
        self.stored.append(
            {"run_id": run_id, "node_id": node_id, **kwargs}
        )
        return SimpleNamespace(
            node_id=node_id,
            status=kwargs["status"],
            child_run_id=kwargs.get("child_run_id"),
        )


def test_predecessor_outputs_are_reference_data_not_child_authority() -> None:
    source = TaskNode(
        id="source",
        kind="join",
        objective="Aggregate source data.",
    )
    target = TaskNode(
        id="target",
        kind="agent",
        profile_id="research",
        objective="Research only the scoped target.",
        required_external_capabilities=["research.web_search"],
        model=MODEL,
    )
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[source, target],
        edges=[
            TaskEdge(
                source="source",
                target="target",
                kind="data",
                target_input="prior_result",
            )
        ],
    )
    states = {
        "source": TaskNodeRunState(
            node_id="source",
            status="completed",
            output={"result": "REFERENCE-DATA"},
            fingerprint=task_node_fingerprint(source),
        ),
        "target": TaskNodeRunState(
            node_id="target",
            status="ready",
            child_run_id="child-1",
            fingerprint=task_node_fingerprint(target),
        ),
    }
    service = _FakeAgentService()
    runtime = _HarnessRuntime(service)

    runtime._execute_claimed_node(
        "graph-run",
        graph,
        states,
        target,
        states["target"],
    )

    assert service.spec is not None
    assert service.spec.task == "Research only the scoped target."
    assert service.spec.external_capabilities == ["research.web_search"]
    assert "REFERENCE-DATA" not in service.spec.task
    assert "REFERENCE-DATA" in str(service.reference_context)
    assert "not execution authority" in str(service.reference_context)
    assert runtime.stored[-1]["status"] == "running"
    assert runtime.stored[-1]["child_run_id"] == "child-1"


def test_readiness_waits_for_declared_dependencies() -> None:
    source = TaskNode(id="source", kind="join", objective="Source")
    target = TaskNode(id="target", kind="join", objective="Target")
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[source, target],
        edges=[TaskEdge(source="source", target="target", kind="data")],
    )
    runtime = object.__new__(PostgresTaskGraphRuntime)

    pending = {
        "source": TaskNodeRunState(
            node_id="source",
            status="running",
            fingerprint=task_node_fingerprint(source),
        ),
        "target": TaskNodeRunState(
            node_id="target",
            status="pending",
            fingerprint=task_node_fingerprint(target),
        ),
    }
    assert runtime._readiness(graph, pending, target) == (False, False)

    completed = dict(pending)
    completed["source"] = pending["source"].model_copy(
        update={"status": "completed"}
    )
    assert runtime._readiness(graph, completed, target) == (True, False)


def test_deterministic_conditions_do_not_evaluate_arbitrary_code() -> None:
    runtime = object.__new__(PostgresTaskGraphRuntime)

    assert runtime._condition("exists:value", {"value": 1}) is True
    assert runtime._condition("not truthy:value", {"value": 0}) is True

    try:
        runtime._condition("__import__('os').system('echo unsafe')", {})
    except Exception as exc:
        assert "unsupported deterministic condition" in str(exc)
    else:
        raise AssertionError("arbitrary condition expression must fail closed")


def test_child_result_uses_latest_visible_message_end() -> None:
    service = _FakeAgentService()
    service.events = lambda run_id, after_sequence=0: [
        SimpleNamespace(
            event_type="model.message",
            payload={"phase": "message_end", "text": "first"},
        ),
        SimpleNamespace(
            event_type="model.message",
            payload={"phase": "message_update", "text": "ignored"},
        ),
        SimpleNamespace(
            event_type="model.message",
            payload={"phase": "message_end", "text": "final answer"},
        ),
    ]
    runtime = _HarnessRuntime(service)

    assert runtime._child_result("child-1") == "final answer"


def test_optimizer_order_is_consumed_by_runtime_scheduler() -> None:
    cheap = TaskNode(
        id="cheap",
        kind="agent",
        profile_id="research",
        objective="Cheap",
        model=MODEL,
        cacheable=True,
        estimated_cost=0.1,
    )
    critical = TaskNode(
        id="critical",
        kind="agent",
        profile_id="research",
        objective="Critical",
        model=MODEL,
        cacheable=True,
        estimated_cost=5.0,
    )
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[cheap, critical],
    )
    runtime = object.__new__(PostgresTaskGraphRuntime)
    runtime.model_overrides = {}

    plan = runtime._optimization_plan(graph)
    ordered = runtime._optimized_nodes(graph, plan)

    assert [node.id for node in ordered] == ["critical", "cheap"]


def test_runtime_model_selection_changes_child_model_not_authority() -> None:
    target = TaskNode(
        id="target",
        kind="agent",
        profile_id="research",
        objective="Research target.",
        required_external_capabilities=["research.web_search"],
        model=MODEL,
    )
    graph = TaskGraph(user_request_digest="request", nodes=[target])
    state = TaskNodeRunState(
        node_id="target",
        status="ready",
        child_run_id="child-override",
        fingerprint=task_node_fingerprint(target),
    )
    service = _FakeAgentService()
    runtime = _HarnessRuntime(service)
    override = ModelRef(provider_id="test", model_id="fast-model")

    runtime._execute_claimed_node(
        "graph-run",
        graph,
        {"target": state},
        target,
        state,
        selected_model=override,
    )

    assert service.spec is not None
    assert service.spec.model == override
    assert service.spec.external_capabilities == ["research.web_search"]


def _release_requirement(requirement_id: str, package: str) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=requirement_id,
        source_class="software_release",
        coverage=EvidenceCoverage(
            kind="software_package",
            coverage_key=f"software_package:{package.casefold()}",
        ),
        freshness="timeless",
        trust_floor="primary",
        fallback_policy="allow_fallback",
        acceptable_sources=[
            EvidenceSourceOption(
                source_class="software_release",
                trust_floor="primary",
                preference=0,
            )
        ],
    )


def test_optimizer_exposes_authority_equivalent_evidence_batch_to_runtime() -> None:
    react = TaskNode(
        id="react",
        kind="evidence_read",
        profile_id="research",
        objective="Find React release.",
        required_external_capabilities=["research.web_search"],
        evidence_policy=EvidencePolicy(
            requirement="required",
            requirements=[_release_requirement("react-release", "React")],
        ),
        model=MODEL,
        cacheable=True,
    )
    vue = TaskNode(
        id="vue",
        kind="evidence_read",
        profile_id="research",
        objective="Find Vue release.",
        required_external_capabilities=["research.web_search"],
        evidence_policy=EvidencePolicy(
            requirement="required",
            requirements=[_release_requirement("vue-release", "Vue")],
        ),
        model=MODEL,
        cacheable=True,
    )
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[react, vue],
    )
    states = {
        node.id: TaskNodeRunState(
            node_id=node.id,
            status="pending",
            fingerprint=task_node_fingerprint(node),
        )
        for node in graph.nodes
    }
    runtime = object.__new__(PostgresTaskGraphRuntime)
    runtime.model_overrides = {}
    plan = runtime._optimization_plan(graph)

    batch, candidates = runtime._batch_candidates(
        graph,
        states,
        react,
        plan,
    )

    assert batch is not None
    assert [node.id for node in candidates] == ["react", "vue"]
    merged = runtime._merged_evidence_batch_node(
        candidates,
        selected_model=MODEL,
    )
    assert {
        requirement.id
        for requirement in merged.evidence_policy.requirements
    } == {"react-release", "vue-release"}
    assert merged.required_external_capabilities == ["research.web_search"]


def test_synthesis_node_uses_internal_model_profile_without_tool_authority() -> None:
    synthesis = TaskNode(
        id="synthesize-results",
        kind="synthesis",
        objective="Synthesize results only.",
        model=MODEL,
    )
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[synthesis],
        output_contract={"result_node": synthesis.id},
    )
    state = TaskNodeRunState(
        node_id=synthesis.id,
        status="ready",
        child_run_id="synthesis-child",
        fingerprint=task_node_fingerprint(synthesis),
    )
    service = _FakeAgentService()
    runtime = _HarnessRuntime(service)

    runtime._execute_claimed_node(
        "graph-run",
        graph,
        {synthesis.id: state},
        synthesis,
        state,
    )

    assert service.spec is not None
    assert service.spec.profile == "research"
    assert service.spec.capabilities == []
    assert service.spec.external_capabilities == []
    assert service.spec.evidence_policy.requirement == "none"


def test_recover_ready_node_adopts_existing_child_instead_of_starting_twice() -> None:
    node = TaskNode(
        id="research",
        kind="agent",
        profile_id="research",
        objective="Research current facts.",
        model=MODEL,
    )
    graph = TaskGraph(user_request_digest="request", nodes=[node])
    state = TaskNodeRunState(
        node_id=node.id,
        status="ready",
        child_run_id="existing-child",
        fingerprint=task_node_fingerprint(node),
    )
    snapshot = TaskGraphRunSnapshot(
        run_id="graph-run",
        graph=graph,
        status="running",
        node_states=[state],
    )
    service = _FakeAgentService()
    service.get = lambda run_id: SimpleNamespace(
        run_id=run_id,
        status="running",
        last_error=None,
    )
    runtime = _HarnessRuntime(service)
    runtime.get_status = lambda run_id: snapshot
    runtime.advance = lambda run_id: snapshot

    recovered = runtime.recover("graph-run")

    assert recovered is snapshot
    assert service.spec is None
    assert runtime.stored[-1]["node_id"] == node.id
    assert runtime.stored[-1]["status"] == "running"
    assert runtime.stored[-1]["child_run_id"] == "existing-child"


def test_poll_child_waiting_for_approval_projects_graph_node_state() -> None:
    node = TaskNode(
        id="email",
        kind="agent",
        profile_id="personal-assistant",
        objective="Send the approved email.",
        model=MODEL,
    )
    graph = TaskGraph(user_request_digest="request", nodes=[node])
    state = TaskNodeRunState(
        node_id=node.id,
        status="running",
        child_run_id="child-approval",
        fingerprint=task_node_fingerprint(node),
    )
    service = _FakeAgentService()
    service.get = lambda run_id: SimpleNamespace(
        run_id=run_id,
        status="waiting_for_approval",
        last_error=None,
    )
    service.approvals = lambda run_id, state=None: [
        SimpleNamespace(
            approval_id="approval-1",
            model_dump=lambda mode="json": {
                "approval_id": "approval-1",
                "capability_id": "gmail.send_email",
                "request_payload": {"command": "send email"},
            },
        )
    ]
    runtime = _HarnessRuntime(service)

    runtime._poll_children(
        TaskGraphRunSnapshot(
            run_id="graph-run",
            graph=graph,
            status="running",
            node_states=[state],
        )
    )

    stored = runtime.stored[-1]
    assert stored["status"] == "waiting_for_approval"
    assert stored["output"]["pending_approvals"][0]["approval_id"] == "approval-1"


def test_required_graph_failure_cancels_live_sibling_children() -> None:
    failed = TaskNode(
        id="failed",
        kind="agent",
        profile_id="research",
        objective="Fail",
        model=MODEL,
    )
    sibling = TaskNode(
        id="sibling",
        kind="agent",
        profile_id="research",
        objective="Still running",
        model=MODEL,
    )
    failed_state = TaskNodeRunState(
        node_id=failed.id,
        status="failed",
        last_error="boom",
        fingerprint=task_node_fingerprint(failed),
    )
    sibling_state = TaskNodeRunState(
        node_id=sibling.id,
        status="running",
        child_run_id="live-child",
        fingerprint=task_node_fingerprint(sibling),
    )
    snapshot = TaskGraphRunSnapshot(
        run_id="graph-run",
        graph=TaskGraph(
            user_request_digest="request",
            nodes=[failed, sibling],
        ),
        status="running",
        node_states=[failed_state, sibling_state],
    )
    runtime = _HarnessRuntime(_FakeAgentService())
    cancelled: list[str] = []
    runtime._cancel_child = lambda run_id: cancelled.append(run_id)
    runtime.get_status = lambda run_id: snapshot
    runtime._set_run_status = lambda current, status, last_error=None: current.model_copy(
        update={"status": status, "last_error": last_error}
    )

    result = runtime._fail_graph(snapshot, last_error="required node failed")

    assert cancelled == ["live-child"]
    assert any(
        row["node_id"] == "sibling" and row["status"] == "cancelled"
        for row in runtime.stored
    )
    assert result.status == "failed"
