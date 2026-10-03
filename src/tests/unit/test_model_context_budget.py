"""Chat budgets follow the model's advertised context window (WP-5.7)."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from app.chat.context_budget import DEFAULT_INPUT_TOKEN_BUDGET, prompt_budget_for_model
from app.providers import model_catalog
from app.providers.model_catalog import advertised_context_window, clear_model_catalog


class _Provider:
    def __init__(self, models, *, fail: bool = False) -> None:
        self.models, self.fail, self.calls = models, fail, 0

    def get_models(self):
        self.calls += 1
        if self.fail:
            raise ConnectionError("down")
        return self.models


@pytest.fixture(autouse=True)
def fresh_catalog():
    clear_model_catalog()
    yield
    clear_model_catalog()


def _models(**windows):
    return [SimpleNamespace(id=name, context_length=length) for name, length in windows.items()]


def test_the_window_comes_from_the_providers_model_list_and_is_cached() -> None:
    provider = _Provider(_models(small=8_192, large=200_000, unknown=None))
    lookup = {"lmstudio": provider}.get

    assert advertised_context_window("lmstudio", "small", provider_lookup=lookup, background=False) == 8_192
    assert advertised_context_window("lmstudio", "large", provider_lookup=lookup, background=False) == 200_000
    assert advertised_context_window("lmstudio", "unknown", provider_lookup=lookup, background=False) is None
    assert provider.calls == 1


def test_a_turn_never_waits_for_the_model_list() -> None:
    release = threading.Event()

    class Slow(_Provider):
        def get_models(self):
            release.wait(5)
            return super().get_models()

    provider = Slow(_models(small=8_192))
    assert advertised_context_window("remote", "small", provider_lookup={"remote": provider}.get) is None
    release.set()
    for _ in range(100):
        if provider.calls:
            break
        threading.Event().wait(0.02)
    assert provider.calls == 1


def test_a_provider_that_cannot_list_models_is_not_asked_again_at_once() -> None:
    provider = _Provider([], fail=True)
    lookup = {"down": provider}.get
    assert advertised_context_window("down", "m", provider_lookup=lookup, background=False) is None
    assert advertised_context_window("down", "m", provider_lookup=lookup, background=False) is None
    assert provider.calls == 1


def test_the_budget_uses_the_window_and_the_configured_cap(monkeypatch) -> None:
    monkeypatch.setattr(model_catalog, "_default_provider", {"lmstudio": _Provider(_models(small=8_192, large=500_000))}.get)
    monkeypatch.delenv("OMNIX_CHAT_INPUT_TOKEN_BUDGET", raising=False)
    advertised_context_window("lmstudio", "small", provider_lookup=model_catalog._default_provider, background=False)

    small = prompt_budget_for_model("lmstudio", "small")
    assert small.max_input_tokens == 8_192
    assert small.reserved_output_tokens == 2_048  # a quarter of a small window, not the 4,096 default
    assert prompt_budget_for_model("lmstudio", "large").max_input_tokens == 500_000
    monkeypatch.setenv("OMNIX_CHAT_INPUT_TOKEN_BUDGET", "100000")
    assert prompt_budget_for_model("lmstudio", "large").max_input_tokens == 100_000
    assert prompt_budget_for_model("lmstudio", "missing").max_input_tokens == 100_000
    monkeypatch.delenv("OMNIX_CHAT_INPUT_TOKEN_BUDGET")
    assert prompt_budget_for_model(None, None).max_input_tokens == DEFAULT_INPUT_TOKEN_BUDGET


def test_prompt_assembly_budgets_for_the_sessions_model(monkeypatch) -> None:
    from app.chat.models import ChatMessage, ChatSession
    from app.chat.prompt_assembly import build_prompt_assembly

    monkeypatch.delenv("OMNIX_CHAT_INPUT_TOKEN_BUDGET", raising=False)
    monkeypatch.setattr(model_catalog, "_default_provider", {"lmstudio": _Provider(_models(tiny=4_096))}.get)
    advertised_context_window("lmstudio", "tiny", provider_lookup=model_catalog._default_provider, background=False)
    message = ChatMessage(id="m1", role="user", content="hello", created_at="2026-10-03T00:00:00+00:00")
    session = ChatSession(id="chat:budget", title="t", provider_id="lmstudio", model_id="tiny", messages=[message],
                          created_at="2026-10-03T00:00:00+00:00", updated_at="2026-10-03T00:00:00+00:00")

    assembly = build_prompt_assembly(session, message, global_system_prompt="")

    assert assembly.budget.max_input_tokens == 4_096
