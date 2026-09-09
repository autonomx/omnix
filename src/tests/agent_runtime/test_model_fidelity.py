from __future__ import annotations

from app.agent_runtime.contracts import ModelRef
from app.agent_runtime.model_fidelity import resolve_model_ref


def test_provider_selected_reasoning_replaces_historical_synthetic_none(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(
        "app.agent_runtime.model_fidelity._provider_reasoning_effort",
        lambda _provider_id: "max",
    )
    resolved = resolve_model_ref(
        ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna", reasoning_effort="none")
    )
    assert resolved.reasoning_effort == "max"
    assert resolved.parameters["requested_reasoning_effort"] == "none"
    assert resolved.parameters["resolved_reasoning_effort"] == "max"
    assert resolved.parameters["reasoning_effort_source"] == "provider_settings"


def test_operator_reasoning_override_remains_authoritative(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_REASONING_EFFORT", "high")
    monkeypatch.setattr(
        "app.agent_runtime.model_fidelity._provider_reasoning_effort",
        lambda _provider_id: "max",
    )
    resolved = resolve_model_ref(
        ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna", reasoning_effort="medium")
    )
    assert resolved.reasoning_effort == "high"
    assert resolved.parameters["reasoning_effort_source"] == "operator_override"


def test_chat_agent_reasoning_reads_selected_provider_setting(monkeypatch) -> None:
    from types import SimpleNamespace
    from app import shared
    from app.agent_runtime import chat_bridge
    monkeypatch.delenv("OMNIX_AGENT_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: SimpleNamespace(reasoning_effort="max"))
    assert chat_bridge._agent_reasoning_effort("chatgpt_codex") == "max"


def test_model_fidelity_records_full_model_audit(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_REASONING_EFFORT", raising=False)
    resolved = resolve_model_ref(ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna", reasoning_effort="max"))
    assert resolved.parameters["requested_provider_id"] == "chatgpt_codex"
    assert resolved.parameters["resolved_provider_id"] == "chatgpt_codex"
    assert resolved.parameters["requested_model_id"] == "gpt-5.6-luna"
    assert resolved.parameters["resolved_model_id"] == "gpt-5.6-luna"
    assert resolved.parameters["requested_reasoning_effort"] == "max"
    assert resolved.parameters["resolved_reasoning_effort"] == "max"
