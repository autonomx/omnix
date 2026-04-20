from fastapi.testclient import TestClient

from app import create_app


def test_session_get_surfaces_bootstrap_payload_at_top_level(monkeypatch):
    app = create_app()
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
        "app.rpg.api.rpg_session_routes.load_runtime_session",
        lambda session_id: fake_session if session_id == "session:test" else None,
    )
    monkeypatch.setattr(
        "app.rpg.api.rpg_session_routes.build_frontend_bootstrap_payload",
        lambda session: dict(fake_payload),
    )

    res = client.post("/api/rpg/session/get", json={"session_id": "session:test"})
    assert res.status_code == 200
    body = res.json()

    assert body["ok"] is True
    assert body["session_id"] == "session:test"
    assert body["choices"] == fake_payload["choices"]
    assert body["npcs"] == fake_payload["npcs"]
    assert body["world"] == fake_payload["world"]
    assert body["narration"] == fake_payload["narration"]
    assert body["game"] == fake_payload