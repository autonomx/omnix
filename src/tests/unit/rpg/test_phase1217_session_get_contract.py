from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.compat_router import create_rpg_compatibility_router


def test_session_get_surfaces_bootstrap_payload_in_game_envelope(monkeypatch):
    app = FastAPI()
    app.include_router(create_rpg_compatibility_router())
    client = TestClient(app)

    fake_session = {
        "manifest": {"session_id": "session:test"},
        "runtime_state": {},
        "simulation_state": {},
    }
    fake_payload = {
        "session_id": "session:test",
        "choices": [{"id": "c1", "text": "Look around"}],
        "npcs": [{"id": "npc_bran", "name": "Bran"}],
        "world": {"title": "Test World"},
        "narration": ["Opening line"],
        "world_events": [],
        "turn_count": 0,
    }

    monkeypatch.setattr(
        "app.rpg.session.runtime.load_runtime_session",
        lambda session_id: fake_session if session_id == "session:test" else None,
    )
    monkeypatch.setattr(
        "app.rpg.session.runtime.build_frontend_bootstrap_payload",
        lambda session: dict(fake_payload),
    )

    res = client.post("/api/rpg/session/get", json={"session_id": "session:test"})
    assert res.status_code == 200
    body = res.json()

    assert body["ok"] is True
    assert body["game"] == fake_payload
    assert body["game"]["session_id"] == "session:test"
    assert body["game"]["choices"] == fake_payload["choices"]
    assert body["game"]["npcs"] == fake_payload["npcs"]
    assert body["game"]["world"] == fake_payload["world"]
    assert body["game"]["narration"] == fake_payload["narration"]
