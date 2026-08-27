from __future__ import annotations

from app.agent_runtime.acceptance import evaluate_acceptance
from app.agent_runtime.contracts import AgentArtifact, AgentEvent, AgentRunSpec, ModelRef, SuccessCriterion


def test_acceptance_requires_model_evidence_to_be_verified_by_omnix() -> None:
    spec = AgentRunSpec(
        run_id="run-1",
        task="Fix tests",
        model=ModelRef(provider_id="test", model_id="model"),
        success_criteria=[SuccessCriterion(id="tests", description="Targeted tests pass")],
        expected_artifacts=["diff"],
    )
    events = [
        AgentEvent(run_id="run-1", event_type="tool.started", payload={"tool_call_id": "1", "tool": "bash", "args": {"command": "python -m pytest -q"}}),
        AgentEvent(run_id="run-1", event_type="tool.completed", payload={"tool_call_id": "1", "tool": "bash", "is_error": False}),
    ]
    result = evaluate_acceptance(
        spec,
        events=events,
        artifacts=[AgentArtifact(run_id="run-1", kind="diff", name="workspace.diff")],
    )
    assert result.passed
    assert result.checks["successful_test_command"]


def test_acceptance_rejects_claimed_completion_without_required_test() -> None:
    spec = AgentRunSpec(
        run_id="run-1",
        task="Fix tests",
        model=ModelRef(provider_id="test", model_id="model"),
        success_criteria=[SuccessCriterion(id="tests", description="Tests pass")],
    )
    result = evaluate_acceptance(spec, events=[], artifacts=[])
    assert not result.passed
    assert "successful_test_command" in result.failures


def test_mutating_coding_run_requires_successful_test_by_default() -> None:
    spec = AgentRunSpec(
        run_id="run-default-coding",
        task="Implement the change",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.write"],
        success_criteria=[
            SuccessCriterion(
                id="generic",
                description="Complete the requested task and report evidence.",
            )
        ],
    )
    result = evaluate_acceptance(spec, events=[], artifacts=[])
    assert not result.passed
    assert "successful_test_command" in result.failures


def test_explicit_required_command_must_succeed() -> None:
    from app.agent_runtime.contracts import AcceptancePlan

    spec = AgentRunSpec(
        run_id="run-required-command",
        task="Fix targeted behavior",
        model=ModelRef(provider_id="test", model_id="model"),
        acceptance_plan=AcceptancePlan(
            required_commands=[["python", "-m", "pytest", "src/tests/target.py", "-q"]],
        ),
    )
    events = [
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.started",
            payload={
                "tool_call_id": "1",
                "tool": "bash",
                "args": {"command": "python -m pytest src/tests/target.py -q"},
            },
        ),
        AgentEvent(
            run_id=spec.run_id,
            event_type="tool.completed",
            payload={"tool_call_id": "1", "tool": "bash", "is_error": False},
        ),
    ]
    result = evaluate_acceptance(spec, events=events, artifacts=[])
    assert result.passed
    assert result.checks["required_command:1"]


def test_optional_success_criterion_does_not_create_required_acceptance_check() -> None:
    spec = AgentRunSpec(
        run_id="run-optional",
        task="Inspect",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        success_criteria=[
            SuccessCriterion(
                id="optional-tests",
                description="Tests pass if applicable",
                required=False,
            )
        ],
    )
    result = evaluate_acceptance(spec, events=[], artifacts=[])
    assert result.passed
    assert "successful_test_command" not in result.checks
