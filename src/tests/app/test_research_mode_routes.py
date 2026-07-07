from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import ChatSessionStore, CreateChatSessionRequest
import app.gateway.research_mode_routes as routes


def test_conversation_research_mode_is_backend_persisted(tmp_path, monkeypatch) -> None:
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Research chat"))
    monkeypatch.setattr(routes, "default_chat_store", lambda: store)

    app = FastAPI()
    routes.register_research_mode_routes(app)
    client = TestClient(app)

    response = client.post(
        f"/api/chat/sessions/{session.id}/research-mode",
        json={"research_mode_override": "deep"},
    )

    assert response.status_code == 200
    assert response.json()["research_mode_override"] == "deep"
    assert ChatSessionStore(tmp_path / "chat.json").get_session(session.id).research_mode_override == "deep"


def test_conversation_research_mode_can_return_to_profile_default(tmp_path, monkeypatch) -> None:
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(
        CreateChatSessionRequest(title="Research chat", research_mode_override="quick")
    )
    monkeypatch.setattr(routes, "default_chat_store", lambda: store)

    app = FastAPI()
    routes.register_research_mode_routes(app)
    client = TestClient(app)

    response = client.post(
        f"/api/chat/sessions/{session.id}/research-mode",
        json={"research_mode_override": None},
    )

    assert response.status_code == 200
    assert response.json()["research_mode_override"] is None
