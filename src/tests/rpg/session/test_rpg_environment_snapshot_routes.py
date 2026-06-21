from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_session_routes import register_rpg_session_routes
from app.rpg.session import durable_store
from app.rpg.session.service import load_session


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = FastAPI()
    register_rpg_session_routes(app)
    return TestClient(app)


def _new_game_payload() -> dict[str, object]:
    return {
        "campaign_template": "classic_fantasy",
        "tone": "heroic adventure",
        "starting_location": "rusty_flagon_tavern",
        "seed": 42,
    }


def test_new_game_response_includes_non_persisted_environment_snapshot(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post("/api/rpg/new-game", json=_new_game_payload())

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is True
    snapshot = result["environment_snapshot"]
    assert snapshot == result["game"]["environment_snapshot"]
    assert snapshot["region_id"] == "market_road"
    assert snapshot["weather"]["condition"] == "rain"
    assert snapshot["context"]["exposure"] == "indoor"

    persisted = load_session(result["session_id"])
    assert "environment_snapshot" not in persisted["state"]
    assert persisted["state"]["world"]["environment"]["region_id"] == "market_road"


def test_read_session_response_includes_environment_snapshot_for_existing_session(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/rpg/new-game", json=_new_game_payload()).json()

    response = client.get(f"/api/rpg/sessions/{created['session_id']}")

    assert response.status_code == 200
    result = response.json()
    assert result["environment_snapshot"]["display"]["day_time"] == "Day 1 • 08:00"
    assert result["game"]["environment_snapshot"]["light_level"] == "tavern_lit"
    assert result["session"]["state"]["environment_snapshot"]["terrain_condition"] == "interior_floor"


def test_list_sessions_decorates_session_state_with_environment_snapshot(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.post("/api/rpg/new-game", json=_new_game_payload())

    response = client.get("/api/rpg/sessions")

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert sessions
    snapshot = sessions[0]["state"]["environment_snapshot"]
    assert snapshot["climate_profile_id"] == "temperate_hills"
    assert snapshot["visibility"] == "interior"
