from __future__ import annotations

from app.agent_runtime.model_gateway import _bounded_max_tokens, _output_tokens
from app.providers.base import ChatResponse


def test_model_gateway_caps_completion_to_remaining_budget() -> None:
    assert _bounded_max_tokens(None, 120) == 120
    assert _bounded_max_tokens(500, 120) == 120
    assert _bounded_max_tokens(50, 120) == 50
    assert _bounded_max_tokens(50, 0) == 0


def test_model_gateway_reads_normalized_output_usage() -> None:
    completion = ChatResponse(
        content="ok",
        model="test",
        usage={"completion_tokens": 17},
    )
    output = ChatResponse(
        content="ok",
        model="test",
        usage={"output_tokens": 19},
    )
    assert _output_tokens(completion) == 17
    assert _output_tokens(output) == 19
