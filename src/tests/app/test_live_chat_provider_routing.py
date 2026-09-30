from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.chat import live_call_prewarm as prewarm
from app.chat.models import CreateChatSessionRequest, SendChatMessageRequest
from app.live_voice.llm.routing import (
    ROUTE_METADATA_KEY,
    _live_voice_affinity_for_current_provider,
    resolve_effective_provider_id,
    resolve_generation_route,
    resolve_provider_route,
    resolve_stream_route,
    route_chat_request,
)
from app.providers import service as provider_service
from app.settings import access as settings_access


@pytest.fixture(autouse=True)
def clear_live_call_affinity():
    prewarm.clear_live_call_prewarm_state()
    yield
    prewarm.clear_live_call_prewarm_state()


def test_default_provider_is_resolved_from_current_settings(monkeypatch) -> None:
    settings = iter(("lmstudio", "cerebras"))
    settings_loads = 0

    def fake_load_settings():
        nonlocal settings_loads
        settings_loads += 1
        return {"provider": next(settings)}

    monkeypatch.setattr(settings_access, "load_settings", fake_load_settings)

    assert resolve_effective_provider_id(None) == "lmstudio"
    assert resolve_effective_provider_id(None) == "cerebras"
    assert settings_loads == 2


def test_default_provider_resolves_to_its_configured_instance(monkeypatch) -> None:
    provider = SimpleNamespace(provider_name="lmstudio")
    requested: list[str | None] = []

    monkeypatch.setattr(
        settings_access,
        "load_settings",
        lambda **_kwargs: {"provider": "lmstudio"},
    )

    def fake_get_provider(provider_id: str | None):
        requested.append(provider_id)
        return provider

    monkeypatch.setattr(provider_service, "get_provider", fake_get_provider)

    effective_provider_id, resolved_provider = resolve_provider_route(None)

    assert effective_provider_id == "lmstudio"
    assert resolved_provider is provider
    assert requested == ["lmstudio"]


def test_generation_worker_resolves_cancellation_provider_from_turn_route(monkeypatch) -> None:
    from app.chat.generation_jobs import _resolve_chat_provider

    provider = SimpleNamespace(provider_name="lmstudio")
    requested: list[str | None] = []

    def fake_get_provider(provider_id: str | None):
        requested.append(provider_id)
        return provider

    monkeypatch.setattr(provider_service, "get_provider", fake_get_provider)
    user_message = SimpleNamespace(
        metadata={ROUTE_METADATA_KEY: {"provider_id": "lmstudio"}}
    )

    resolved = _resolve_chat_provider(
        SimpleNamespace(provider_id="cerebras"),
        SendChatMessageRequest(content="Hello"),
        user_message,
    )

    assert resolved is provider
    assert requested == ["lmstudio"]


def test_begin_persists_the_resolved_route_for_later_workers(tmp_path, monkeypatch) -> None:
    from app.chat.prompt_store import ChatSessionStore

    monkeypatch.setattr(
        settings_access,
        "load_settings",
        lambda **_kwargs: {"provider": "lmstudio"},
    )
    store = ChatSessionStore(tmp_path / "sessions.json")
    session = store.create_session(
        CreateChatSessionRequest(provider_id="cerebras", model_id="stale-model")
    )

    started = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="Hello"),
    )

    assert started is not None
    _, user_message = started
    persisted = store.get_session(session.id)
    assert persisted is not None
    persisted_message = next(item for item in persisted.messages if item.id == user_message.id)
    assert persisted.provider_id == "lmstudio"
    assert persisted.model_id is None
    assert persisted_message.metadata[ROUTE_METADATA_KEY] == {
        "provider_id": "lmstudio",
        "model_id": None,
        "provider_explicit": False,
        "model_explicit": False,
        "execution_lane": "session",
    }

    stream_route = resolve_stream_route(
        persisted_message,
        provider_id="cerebras",
        model_id="stale-model",
    )
    generation_route = resolve_generation_route(
        persisted_message,
        provider_id="cerebras",
        model_id="stale-model",
        request=SendChatMessageRequest(content="Hello"),
    )
    assert stream_route.provider_id == "lmstudio"
    assert stream_route.model_id is None
    assert generation_route == stream_route


def test_live_voice_ignores_stale_prewarm_affinity_after_settings_change(monkeypatch) -> None:
    monkeypatch.setattr(settings_access, "load_settings", lambda: {"provider": "lmstudio"})
    prewarm.remember_live_call_provider_affinity(
        "session-live",
        "cerebras",
        "stale-cerebras-model",
    )

    assert _live_voice_affinity_for_current_provider("session-live") is None


def test_live_voice_uses_prewarm_affinity_when_provider_matches(monkeypatch) -> None:
    monkeypatch.setattr(settings_access, "load_settings", lambda: {"provider": "lmstudio"})
    prewarm.remember_live_call_provider_affinity(
        "session-live",
        "lmstudio",
        "session-live-model",
    )

    assert _live_voice_affinity_for_current_provider("session-live") == (
        "lmstudio",
        "session-live-model",
    )


def test_live_voice_turn_uses_prewarmed_session_affinity(monkeypatch) -> None:
    monkeypatch.setattr(settings_access, "load_settings", lambda: {"provider": "cerebras"})
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


def test_explicit_live_provider_ignores_implicit_affinity(monkeypatch) -> None:
    monkeypatch.setattr(settings_access, "load_settings", lambda: {"provider": "lmstudio"})
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


def test_explicit_provider_and_model_are_preserved_in_durable_route() -> None:
    request = SendChatMessageRequest(
        content="Hello",
        provider_id="llm:cerebras",
        model_id="llm:cerebras:llama-3.3-70b",
    )

    routed_request, route = route_chat_request(request)
    message = SimpleNamespace(metadata={ROUTE_METADATA_KEY: route.to_metadata()})
    resolved = resolve_stream_route(message, provider_id="lmstudio", model_id=None)

    assert resolve_effective_provider_id("llm:cerebras") == "llm:cerebras"
    assert routed_request.provider_id == "llm:cerebras"
    assert resolved.provider_id == "llm:cerebras"
    assert resolved.model_id == "llm:cerebras:llama-3.3-70b"
    assert resolved.provider_explicit is True
    assert resolved.model_explicit is True
    assert resolved.execution_lane == "session"


def test_live_turn_uses_opt_in_dedicated_provider_and_model(monkeypatch) -> None:
    monkeypatch.setattr(settings_access, "load_settings", lambda: {"provider": "lmstudio"})
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
    monkeypatch.setattr(settings_access, "load_settings", lambda: {"provider": "lmstudio"})
    monkeypatch.setenv("OMNIX_LIVE_VOICE_EXECUTION_MODE", "dedicated")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_MODEL_ID", "qwen-live-fast")

    routed_request, route = route_chat_request(
        SendChatMessageRequest(content="This is a normal text turn")
    )

    assert routed_request.model_id is None
    assert route.execution_lane == "session"


def test_empty_configured_provider_falls_back_to_lmstudio(monkeypatch) -> None:
    monkeypatch.setattr(settings_access, "load_settings", lambda: {"provider": ""})

    assert resolve_effective_provider_id(None) == "lmstudio"
