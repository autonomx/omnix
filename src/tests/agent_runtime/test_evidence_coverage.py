from __future__ import annotations

from app.agent_runtime.contracts import (
    EvidenceCoverage,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    EvidenceSourceOption,
)
from app.agent_runtime.evidence import (
    evaluate_evidence_set,
    merge_evidence_requirements,
)
from app.agent_runtime.semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticSubject,
    SemanticTask,
    compile_semantic_task,
)


def _coverage(name: str) -> EvidenceCoverage:
    return EvidenceCoverage(
        kind="software_package",
        coverage_key=f"software_package:{name.casefold()}",
    )


def _requirement(
    requirement_id: str,
    package: str,
    *,
    freshness: str = "timeless",
    trust: str = "primary",
    fallback: str = "allow_fallback",
) -> EvidenceRequirement:
    return EvidenceRequirement(
        id=requirement_id,
        source_class="software_release",
        coverage=_coverage(package),
        freshness=freshness,
        trust_floor=trust,
        fallback_policy=fallback,
        acceptable_sources=[
            EvidenceSourceOption(
                source_class="software_release",
                trust_floor=trust,
                preference=0,
            )
        ],
    )


def _receipt(*packages: str) -> EvidenceReceipt:
    return EvidenceReceipt(
        run_id="run-1",
        capability_id="research.web_search",
        source_class="software_release",
        coverage=[_coverage(package) for package in packages],
        request_digest="request",
        source_count=1,
        trust_level="primary",
        result_digest="result",
    )


def test_semantic_compiler_preserves_same_source_class_obligations() -> None:
    task = SemanticTask(
        intent="Compare the latest stable React and Vue releases",
        subjects=[
            SemanticSubject(target="software_release", reference="React"),
            SemanticSubject(target="software_release", reference="Vue"),
        ],
        operations=[
            SemanticOperation(
                kind="compare",
                target="software_release",
                subject_reference="React",
            ),
            SemanticOperation(
                kind="compare",
                target="software_release",
                subject_reference="Vue",
            ),
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="software_release",
                subject_reference="React",
                freshness="current",
                retrieval_mode="lookup",
            ),
            SemanticDataDependency(
                target="software_release",
                subject_reference="Vue",
                freshness="current",
                retrieval_mode="lookup",
            ),
        ],
    )

    compilation = compile_semantic_task(
        "Research the latest stable React and Vue releases using primary sources.",
        task,
    )

    requirements = compilation.evidence_decision.policy.requirements
    assert len(requirements) == 2
    assert len({requirement.id for requirement in requirements}) == 2
    assert {requirement.coverage.coverage_key for requirement in requirements} == {
        "software_package:react",
        "software_package:vue",
    }


def test_receipt_cannot_satisfy_undeclared_same_source_coverage() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            _requirement("react", "React"),
            _requirement("vue", "Vue"),
        ],
    )

    evidence = evaluate_evidence_set("run-1", policy, [_receipt("React")])

    assert evidence.passed is False
    by_id = {row.requirement_id: row for row in evidence.requirements}
    assert by_id["react"].status == "satisfied"
    assert by_id["vue"].status == "wrong_subject"


def test_batched_receipt_must_explicitly_declare_each_coverage() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            _requirement("node", "Node"),
            _requirement("deno", "Deno"),
            _requirement("bun", "Bun"),
        ],
    )

    evidence = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt("Node", "Deno", "Bun")],
    )

    assert evidence.passed is True
    assert {row.status for row in evidence.requirements} == {"satisfied"}


def test_duplicate_obligation_merges_policy_monotonically() -> None:
    merged = merge_evidence_requirements(
        [
            _requirement(
                "react-old",
                "React",
                freshness="timeless",
                trust="reputable",
                fallback="allow_fallback",
            ),
            _requirement(
                "react-new",
                "React",
                freshness="current",
                trust="primary",
                fallback="fail_closed",
            ),
        ]
    )

    assert len(merged) == 1
    requirement = merged[0]
    assert requirement.id == "react-old"
    assert requirement.freshness == "current"
    assert requirement.trust_floor == "primary"
    assert requirement.fallback_policy == "fail_closed"
