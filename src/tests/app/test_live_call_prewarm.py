from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatSession
from app.gateway import live_call_prewarm as prewarm
from app.providers import CerebrasProvider, ProviderConfig


class _FakeStore:
    def __init__(self) -> None:
        self.calls = 0
        self.prompt_calls = 0
        self.warm_user_message = None
        self.session = ChatSession(
            id="session-prewarm",
            title="Prewarm",
            provider_id="fake-provider",
            model_id="fake-model",
            interaction_mode="character",
            character_id="jinx",
            character_profile_version=5,
            effective_identity_hash="a" * 64,
            active_segment_id="segment-jinx",
            message_count=2,
            created_at="2026-08-05T00:00:00+00:00",
            updated_at="2026-08-05T00:00:00+00:00",
        )

    def get_session(self, session_id: str):
        self.calls += 1
        return self.session if session_id == self.session.id else None

    def build_provider_prompt(self, session, user_message, context_items):
        assert session is self.session
        assert context_items == []
        self.prompt_calls += 1
        self.warm_user_message = user_message
        rendered = SimpleNamespace(messages=[
            SimpleNamespace(
                role="system",
                content="You are Jinx. Stay chaotic, theatrical, and in character.",
            ),
            SimpleNamespace(role="assistant", content="Make it interesting."),
            SimpleNamespace(role="user", content=user_message.content),
        ])
        return SimpleNamespace(), rendered


