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


class _FakeTtsProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate_audio_stream(self, **kwargs):
        self.calls += 1
        assert kwargs["speaker"] == "Jinx"
        assert kwargs["chunk_size"] == 1
        yield [0.0, 0.1, -0.1], 24_000, {}


def test_live_call_prewarm_warms_llm_and_tts_once(monkeypatch) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    llm = _FakeLlmProvider()
    tts = _FakeTtsProvider()
    monkeypatch.setattr(prewarm.shared, "get_provider", lambda _provider_id: llm)
    monkeypatch.setattr(prewarm, "get_tts_provider", lambda: tts)

    app = FastAPI()
    prewarm.register_live_call_prewarm_routes(
        app,
        chat_store_factory=lambda: store,
    )
    client = TestClient(app)

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
    assert first.json()["llm"]["status"] == "warmed"
    assert first.json()["tts"]["status"] == "warmed"
    assert second.status_code == 200
    assert second.json()["status"] == "cached"
    assert llm.calls == 1
    assert tts.calls == 1
    assert store.calls == 2


def test_live_call_prewarm_is_best_effort_when_providers_are_unavailable(
    monkeypatch,
) -> None:
    prewarm.clear_live_call_prewarm_state()
    store = _FakeStore()
    monkeypatch.setattr(prewarm.shared, "get_provider", lambda _provider_id: None)
    monkeypatch.setattr(prewarm, "get_tts_provider", lambda: None)

    app = FastAPI()
    prewarm.register_live_call_prewarm_routes(
        app,
        chat_store_factory=lambda: store,
    )
    client = TestClient(app)

    response = client.post(
        "/api/live-call/sessions/session-prewarm/prewarm",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["llm"]["status"] == "unavailable"
    assert response.json()["tts"]["status"] == "unavailable"
