from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


def _session(client: TestClient) -> str:
    response = client.post("/api/chat/sessions", json={"title": "Rendering"})
    assert response.status_code == 200
    return response.json()["id"]


def test_live_conversation_rendering_routes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_LIVE_PRONUNCIATION_PATH", str(tmp_path / "pronunciations.json"))
    client = TestClient(create_gateway_app())
    session_id = _session(client)

    plan = client.post(
        f"/api/chat/sessions/{session_id}/live-conversation/delivery-plan",
        json={"text": "I'm sorry. Take your time.", "stance": "listen", "serious": True},
    )
    assert plan.status_code == 200
    assert plan.json()["speech_act"] == "reassurance"
    assert plan.json()["pace"] == "slightly_slow"

    created = client.post(
        f"/api/chat/sessions/{session_id}/live-conversation/pronunciations",
        json={"phrase": "Nika", "pronunciation": "NEE-kah", "locale": "en-US"},
    )
    assert created.status_code == 200
    entry = created.json()["entries"][0]

    listed = client.get(f"/api/chat/sessions/{session_id}/live-conversation/pronunciations")
    assert listed.status_code == 200
    assert listed.json()["entries"] == [entry]

    removed = client.delete(
        f"/api/chat/sessions/{session_id}/live-conversation/pronunciations/{entry['id']}"
    )
    assert removed.status_code == 200
    assert removed.json()["entries"] == []


def test_rendering_routes_require_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    client = TestClient(create_gateway_app())

    response = client.get("/api/chat/sessions/chat:missing/live-conversation/pronunciations")

    assert response.status_code == 404
