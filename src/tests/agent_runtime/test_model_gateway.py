from __future__ import annotations

from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.model_gateway import AgentChatCompletionRequest, AgentModelMessage, _kwargs


def test_agent_model_request_preserves_tool_and_reasoning_semantics() -> None:
    request = AgentChatCompletionRequest(
        model="lmstudio::qwen",
        messages=[AgentModelMessage(role="user", content="hello")],
        tools=[{"type": "function", "function": {"name": "read"}}],
        tool_choice="auto",
    )
    values = _kwargs(request, "high")
    assert values["tools"][0]["function"]["name"] == "read"
    assert values["tool_choice"] == "auto"
    assert values["reasoning_effort"] == "high"


def test_model_ref_is_not_runtime_specific() -> None:
    spec = AgentRunSpec(
        task="inspect",
        model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-sol"),
    )
    assert spec.model.provider_id == "chatgpt_codex"
