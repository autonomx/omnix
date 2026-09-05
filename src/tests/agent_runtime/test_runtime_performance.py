from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import inspect
import time

from app.agent_runtime.contracts import (
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
)
from app.agent_runtime.evidence import (
    classify_evidence,
    compile_task_authority,
    evaluate_evidence_set,
)
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.router import route_omnix_request
from app.agent_runtime.semantic_task_parser import (
    ProviderSemanticTaskParser,
    _SEMANTIC_TASK_CONTRACT,
)


def test_deterministic_router_budget_for_2000_requests() -> None:
    prompts = [
        "fix the parser tests",
        "check whether the bedroom lamp is on",
        "research today's NVDA catalysts",
        "check my calendar tomorrow",
        "explain TCP congestion control",
    ]
    started = time.perf_counter()
    for index in range(2000):
        route_omnix_request(prompts[index % len(prompts)])
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0, f"deterministic routing took {elapsed:.3f}s"


def test_authority_compiler_budget_for_500_requests() -> None:
    cases = [
        (
            "coding",
            "inspect and fix the parser tests",
            ("workspace_read", "workspace_mutate", "workspace_execute"),
        ),
        (
            "house",
            "check the bedroom lamp and turn it off",
            ("home_read", "home_mutate"),
        ),
        (
            "research",
            "research the latest Python release",
            ("research_read",),
        ),
        (
            "personal-assistant",
            "check my calendar and schedule a meeting",
            ("calendar_read", "calendar_create"),
        ),
        (
            "trading-research",
            "research today's NVDA catalysts",
            ("market_read",),
        ),
    ]
    started = time.perf_counter()
    for index in range(500):
        profile_id, task, actions = cases[index % len(cases)]
        decision = classify_evidence(task, profile_id=profile_id)
        compile_task_authority(
            get_agent_profile(profile_id),
            task,
            decision,
            semantic_action_intents=actions,
        )
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0, f"authority compilation took {elapsed:.3f}s"


def test_evidence_evaluation_budget_for_dense_receipt_set() -> None:
    requirements = [
        EvidenceRequirement(
            id=f"req-{index}",
            source_class="general_current_web",
            trust_floor="reputable",
        )
        for index in range(100)
    ]
    policy = EvidencePolicy(requirement="required", requirements=requirements)
    now = datetime.now(timezone.utc)
    receipts = [
        EvidenceReceipt(
            receipt_id=f"receipt-{index}",
            run_id="load",
            capability_id="research.web_search",
            source_class="general_current_web",
            request_digest=f"request-{index}",
            result_digest=f"result-{index}",
            trust_level="reputable",
            observed_at=now,
            executed_at=now,
            source_count=1,
        )
        for index in range(200)
    ]

    started = time.perf_counter()
    result = evaluate_evidence_set("load", policy, receipts, now=now)
    elapsed = time.perf_counter() - started

    assert result.passed is True
    assert elapsed < 5.0, f"evidence evaluation took {elapsed:.3f}s"


def test_50_concurrent_authority_compilations_complete_without_shared_state() -> None:
    def compile_one(index: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
        profile_id = "research" if index % 2 == 0 else "trading-research"
        task = (
            "research the latest Python release"
            if profile_id == "research"
            else "research today's NVDA catalysts"
        )
        actions = ("research_read",) if profile_id == "research" else ("market_read",)
        decision = classify_evidence(task, profile_id=profile_id)
        compiled = compile_task_authority(
            get_agent_profile(profile_id),
            task,
            decision,
            semantic_action_intents=actions,
        )
        return compiled.required_local, compiled.required_external

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(compile_one, range(50)))
    elapsed = time.perf_counter() - started

    assert len(results) == 50
    assert all(external for _local, external in results)
    assert elapsed < 5.0, f"concurrent authority compilation took {elapsed:.3f}s"


def test_semantic_task_parser_response_token_budget_is_bounded() -> None:
    assert _SEMANTIC_TASK_CONTRACT.max_tokens <= 420


def test_semantic_task_parser_retry_budget_is_bounded() -> None:
    source = inspect.getsource(ProviderSemanticTaskParser.parse_contextual)
    assert "max_provider_calls=2" in source
    assert "max_transport_retries=1" in source
    assert "max_validation_regenerations=1" in source
    assert "deadline_seconds=max(0.001, deadline_seconds)" in source
