from __future__ import annotations

import pytest

from app.agent_runtime.contracts import (
    EvidenceCoverage,
    EvidencePolicy,
    EvidenceRequirement,
    EvidenceSourceOption,
    ModelRef,
)
from app.agent_runtime.evidence import build_evidence_receipt, evaluate_evidence_set
from app.agent_runtime.semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticTask,
)
from app.agent_runtime.task_graph import TaskEdge, TaskGraph, TaskNode, compile_task_graph
from app.assistant_tools.repo_adapter import GitHubCliRuntimeAdapter


MODEL = ModelRef(provider_id="test", model_id="test-model")


def _release_policy() -> EvidencePolicy:
    requirement = EvidenceRequirement(
        id="react-release",
        source_class="software_release",
        coverage=EvidenceCoverage(
            kind="software_package",
            coverage_key="software_package:react",
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
    return EvidencePolicy(requirement="required", requirements=[requirement])


def _web_receipt(*, url: str, title: str, snippet: str):
    return build_evidence_receipt(
        run_id="run-1",
        task_revision_id="revision-1",
        policy=_release_policy(),
        capability_id="research.web_search",
        request_input={"query": "React stable release"},
        result_payload={
            "output": {
                "items": [
                    {
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                        "metadata": {"query": "React stable release"},
                    }
                ]
            }
        },
        error=None,
        requirement_id="react-release",
        source_class_hint="software_release",
    )


def test_fallback_result_title_and_metadata_cannot_prove_query_subject() -> None:
    receipt = _web_receipt(
        url="https://example.com/unrelated",
        title="React stable release",
        snippet="An unrelated project published a new version.",
    )
    assert receipt is not None
    assert receipt.coverage == []


def test_arbitrary_github_repository_is_not_primary_release_evidence() -> None:
    receipt = _web_receipt(
        url="https://github.com/example/react/releases/tag/v99",
        title="React v99",
        snippet="React published version 99.",
    )
    assert receipt is not None
    assert receipt.trust_level == "reputable"
    evidence = evaluate_evidence_set("run-1", _release_policy(), [receipt])
    assert evidence.passed is False
    assert evidence.requirements[0].status == "insufficient_trust"


def test_known_upstream_github_repository_can_be_primary_release_evidence() -> None:
    receipt = _web_receipt(
        url="https://github.com/facebook/react/releases/tag/v20.0.0",
        title="React v20",
        snippet="React published version 20.0.0.",
    )
    assert receipt is not None
    assert receipt.trust_level == "primary"
    assert evaluate_evidence_set("run-1", _release_policy(), [receipt]).passed is True


def test_dependency_only_read_precedes_explicit_read_consumer() -> None:
    task = SemanticTask(
        intent="read filing then research release",
        operations=[
            SemanticOperation(
                kind="research",
                target="software_release",
                subject_reference="React",
            )
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_filing",
                subject_reference="GME",
                freshness="current",
                retrieval_mode="lookup",
            )
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )
    compiled = compile_task_graph(
        "Use the current GME filing context, then research the React release.",
        task,
        model=MODEL,
    )
    assert compiled.ok is True
    assert compiled.graph is not None
    trading = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "trading-research"
    )
    research = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "research"
    )
    assert any(
        edge.source == trading.id
        and edge.target == research.id
        and edge.kind == "data"
        for edge in compiled.graph.edges
    )


def test_capability_node_requires_exact_explicit_broker_authority() -> None:
    with pytest.raises(ValueError, match="explicitly issue exactly"):
        TaskNode(
            id="ci",
            kind="capability",
            capability_id="github.inspect_ci",
            input_template={"repository": "autonomx/omnix", "ref": "main"},
        )

    node = TaskNode(
        id="ci",
        kind="capability",
        capability_id="github.inspect_ci",
        required_external_capabilities=["github.inspect_ci"],
        input_template={"repository": "autonomx/omnix", "ref": "main"},
    )
    assert node.required_external_capabilities == ["github.inspect_ci"]


def test_capability_node_cannot_consume_predecessor_data() -> None:
    source = TaskNode(id="source", kind="join", objective="source")
    capability = TaskNode(
        id="ci",
        kind="capability",
        capability_id="github.inspect_ci",
        required_external_capabilities=["github.inspect_ci"],
        input_template={"repository": "autonomx/omnix", "ref": "main"},
    )
    with pytest.raises(ValueError, match="cannot consume predecessor data"):
        TaskGraph(
            user_request_digest="request",
            nodes=[source, capability],
            edges=[
                TaskEdge(
                    source="source",
                    target="ci",
                    kind="data",
                    target_input="repository",
                )
            ],
        )


def test_ci_adapter_resolves_immutable_sha_and_paginates_all_status_surfaces() -> None:
    adapter = object.__new__(GitHubCliRuntimeAdapter)
    adapter.timeout = 30.0
    commit_sha = "a" * 40
    calls: list[str] = []

    def fake_gh(args, *, timeout=None):
        del timeout
        endpoint = str(args[-1])
        calls.append(endpoint)
        if endpoint == "repos/autonomx/omnix/commits/main":
            return {"sha": commit_sha}
        if "check-runs?per_page=100&page=1" in endpoint:
            return {
                "total_count": 101,
                "check_runs": [
                    {
                        "id": index,
                        "name": f"check-{index}",
                        "status": "completed",
                        "conclusion": "success",
                        "app": {"slug": "actions"},
                    }
                    for index in range(1, 101)
                ],
            }
        if "check-runs?per_page=100&page=2" in endpoint:
            return {
                "total_count": 101,
                "check_runs": [
                    {
                        "id": 101,
                        "name": "check-101",
                        "status": "completed",
                        "conclusion": "success",
                        "app": {"slug": "actions"},
                    }
                ],
            }
        if "statuses?per_page=100&page=1" in endpoint:
            return [{"context": "legacy/status", "state": "success"}]
        raise AssertionError(endpoint)

    adapter._gh = fake_gh
    result = adapter.inspect_ci(repository="autonomx/omnix", ref="main")
    assert result["requested_ref"] == "main"
    assert result["resolved_commit"] == commit_sha
    assert result["checks_passed"] is True
    assert len(result["checks"]) == 101
    assert any("check-runs?per_page=100&page=2" in call for call in calls)
    assert result["statuses"] == [
        {"context": "legacy/status", "state": "success", "description": None}
    ]


def test_ci_adapter_does_not_treat_neutral_as_success() -> None:
    adapter = object.__new__(GitHubCliRuntimeAdapter)
    adapter.timeout = 30.0

    def fake_gh(args, *, timeout=None):
        del timeout
        endpoint = str(args[-1])
        if endpoint.endswith("/commits/main"):
            return {"sha": "b" * 40}
        if "check-runs?" in endpoint:
            return {
                "total_count": 1,
                "check_runs": [
                    {
                        "id": 1,
                        "name": "required",
                        "status": "completed",
                        "conclusion": "neutral",
                        "app": {"slug": "actions"},
                    }
                ],
            }
        if "statuses?" in endpoint:
            return []
        raise AssertionError(endpoint)

    adapter._gh = fake_gh
    result = adapter.inspect_ci(repository="autonomx/omnix", ref="main")
    assert result["checks_passed"] is False
