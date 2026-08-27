from __future__ import annotations

from pathlib import Path


def test_repository_keeps_enqueue_command_compatibility_contract() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "repository.py").read_text(encoding="utf-8")
    assert "def enqueue_command(self, command: AgentRunCommand) -> AgentRunCommand:" in source
    assert "def enqueue_command_with_status" in source


def test_broker_reuses_durable_approval_for_execution_key() -> None:
    source = (Path(__file__).parents[2] / "app" / "agent_runtime" / "broker_api.py").read_text(encoding="utf-8")
    assert "find_capability_approval" in source
