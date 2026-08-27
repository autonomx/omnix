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
