from pathlib import Path

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.pi_runtime import PiAgentRuntime, pi_rpc_argv


def test_mutating_coding_runtime_exposes_internal_planning_tool(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-plan-tool",
        task="Update the implementation safely",
        objective="Update the implementation safely",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
        workspace=WorkspaceSpec(root=str(tmp_path)),
    )

    argv = pi_rpc_argv(spec, pi_path="pi")

    assert "--tools" in argv
    tools = argv[argv.index("--tools") + 1].split(",")
    assert "omnix_plan" in tools


def test_nonmutating_runtime_does_not_gain_planning_tool(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-chat-no-plan-tool",
        task="Explain the code",
        objective="Explain the code",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read"],
        expected_artifacts=[],
        workspace=WorkspaceSpec(root=str(tmp_path)),
    )

    argv = pi_rpc_argv(spec, pi_path="pi")

    tools = argv[argv.index("--tools") + 1].split(",")
    assert "omnix_plan" not in tools


def test_engineering_prompt_makes_normal_working_plan_advisory(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-plan-prompt",
        task='Rename "old label" to "new label"',
        objective='Rename "old label" to "new label"',
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
        workspace=WorkspaceSpec(root=str(tmp_path)),
    )

    prompt = PiAgentRuntime._initial_prompt(spec)

    assert "omnix_plan" in prompt
    assert "working plan is informative rather than permission" in prompt
    assert "Do not stop for a PlanDelta" in prompt
    assert "consequential operation" in prompt
    assert "PLAN CONFORMANCE" not in prompt
