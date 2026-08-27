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
