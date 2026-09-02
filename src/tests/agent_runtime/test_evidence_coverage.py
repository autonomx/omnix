from __future__ import annotations

from datetime import datetime, timezone

from app.agent_runtime.contracts import (
    EvidenceCoverage,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    EvidenceSourceOption,
)
from app.agent_runtime.evidence import (
    build_evidence_receipt,
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


def _web_result(*snippets: str) -> dict[str, object]:
    return {
        "output": {
            "items": [
                {
                    "url": f"https://github.com/example/{index}",
                    "title": snippet,
                    "snippet": snippet,
                }
                for index, snippet in enumerate(snippets, start=1)
            ]
        }
    }


def test_receipt_builder_never_copies_unobserved_key_coverage() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            _requirement("react", "React"),
            _requirement("vue", "Vue"),
        ],
    )

    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="revision-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "React and Vue stable releases"},
        result_payload=_web_result("React 20.0 stable release"),
        error=None,
        requirement_id="react",
        source_class_hint="software_release",
    )

    assert receipt is not None
    assert {
        item.coverage_key for item in receipt.coverage
    } == {"software_package:react"}


def test_receipt_builder_emits_multiple_only_when_result_observes_each() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            _requirement("react", "React"),
            _requirement("vue", "Vue"),
        ],
    )

    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="revision-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "React and Vue stable releases"},
        result_payload=_web_result(
            "React 20.0 stable release",
            "Vue 4.0 stable release",
        ),
        error=None,
        requirement_id="react",
        source_class_hint="software_release",
    )

    assert receipt is not None
    assert {
        item.coverage_key for item in receipt.coverage
    } == {
        "software_package:react",
        "software_package:vue",
    }


def test_temporal_obligations_do_not_collapse_historical_with_current() -> None:
    current = _requirement("react-current", "React", freshness="current")
    historical = _requirement("react-history", "React").model_copy(
        update={
            "freshness": "as_of_date",
            "as_of_date": datetime(2026, 8, 1, tzinfo=timezone.utc),
        }
    )
    older = historical.model_copy(
        update={
            "id": "react-older",
            "as_of_date": datetime(2026, 7, 1, tzinfo=timezone.utc),
        }
    )

    merged = merge_evidence_requirements([current, historical, older])

    assert len(merged) == 3
    assert {row.freshness for row in merged} == {"current", "as_of_date"}
    assert {
        row.as_of_date
        for row in merged
        if row.freshness == "as_of_date"
    } == {
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        datetime(2026, 7, 1, tzinfo=timezone.utc),
    }


def test_semantic_dependency_supports_explicit_as_of_date() -> None:
    moment = datetime(2026, 8, 1, tzinfo=timezone.utc)
    task = SemanticTask(
        intent="check historical market quote",
        operations=[
            SemanticOperation(
                kind="read",
                target="market_quote",
                subject_reference="GME",
            )
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_quote",
                subject_reference="GME",
                freshness="as_of_date",
                as_of_date=moment,
                retrieval_mode="lookup",
            )
        ],
    )

    compilation = compile_semantic_task(
        "What was GME at the close on August 1, 2026?",
        task,
    )
    requirement = compilation.evidence_decision.policy.requirements[0]

    assert requirement.freshness == "as_of_date"
    assert requirement.as_of_date == moment


def test_web_receipt_subject_is_not_inferred_from_query_when_results_miss_it() -> None:
    requirement = EvidenceRequirement(
        id="gme-news",
        source_class="market_news",
        subject=None,
        coverage=EvidenceCoverage(
            kind="security",
            coverage_key="security:GME:US",
            subject=None,
        ),
        freshness="timeless",
        trust_floor="reputable",
        fallback_policy="allow_fallback",
        acceptable_sources=[
            EvidenceSourceOption(
                source_class="market_news",
                trust_floor="reputable",
                preference=0,
            )
        ],
    )
    policy = EvidencePolicy(requirement="required", requirements=[requirement])

    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="revision-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "latest GME news"},
        result_payload={
            "output": {
                "items": [
                    {
                        "url": "https://example.com/article",
                        "title": "Unrelated market story",
                        "snippet": "A different company reported results.",
                    }
                ]
            }
        },
        error=None,
        requirement_id="gme-news",
        source_class_hint="market_news",
    )

    assert receipt is not None
    assert receipt.subject is None
    assert receipt.coverage == []