class _FakeLlmProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.last_kwargs = None

    def chat_completion(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        assert kwargs["stream"] is True
        assert kwargs["model"] == "fake-model"
        assert kwargs["chat_template_kwargs"] == {"enable_thinking": False}
        assert kwargs["messages"][0].role == "system"
        assert "You are Jinx" in kwargs["messages"][0].content
        return iter([SimpleNamespace(content="ready")])


class _FailingLlmProvider:
    def __init__(self) -> None:
        self.calls = 0

    def chat_completion(self, **_kwargs):
        self.calls += 1
        raise RuntimeError("no model loaded")


class _FakeTtsProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.last_kwargs = None

    def generate_audio_stream(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        assert kwargs["text"] == "Ready to answer."
        assert kwargs["speaker"] == "Jinx"
        assert kwargs["language"] == "English"
        assert kwargs["chunk_size"] == 4
        assert kwargs["max_new_tokens"] == 42
        assert kwargs["temperature"] == 0.6
        assert kwargs["top_k"] == 20
        assert kwargs["top_p"] == 0.85
        assert kwargs["repetition_penalty"] == 1.05
        assert kwargs["append_silence"] is False
        assert kwargs["parity_mode"] is False
        assert kwargs["non_streaming_mode"] is False
        yield [0.0, 0.1, -0.1], 24_000, {}


def _client(store: _FakeStore) -> TestClient:
    app = FastAPI()
    prewarm.register_live_call_prewarm_routes(
        app,
        chat_store_factory=lambda: store,
    )
    return TestClient(app)


def _fake_provider_settings() -> dict[str, object]:
    return {
        "provider": "fake-provider",
        "fake-provider": {"model": "fake-model"},
    }


def test_live_call_prewarm_warms_real_prompt_prefix_and_tts_once(monkeypatch) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    llm = _FakeLlmProvider()
    tts = _FakeTtsProvider()
    monkeypatch.setattr(prewarm.shared, "load_settings", _fake_provider_settings)
    monkeypatch.setattr(prewarm.shared, "get_provider", lambda _provider_id: llm)
    monkeypatch.setattr(prewarm, "get_tts_provider", lambda: tts)
    client = _client(store)

    first = client.post(
        "/api/live-call/sessions/session-prewarm/prewarm",
        json={"speaker": "Jinx", "language": "English"},
    )
    second = client.post(
        "/api/live-call/sessions/session-prewarm/prewarm",
        json={"speaker": "Jinx", "language": "English"},
    )

    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert first.json()["fully_warmed"] is True
    assert first.json()["llm"]["status"] == "warmed"
    assert first.json()["llm"]["prompt_message_count"] == 3
    assert first.json()["llm"]["prompt_chars"] > 60
    assert first.json()["tts"]["status"] == "warmed"
    assert second.status_code == 200
    assert second.json()["status"] == "cached"
    assert second.json()["fully_warmed"] is True
    assert llm.calls == 1
    assert tts.calls == 1
    assert tts.last_kwargs is not None
    assert store.prompt_calls == 1
    assert store.warm_user_message.metadata["side_effects_allowed"] is False
    assert store.warm_user_message.metadata["memory_writes_allowed"] is False
    assert store.calls == 2
    assert prewarm.live_call_provider_affinity("session-prewarm") == (
        "fake-provider",
        "fake-model",
    )


def test_live_call_prewarm_uses_settings_provider_over_stale_session_provider(
    monkeypatch,
) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    store.session.provider_id = "cerebras"
    store.session.model_id = "stale-cerebras-model"
    llm = _FakeLlmProvider()
    tts = _FakeTtsProvider()
    requested_provider_ids: list[str | None] = []

    monkeypatch.setattr(prewarm.shared, "load_settings", _fake_provider_settings)

    def fake_get_provider(provider_id: str | None):
        requested_provider_ids.append(provider_id)
        return llm

    monkeypatch.setattr(prewarm.shared, "get_provider", fake_get_provider)
    monkeypatch.setattr(prewarm, "get_tts_provider", lambda: tts)
    client = _client(store)

    response = client.post(
        "/api/live-call/sessions/session-prewarm/prewarm",
        json={"speaker": "Jinx", "language": "English"},
    )

    assert response.status_code == 200
    assert response.json()["fully_warmed"] is True
    assert requested_provider_ids == ["fake-provider"]
    assert store.session.provider_id == "cerebras"
    assert prewarm.live_call_provider_affinity("session-prewarm") == (
        "fake-provider",
        "fake-model",
    )


def test_cerebras_live_call_prewarm_omits_unsupported_template_kwargs(monkeypatch) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    provider = CerebrasProvider(
        ProviderConfig(
            provider_type="cerebras",
            api_key="test-key",
            model="fake-model",
        )
    )
    captured_payload = {}

    def fake_stream_completion(payload, *, timeout=None):
        captured_payload.update(payload)
        return iter([SimpleNamespace(content="ready")])

    monkeypatch.setattr(provider, "_stream_completion", fake_stream_completion)
    monkeypatch.setattr(prewarm.shared, "get_provider", lambda _provider_id: provider)

    result = prewarm._warm_llm(store, store.session)

    assert result.status == "warmed"
    assert captured_payload["model"] == "fake-model"
    assert captured_payload["stream"] is True
    assert "chat_template_kwargs" not in captured_payload


def test_live_call_prewarm_does_not_cache_partial_success(monkeypatch) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    llm = _FailingLlmProvider()
    tts = _FakeTtsProvider()
    monkeypatch.setattr(prewarm.shared, "load_settings", _fake_provider_settings)
    monkeypatch.setattr(prewarm.shared, "get_provider", lambda _provider_id: llm)
    monkeypatch.setattr(prewarm, "get_tts_provider", lambda: tts)
    client = _client(store)

    first = client.post(
        "/api/live-call/sessions/session-prewarm/prewarm",
        json={"speaker": "Jinx", "language": "English"},
    )
    second = client.post(
        "/api/live-call/sessions/session-prewarm/prewarm",
        json={"speaker": "Jinx", "language": "English"},
    )

    assert first.status_code == 200
    assert first.json()["ok"] is False
    assert first.json()["fully_warmed"] is False
    assert first.json()["status"] == "partial"
    assert first.json()["llm"]["status"] == "failed"
    assert first.json()["tts"]["status"] == "warmed"
    assert second.json()["cached"] is False
    assert second.json()["status"] == "partial"
    assert llm.calls == 2
    assert tts.calls == 2
    assert store.prompt_calls == 2
    assert prewarm.live_call_provider_affinity("session-prewarm") == (
        "fake-provider",
        "fake-model",
    )


def test_live_call_prewarm_is_best_effort_when_providers_are_unavailable(
    monkeypatch,
) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    monkeypatch.setattr(prewarm.shared, "load_settings", _fake_provider_settings)
    monkeypatch.setattr(prewarm.shared, "get_provider", lambda _provider_id: None)
    monkeypatch.setattr(prewarm, "get_tts_provider", lambda: None)
    client = _client(store)

    response = client.post(
        "/api/live-call/sessions/session-prewarm/prewarm",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["fully_warmed"] is False
    assert response.json()["status"] == "unavailable"
    assert response.json()["llm"]["status"] == "unavailable"
    assert response.json()["tts"]["status"] == "unavailable"
    assert store.prompt_calls == 0
    assert prewarm.live_call_provider_affinity("session-prewarm") == (
        "fake-provider",
        "fake-model",
    )
