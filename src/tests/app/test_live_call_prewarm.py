from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatSession
from app.gateway import live_call_prewarm as prewarm


class _FakeStore:
    def __init__(self) -> None:
        self.calls = 0
        self.session = ChatSession(
            id="session-prewarm",
            title="Prewarm",
            provider_id="fake-provider",
            model_id="fake-model",
            created_at="2026-08-05T00:00:00+00:00",
            updated_at="2026-08-05T00:00:00+00:00",
        )

    def get_session(self, session_id: str):
        self.calls += 1
        return self.session if session_id == self.session.id else None


class _FakeLlmProvider:
    def __init__(self) -> None:
        self.calls = 0

    def chat_completion(self, **kwargs):
        self.calls += 1
        assert kwargs["stream"] is True
        assert kwargs["model"] == "fake-model"
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

    def generate_audio_stream(self, **kwargs):
        self.calls += 1
        assert kwargs["speaker"] == "Jinx"
        assert kwargs["chunk_size"] == 1
        yield [0.0, 0.1, -0.1], 24_000, {}


def _client(store: _FakeStore) -> TestClient:
    app = FastAPI()
    prewarm.register_live_call_prewarm_routes(
        app,
        chat_store_factory=lambda: store,
    )
    return TestClient(app)


def test_live_call_prewarm_warms_llm_and_tts_once(monkeypatch) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    llm = _FakeLlmProvider()
    tts = _FakeTtsProvider()
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
    assert first.json()["tts"]["status"] == "warmed"
    assert second.status_code == 200
    assert second.json()["status"] == "cached"
    assert second.json()["fully_warmed"] is True
    assert llm.calls == 1
    assert tts.calls == 1
    assert store.calls == 2


def test_live_call_prewarm_does_not_cache_partial_success(monkeypatch) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    llm = _FailingLlmProvider()
    tts = _FakeTtsProvider()
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


def test_live_call_prewarm_is_best_effort_when_providers_are_unavailable(
    monkeypatch,
) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
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