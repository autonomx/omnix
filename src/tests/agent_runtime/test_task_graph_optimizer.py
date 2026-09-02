from __future__ import annotations

from app.agent_runtime.contracts import (
    EvidenceCoverage,
    EvidencePolicy,
    EvidenceRequirement,
    EvidenceSourceOption,
    ModelRef,
)
from app.agent_runtime.task_graph import TaskEdge, TaskGraph, TaskNode
from app.agent_runtime.task_graph_optimizer import optimize_task_graph


MODEL = ModelRef(provider_id="test", model_id="default")
FAST_MODEL = ModelRef(provider_id="test", model_id="fast")


def _release_requirement(requirement_id: str, package: str) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=requirement_id,
        source_class="software_release",
        coverage=EvidenceCoverage(
            kind="software_package",
            coverage_key=f"software_package:{package}",
        ),
        freshness="current",
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


def _release_node(node_id: str, requirement: EvidenceRequirement) -> TaskNode:
    return TaskNode(
        id=node_id,
        kind="evidence_read",
        profile_id="research",
        objective=f"Check {node_id}",
        semantic_action_intents=["research_read"],
        required_external_capabilities=["research.web_search"],
        evidence_policy=EvidencePolicy(
            requirement="required",
            requirements=[requirement],
        ),
        model=MODEL,
        cacheable=True,
        estimated_cost=0.5,
    )


def test_optimizer_batches_acquisition_but_preserves_requirement_coverage() -> None:
    react = _release_node("react", _release_requirement("react-release", "react"))
    vue = _release_node("vue", _release_requirement("vue-release", "vue"))
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[react, vue],
        max_parallel_nodes=4,
    )

    plan = optimize_task_graph(graph)

    assert len(plan.evidence_batches) == 1
    batch = plan.evidence_batches[0]
    assert batch.capability_id == "research.web_search"
    assert batch.requirement_ids == ["react-release", "vue-release"]
    assert {
        item.coverage_key for item in batch.coverage
    } == {
        "software_package:react",
        "software_package:vue",
    }
    assert plan.parallel_groups[0] == ["react", "vue"]
    assert set(plan.cache_keys) == {"react", "vue"}


def test_optimizer_never_caches_or_speculates_mutating_nodes() -> None:
    read = _release_node("read", _release_requirement("read-release", "react"))
    mutation = TaskNode(
        id="email",
        kind="agent",
        profile_id="personal-assistant",
        objective="Send the selected result",
        semantic_action_intents=["email_send"],
        required_external_capabilities=["gmail.send_email"],
        model=MODEL,
        cacheable=True,
        estimated_cost=1.0,
    )
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[read, mutation],
        edges=[TaskEdge(source="read", target="email", kind="data")],
    )

    plan = optimize_task_graph(graph)

    assert "read" in plan.cache_keys
    assert "email" not in plan.cache_keys
    assert plan.speculative_read_nodes == ["read"]
    assert plan.parallel_groups == [["read"], ["email"]]


def test_model_override_changes_selection_not_node_authority() -> None:
    read = _release_node("read", _release_requirement("read-release", "react"))
    graph = TaskGraph(user_request_digest="request", nodes=[read])
    authority_before = (
        list(read.required_local_capabilities),
        list(read.required_external_capabilities),
        read.evidence_policy,
    )

    plan = optimize_task_graph(
        graph,
        model_overrides={"research": FAST_MODEL},
    )

    assert plan.model_selections["read"] == FAST_MODEL
    assert (
        list(read.required_local_capabilities),
        list(read.required_external_capabilities),
        read.evidence_policy,
    ) == authority_before


def test_cost_priority_favors_longer_critical_path() -> None:
    first = _release_node("first", _release_requirement("first-release", "react"))
    second = _release_node("second", _release_requirement("second-release", "vue"))
    independent = _release_node(
        "independent",
        _release_requirement("independent-release", "svelte"),
    )
    second = second.model_copy(update={"estimated_cost": 3.0})
    graph = TaskGraph(
        user_request_digest="request",
        nodes=[first, second, independent],
        edges=[TaskEdge(source="first", target="second", kind="data")],
    )

    plan = optimize_task_graph(graph)

    assert plan.cost_priority[0] == "first"
    assert plan.parallel_groups[0] == ["first", "independent"]
    assert plan.parallel_groups[1] == ["second"]
