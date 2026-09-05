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
