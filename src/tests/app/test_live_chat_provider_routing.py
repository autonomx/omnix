from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import shared
from app.chat.models import SendChatMessageRequest
from app.gateway import live_call_prewarm as prewarm
from app.gateway.live_chat_provider_routing import (
    _live_voice_affinity_for_current_provider,
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
    prewarm.clear_live_call_prewarm_state()
    yield
    _reset_provider_route_state_for_tests()
    prewarm.clear_live_call_prewarm_state()


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


def test_default_provider_resolution_is_process_cached(monkeypatch) -> None:
    settings_loads = 0

    def fake_load_settings():
        nonlocal settings_loads
        settings_loads += 1
        return {"provider": "lmstudio"}

    monkeypatch.setattr(shared, "load_settings", fake_load_settings)

    assert resolve_effective_provider_id(None) == "lmstudio"
    assert resolve_effective_provider_id(None) == "lmstudio"
    assert settings_loads == 1


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
    assert route.execution_lane == "session"


def test_live_voice_ignores_stale_prewarm_affinity_after_settings_change(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})
    prewarm.remember_live_call_provider_affinity(
        "session-live",
        "cerebras",
        "stale-cerebras-model",
    )

    assert _live_voice_affinity_for_current_provider("session-live") is None


def test_live_voice_keeps_prewarm_affinity_when_settings_provider_matches(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})
    prewarm.remember_live_call_provider_affinity(
        "session-live",
        "lmstudio",
        "session-live-model",
    )

    assert _live_voice_affinity_for_current_provider("session-live") == (
        "lmstudio",
        "session-live-model",
    )


def test_implicit_live_turn_uses_prewarmed_session_affinity(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "cerebras"})
    request = SendChatMessageRequest(
        content="Hello",
        user_turn_id="voice-user-turn:one",
        speech_segment_id="voice-segment:one",
    )

    routed_request, route = route_chat_request(
        request,
        implicit_provider_id="lmstudio",
        implicit_model_id="session-live-model",
    )

    assert routed_request.provider_id == "lmstudio"
    assert routed_request.model_id == "session-live-model"
    assert route.provider_explicit is False
    assert route.model_explicit is False
    assert route.execution_lane == "session"


def test_explicit_live_provider_ignores_prewarmed_session_affinity(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})
    request = SendChatMessageRequest(
        content="Hello",
        provider_id="llm:cerebras",
        user_turn_id="voice-user-turn:two",
        speech_segment_id="voice-segment:two",
    )

    routed_request, route = route_chat_request(
        request,
        implicit_provider_id="lmstudio",
        implicit_model_id="session-live-model",
    )

    assert routed_request.provider_id == "llm:cerebras"
    assert routed_request.model_id is None
    assert route.provider_explicit is True
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
    assert route.execution_lane == "session"


def test_live_turn_uses_opt_in_dedicated_provider_and_model(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})
    monkeypatch.setenv("OMNIX_LIVE_VOICE_EXECUTION_MODE", "dedicated")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_PROVIDER_ID", "lmstudio")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_MODEL_ID", "qwen-live-fast")
    request = SendChatMessageRequest(
        content="Hello",
        user_turn_id="voice-user-turn:one",
        speech_segment_id="segment-one",
    )

    routed_request, route = route_chat_request(request)

    assert routed_request.provider_id == "lmstudio"
    assert routed_request.model_id == "qwen-live-fast"
    assert route.execution_lane == "dedicated"
    assert route.provider_explicit is False
    assert route.model_explicit is False


def test_text_turn_does_not_use_dedicated_live_lane(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})
    monkeypatch.setenv("OMNIX_LIVE_VOICE_EXECUTION_MODE", "dedicated")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_MODEL_ID", "qwen-live-fast")

    routed_request, route = route_chat_request(
        SendChatMessageRequest(content="This is a normal text turn")
    )

    assert routed_request.model_id is None
    assert route.execution_lane == "session"


def test_empty_configured_provider_falls_back_to_lmstudio(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": ""})

    assert resolve_effective_provider_id(None) == "lmstudio"
