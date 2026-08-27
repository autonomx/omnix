from __future__ import annotations

from app.agent_runtime.model_gateway import normalize_llm_model_id


def test_agent_model_gateway_normalizes_facade_model_ids() -> None:
    assert normalize_llm_model_id("llm:lmstudio", "llm:lmstudio:qwen3") == "qwen3"
    assert normalize_llm_model_id("lmstudio", "qwen3") == "qwen3"
    assert normalize_llm_model_id("llm:chatgpt_codex", "llm:chatgpt_codex:gpt-5.6") == "gpt-5.6"
