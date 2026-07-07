from __future__ import annotations

from fastapi.testclient import TestClient

import app.gateway.rpg_map_routes as rpg_map_routes
from app.gateway.main import create_gateway_app
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_projection import initial_map_session_state


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:test", "session_id": "session:test"},
        "state": {
            "session_id": "session:test",
            "current_turn": 4,
            "world": {"weather": "Clear"},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
    }


def test_map_definition_is_cacheable_and_revision_aware() -> None:
    client = TestClient(create_gateway_app())
    path = f"/api/rpg/maps/{FROST_HAVEN_MAP_ID}"

    response = client.get(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["definition"]["map_id"] == FROST_HAVEN_MAP_ID
    assert payload["definition_revision"].startswith("sha256:")
    assert response.headers["cache-control"] == "public, max-age=3600, immutable"
    assert response.headers["etag"]

    cached = client.get(path, headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304

    known = client.get(path, params={"known_definition_revision": payload["definition_revision"]})
    assert known.status_code == 200
    assert known.json()["definition"] is None


def test_map_overlay_is_live_and_not_cacheable(monkeypatch) -> None:
    monkeypatch.setattr(rpg_map_routes, "load_session", lambda session_id: _session())
    client = TestClient(create_gateway_app())

    response = client.get(f"/api/rpg/sessions/session:test/maps/{FROST_HAVEN_MAP_ID}/overlay")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overlay"]["availability"] == "ready"
    assert payload["overlay"]["current_location_id"] == "rusty_flagon_tavern"
    assert payload["overlay_revision"] == 0
    assert payload["session_turn_index"] == 4
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["etag"]


def test_map_overlay_reports_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(rpg_map_routes, "load_session", lambda session_id: None)
    client = TestClient(create_gateway_app())

    response = client.get(f"/api/rpg/sessions/missing/maps/{FROST_HAVEN_MAP_ID}/overlay")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "session_not_found"


def test_unknown_map_returns_typed_not_found(monkeypatch) -> None:
    monkeypatch.setattr(rpg_map_routes, "load_session", lambda session_id: _session())
    client = TestClient(create_gateway_app())

    definition = client.get("/api/rpg/maps/map:missing")
    overlay = client.get("/api/rpg/sessions/session:test/maps/map:missing/overlay")

    assert definition.status_code == 404
    assert definition.json()["detail"]["error"] == "map_definition_not_found"
    assert overlay.status_code == 404
    assert overlay.json()["detail"]["error"] == "map_definition_not_found"
