from __future__ import annotations

import asyncio
import threading

from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.model_gateway import (
    AgentChatCompletionRequest,
    AgentModelMessage,
    _kwargs,
    _messages,
    _stream_responses,
)


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


def test_provider_stream_iterator_stays_on_one_worker_thread() -> None:
    observed_threads: list[int] = []

    def provider_stream():
        lock = threading.RLock()
        with lock:
            for value in ("first", "second"):
                observed_threads.append(threading.get_ident())
                yield value

    async def collect() -> list[str]:
        return [value async for value in _stream_responses(provider_stream())]

    assert asyncio.run(collect()) == ["first", "second"]
    assert len(set(observed_threads)) == 1
    assert observed_threads[0] != threading.get_ident()



def test_agent_model_messages_preserve_images() -> None:
    rows = [
        AgentModelMessage(
            role="user",
            content=[
                {"type": "text", "text": "Inspect this screenshot"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,YWJj"},
                },
            ],
        )
    ]

    messages = _messages(rows)

    assert len(messages) == 1
    assert messages[0].content == "Inspect this screenshot"
    assert messages[0].vision_images == [{"data": "data:image/png;base64,YWJj"}]


def test_agent_model_messages_accept_pi_image_blocks() -> None:
    rows = [
        AgentModelMessage(
            role="user",
            content=[
                {"type": "text", "text": "Inspect"},
                {
                    "type": "image",
                    "data": "YWJj",
                    "mimeType": "image/webp",
                },
            ],
        )
    ]

    messages = _messages(rows)

    assert messages[0].vision_images == [{"data": "data:image/webp;base64,YWJj"}]
