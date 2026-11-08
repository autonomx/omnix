"""The Memory model setting: memory's own calls use the provider and model it names, or the default provider."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.assistant_memory import conversation_reading, model_route, structured_provider


def _setting(monkeypatch, row: dict | None) -> None:
    overrides = {} if row is None else {model_route.MEMORY_ROUTE_KEY: row}
    profile = SimpleNamespace(global_settings=SimpleNamespace(routing=SimpleNamespace(task_overrides=overrides)))
    monkeypatch.setattr("app.settings.effective_defaults.load_effective_profile", lambda: profile)


@pytest.fixture
def providers(monkeypatch):
    from app.providers import service as provider_service

    asked: list[str | None] = []

    def get_provider(name=None):
        asked.append(name)
        return SimpleNamespace(provider_name=name or "claude_cli", config=SimpleNamespace(model="configured"))

    monkeypatch.setattr(provider_service, "get_provider", get_provider)
    for name in ("OMNIX_MEMORY_STRUCTURED_EXTRACTION_PROVIDER", "OMNIX_MEMORY_READING_MODEL",
                 "OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODE", "auto")
    return asked


def test_unset_memory_keeps_the_default_provider_and_sonnet_for_reading(monkeypatch, providers) -> None:
    _setting(monkeypatch, None)

    reader = conversation_reading.default_conversation_reader()
    proposer = structured_provider.default_structured_proposal_provider()

    assert providers == [None, None]
    assert reader.model_id == "sonnet"
    assert proposer.model == "configured"  # the provider's configured model


def test_a_chosen_provider_and_model_serve_both_memory_jobs(monkeypatch, providers) -> None:
    _setting(monkeypatch, {"providerId": "llm:chatgpt_codex", "modelId": "gpt-5.6-sol"})

    reader = conversation_reading.default_conversation_reader()
    proposer = structured_provider.default_structured_proposal_provider()

    assert providers == ["chatgpt_codex", "chatgpt_codex"]
    assert reader.model_id == "gpt-5.6-sol" and proposer.model == "gpt-5.6-sol"


def test_a_chosen_provider_without_a_model_uses_that_providers_own_choice(monkeypatch, providers) -> None:
    _setting(monkeypatch, {"providerId": "lmstudio", "modelId": ""})

    reader = conversation_reading.default_conversation_reader()

    assert providers == ["lmstudio"]
    assert reader.model_id == "configured"  # LM Studio's configured model; the Sonnet choice is the Claude CLI's alone


def test_the_environment_still_wins_and_takes_the_model_with_its_provider(monkeypatch, providers) -> None:
    _setting(monkeypatch, {"providerId": "chatgpt_codex", "modelId": "gpt-5.6-sol"})
    monkeypatch.setenv("OMNIX_MEMORY_STRUCTURED_EXTRACTION_PROVIDER", "claude_cli")

    reader = conversation_reading.default_conversation_reader()

    assert providers == ["claude_cli"] and reader.model_id == "sonnet"


def test_an_unreadable_setting_falls_back_to_the_default_provider(monkeypatch) -> None:
    def broken():
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr("app.settings.effective_defaults.load_effective_profile", broken)

    assert model_route.memory_model() == model_route.MemoryModel()
