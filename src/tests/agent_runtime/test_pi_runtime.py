from __future__ import annotations

from pathlib import Path

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.pi_runtime import normalize_pi_event, pi_rpc_argv


def test_pi_rpc_command_is_headless_and_guarded(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-pi",
        task="Inspect",
        model=ModelRef(provider_id="openai", model_id="gpt-test", reasoning_effort="medium"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=["workspace.read"],
    )
    argv = pi_rpc_argv(spec, pi_path="pi")
    assert argv[:3] == ["pi", "--mode", "rpc"]
    assert "--extension" in argv
    assert "--tools" in argv
    assert "--no-context-files" in argv
    assert "--thinking" in argv


def test_pi_events_are_normalized_without_leaking_runtime_contracts() -> None:
    event = normalize_pi_event(
        "run-1",
        {"type": "tool_execution_start", "toolCallId": "call-1", "toolName": "read", "args": {"path": "a.py"}},
    )
    assert event is not None
    assert event.event_type == "tool.started"
    assert event.payload["tool"] == "read"


def test_pi_rpc_projects_git_read_capabilities_to_guarded_shell(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-git-read",
        task="Inspect git state",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=["workspace.git_status", "workspace.git_diff"],
    )
    argv = pi_rpc_argv(spec, pi_path="pi")
    assert "--tools" in argv
    tools = argv[argv.index("--tools") + 1].split(",")
    assert ("powershell" if __import__("os").name == "nt" else "bash") in tools


def test_pi_rpc_without_local_capabilities_disables_builtin_tools(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-no-tools",
        task="Reason only",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=[],
    )
    argv = pi_rpc_argv(spec, pi_path="pi")
    assert "--no-builtin-tools" in argv
