from __future__ import annotations

from app.platform.agent_runtime.model_gateway import agent_conversation_id


def test_agent_conversation_id_changes_for_a_fresh_pi_session() -> None:
    assert agent_conversation_id("run-1", "session-a") != agent_conversation_id("run-1", "session-b")
    assert agent_conversation_id("run-1") == "agent:run-1"
