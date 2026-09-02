from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.contracts import ModelRef
from app.agent_runtime.task_graph import (
    TaskEdge,
    TaskGraph,
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
