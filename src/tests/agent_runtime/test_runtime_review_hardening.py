from __future__ import annotations

from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.model_gateway import _STREAM_END, _next_stream_response, normalize_llm_provider_id
from app.agent_runtime.pi_runtime import normalize_pi_event


def test_pi_settled_is_a_claim_not_terminal_completion() -> None:
    event = normalize_pi_event("run-1", {"type": "agent_settled"})
    assert event is not None
    assert event.event_type == "run.settled"


def test_model_gateway_normalizes_facade_provider_ids() -> None:
    assert normalize_llm_provider_id("llm:chatgpt_codex") == "chatgpt_codex"
    assert normalize_llm_provider_id("lmstudio") == "lmstudio"


def test_stream_iterator_stop_does_not_raise_stopiteration() -> None:
    iterator = iter([])
    assert _next_stream_response(iterator) is _STREAM_END


def test_model_ref_can_keep_ui_provider_identity() -> None:
    spec = AgentRunSpec(task="inspect", model=ModelRef(provider_id="llm:lmstudio", model_id="qwen"))
    assert spec.model.provider_id == "llm:lmstudio"
