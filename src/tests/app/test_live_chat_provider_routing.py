from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import shared
from app.chat.models import SendChatMessageRequest
from app.gateway.live_chat_provider_routing import (
    _remember_turn_route,
    _reset_provider_route_state_for_tests,
    _stream_route,
    resolve_effective_provider_id,
    resolve_provider_route,
    route_chat_request,
)


@pytest.fixture(autouse=True)
def reset_route_state():
    _reset_provider_route_state_for_tests()
    yield
    _reset_provider_route_state_for_tests()


def test_default_provider_is_concretized_before_metrics_and_retry(monkeypatch) -> None:
    provider = SimpleNamespace(provider_name="lmstudio")
    requested: list[str | None] = []

    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})

    def fake_get_provider(provider_id: str | None):
        requested.append(provider_id)
        return provider

    monkeypatch.setattr(shared, "get_provider", fake_get_provider)

    effective_provider_id, resolved_provider = resolve_provider_route(None)

    assert effective_provider_id == "lmstudio"
    assert resolved_provider is provider
    assert requested == ["lmstudio"]
    assert resolved_provider.provider_name == "lmstudio"


def test_implicit_turn_overrides_stale_session_provider_and_model(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})
    request = SendChatMessageRequest(content="Hello")

    routed_request, route = route_chat_request(request)
    _remember_turn_route("msg:user", route)
    provider_id, model_id, remembered = _stream_route(
        SimpleNamespace(id="msg:user"),
        "cerebras",
        "llama-3.3-70b",
    )

    assert routed_request.provider_id == "lmstudio"
    assert routed_request.model_id is None
    assert provider_id == "lmstudio"
    assert model_id is None
    assert remembered is route
    assert route.provider_explicit is False
    assert route.model_explicit is False


def test_explicit_provider_and_model_routing_is_preserved(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})
    request = SendChatMessageRequest(
        content="Hello",
        provider_id="llm:cerebras",
        model_id="llm:cerebras:llama-3.3-70b",
    )

    routed_request, route = route_chat_request(request)
    _remember_turn_route("msg:explicit", route)
    provider_id, model_id, remembered = _stream_route(
        SimpleNamespace(id="msg:explicit"),
        "lmstudio",
        None,
    )

    assert resolve_effective_provider_id("llm:cerebras") == "llm:cerebras"
    assert routed_request.provider_id == "llm:cerebras"
    assert provider_id == "llm:cerebras"
    assert model_id == "llm:cerebras:llama-3.3-70b"
    assert remembered is route
    assert route.provider_explicit is True
    assert route.model_explicit is True


def test_empty_configured_provider_falls_back_to_lmstudio(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": ""})

    assert resolve_effective_provider_id(None) == "lmstudio"
