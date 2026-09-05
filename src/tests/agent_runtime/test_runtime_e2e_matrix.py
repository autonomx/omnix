from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agent_runtime.acceptance import evaluate_acceptance
from app.agent_runtime.contracts import (
    AgentArtifact,
    AgentEvent,
    AgentRunSpec,
    EvidenceReceipt,
    ModelRef,
    SuccessCriterion,
)
from app.agent_runtime.evidence import (
    classify_evidence,
    compile_task_authority,
    evaluate_evidence_set,
)
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.router import route_omnix_request


def _receipt(run_id: str, requirement) -> EvidenceReceipt:
    now = datetime.now(timezone.utc)
    return EvidenceReceipt(
        run_id=run_id,
        capability_id="test.evidence",
        source_class=requirement.source_class,
        subject=requirement.subject,
        request_digest=f"request:{requirement.id}",
        result_digest=f"result:{requirement.id}",
        trust_level=requirement.trust_floor,
        observed_at=now,
        executed_at=now,
        freshest_source_at=now,
    )


@pytest.mark.parametrize(
    "prompt,profile_id,actions,expected_source,expected_external",
    [
        (
            "/agent research the latest stable Python release",
            "research",
            ("research_read",),
            "software_release",
            {"research.web_search"},
        ),
        (
            "/agent check whether the bedroom lamp is on and turn it off",
            "house",
            ("home_read", "home_mutate"),
            "home_state",
            {"home.get_state", "home.set_state"},
        ),
        (
            "/agent check my calendar tomorrow and schedule a meeting with Sam",
            "personal-assistant",
            ("calendar_read", "calendar_create"),
            "calendar_state",
            {"calendar.read_availability", "calendar.create_event"},
        ),
        (
            "/agent research today's NVDA catalysts",
            "trading-research",
            ("market_read",),
            "market_news",
            {"research.web_search"},
        ),
    ],
)
def test_route_to_evidence_to_authority_to_acceptance(
    prompt: str,
    profile_id: str,
    actions: tuple[str, ...],
    expected_source: str,
    expected_external: set[str],
) -> None:
    route = route_omnix_request(prompt)
    assert route.lane == "agent"

    task = prompt.removeprefix("/agent ").strip()
    evidence = classify_evidence(task, profile_id=profile_id)
    assert any(
        requirement.source_class == expected_source
        for requirement in evidence.policy.requirements
    )

    compiled = compile_task_authority(
        get_agent_profile(profile_id),
        task,
        evidence,
        semantic_action_intents=actions,
    )
    assert expected_external <= set(compiled.required_external)

    receipts = [
        _receipt("run-e2e", requirement)
        for requirement in evidence.policy.requirements
    ]
    evidence_set = evaluate_evidence_set("run-e2e", evidence.policy, receipts)
    assert evidence_set.passed is True

    spec = AgentRunSpec(
        run_id="run-e2e",
        task=task,
        objective=task,
        profile=profile_id,
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=list(compiled.required_local),
        external_capabilities=list(compiled.required_external),
        evidence_policy=evidence.policy,
    )
    acceptance = evaluate_acceptance(
        spec,
        events=[],
        artifacts=[],
        evidence_set=evidence_set,
    )
    assert acceptance.passed is True


def test_coding_e2e_requires_mutation_artifact_and_successful_test() -> None:
    prompt = "/agent fix the parser tests and run pytest"
    route = route_omnix_request(prompt)
    assert route.lane == "agent"

    task = prompt.removeprefix("/agent ").strip()
    evidence = classify_evidence(task, profile_id="coding")
    compiled = compile_task_authority(
        get_agent_profile("coding"),
        task,
        evidence,
        semantic_action_intents=("workspace_mutate", "workspace_execute"),
    )
    local = set(compiled.required_local)
    assert {"workspace.edit", "workspace.test"} <= local

    spec = AgentRunSpec(
        run_id="coding-e2e",
        task=task,
        objective=task,
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=list(compiled.required_local),
        evidence_policy=evidence.policy,
        expected_artifacts=["diff"],
        success_criteria=[
            SuccessCriterion(id="tests", description="Targeted tests pass")
        ],
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "pytest",
                "tool": "bash",
                "args": {"command": "python -m pytest src/tests/parser -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={
                "tool_call_id": "pytest",
                "tool": "bash",
                "is_error": False,
                "result": {"details": {"exitCode": 0}},
            },
        ),
    ]
    artifacts = [
        AgentArtifact(
            run_id=spec.run_id,
            kind="diff",
            name="workspace.diff",
        )
    ]

    result = evaluate_acceptance(spec, events=events, artifacts=artifacts)
    assert result.passed is True
    assert result.checks["diff_artifact"] is True
    assert result.checks["successful_test_command"] is True


def test_coding_e2e_rejects_model_completion_without_omnix_artifacts() -> None:
    spec = AgentRunSpec(
        run_id="coding-e2e-missing",
        task="fix the parser tests",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
        success_criteria=[
            SuccessCriterion(id="tests", description="Targeted tests pass")
        ],
    )
    result = evaluate_acceptance(
        spec,
        events=[
            AgentEvent(
                run_id=spec.run_id,
                event_type="model.message",
                payload={"content": "Done. All tests pass."},
            )
        ],
        artifacts=[],
    )
    assert result.passed is False
    assert "missing_diff_artifact" in result.failures
    assert "successful_test_command" in result.failures
