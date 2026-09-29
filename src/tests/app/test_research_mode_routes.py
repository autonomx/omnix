from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatSessionStore, CreateChatSessionRequest
import app.chat.research_mode_routes as routes
import app.chat.character_store as character_store


class _Segment:
    id = "segment:test"


class _CharacterRepository:
    def create_segment(self, **_kwargs):
        return _Segment()


def _use_memory_character_repository(monkeypatch) -> None:
    monkeypatch.setattr(character_store, "_character_repository", _CharacterRepository)
    monkeypatch.setattr(character_store, "_attach_character_snapshot", lambda _session: None)


def test_conversation_research_mode_is_backend_persisted(tmp_path, monkeypatch) -> None:
    _use_memory_character_repository(monkeypatch)
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Research chat"))
    app = FastAPI()
    app.include_router(routes.create_research_mode_router(chat_store_factory=lambda: store))
    client = TestClient(app)

    response = client.post(
        f"/api/chat/sessions/{session.id}/research-mode",
        json={"research_mode_override": "deep"},
    )

    assert response.status_code == 200
    assert response.json()["research_mode_override"] == "deep"
    assert ChatSessionStore(tmp_path / "chat.json").get_session(session.id).research_mode_override == "deep"


def test_conversation_research_mode_can_return_to_profile_default(tmp_path, monkeypatch) -> None:
    _use_memory_character_repository(monkeypatch)
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(
        CreateChatSessionRequest(title="Research chat", research_mode_override="quick")
    )
    app = FastAPI()
    app.include_router(routes.create_research_mode_router(chat_store_factory=lambda: store))
    client = TestClient(app)

    response = client.post(
        f"/api/chat/sessions/{session.id}/research-mode",
        json={"research_mode_override": None},
    )

    assert response.status_code == 200
    assert response.json()["research_mode_override"] is None
