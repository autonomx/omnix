from __future__ import annotations

import pytest
from tests.support.routers import include_router_registrar

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.apps.rpg.api.feature_routes.rpg_session_routes as routes
from app.apps.rpg.api.feature_routes.rpg_session_routes import register_rpg_session_routes
from app.apps.rpg.session import durable_store
from app.apps.rpg.session.service import load_session


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = FastAPI()
    include_router_registrar(app, register_rpg_session_routes)
    return TestClient(app)


def _new_game_payload() -> dict[str, object]:
    return {
        "campaign_template": "classic_fantasy",
        "tone": "heroic adventure",
        "starting_location": "rusty_flagon_tavern",
        "seed": 42,
    }


def _region_environment(region_id: str, climate: str, condition: str) -> dict[str, object]:
    return {
        "environment_version": 1,
        "region_id": region_id,
        "climate_profile_id": climate,
        "environment_seed": 42,
        "calendar": {"year": 1, "day_of_year": 278, "days_per_year": 360},
        "absolute_minutes": 480,
        "active_events": [
            {
                "id": f"weather_{region_id}",
                "type": "weather",
                "condition": condition,
                "intensity": "moderate",
                "remaining_minutes": 600,
                "started_at_minute": 480,
            }
        ],
        "recent_conditions": {},
        "event_history": [],
    }


@pytest.mark.postgres
def test_new_game_response_includes_non_persisted_environment_snapshot(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.post("/api/rpg/new-game", json=_new_game_payload())

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is True
    snapshot = result["environment_snapshot"]
    contract = result["environment_narration_contract"]
    assert snapshot == result["game"]["environment_snapshot"]
    assert contract == result["game"]["environment_narration_contract"]
    assert contract["authority"] == "read_only_environment_snapshot"
    assert "create_new_weather" in contract["forbidden"]
    assert snapshot["region_id"] == "market_road"
    assert snapshot["weather"]["condition"] == "rain"
    assert snapshot["context"]["exposure"] == "indoor"

    persisted = load_session(result["session_id"])
    assert "environment_snapshot" not in persisted["state"]
    assert "environment_narration_contract" not in persisted["state"]
    assert persisted["state"]["world"]["environment"]["region_id"] == "market_road"


@pytest.mark.postgres
def test_read_session_response_includes_environment_snapshot_for_existing_session(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/rpg/new-game", json=_new_game_payload()).json()

    response = client.get(f"/api/rpg/sessions/{created['session_id']}")

    assert response.status_code == 200
    result = response.json()
    assert result["environment_snapshot"]["display"]["day_time"] == "Day 1 • 08:00"
    assert result["environment_narration_contract"]["environment_snapshot"] == result["environment_snapshot"]
    assert result["game"]["environment_snapshot"]["light_level"] == "tavern_lit"
    assert result["session"]["state"]["environment_snapshot"]["terrain_condition"] == "interior_floor"


def test_read_session_response_uses_active_region_environment_snapshot(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    session = {
        "session_id": "multi-region",
        "state": {
            "world": {
                "environment": {"active_region_id": "southern_coast"},
                "regions": {
                    "northern_mountains": {
                        "environment": _region_environment(
                            "northern_mountains",
                            "northern_mountains",
                            "snow",
                        )
                    },
                    "southern_coast": {
                        "environment": _region_environment(
                            "southern_coast",
                            "road_lowlands",
                            "rain",
                        )
                    },
                },
            },
            "scene": {
                "environment_context": {
                    "exposure": "outdoor",
                    "shelter": "exposed",
                    "region_id": "southern_coast",
                    "location_id": "coast_road",
                }
            },
        },
    }
    monkeypatch.setattr(routes, "load_session", lambda session_id: session)

    response = client.get("/api/rpg/sessions/multi-region")

    assert response.status_code == 200
    result = response.json()
    snapshot = result["environment_snapshot"]
    assert snapshot["region_id"] == "southern_coast"
    assert snapshot["weather"]["condition"] == "rain"
    mountains = result["session"]["state"]["world"]["regions"]["northern_mountains"]
    assert mountains["environment"]["active_events"][0]["condition"] == "snow"


@pytest.mark.postgres
def test_list_sessions_decorates_session_state_with_environment_snapshot(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.post("/api/rpg/new-game", json=_new_game_payload())

    response = client.get("/api/rpg/sessions")

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert sessions
    snapshot = sessions[0]["state"]["environment_snapshot"]
    contract = sessions[0]["state"]["environment_narration_contract"]
    assert snapshot["climate_profile_id"] == "temperate_hills"
    assert snapshot["visibility"] == "interior"
    assert contract["environment_snapshot"] == snapshot
