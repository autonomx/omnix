from __future__ import annotations

from copy import deepcopy

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
            "player": {"location_id": "rusty_flagon_tavern"},
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
    assert client.get(path, headers={"If-None-Match": response.headers["etag"]}).status_code == 304
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
    assert payload["overlay"]["object_states"]
    assert payload["overlay_revision"] == 0
    assert payload["session_turn_index"] == 4
    assert response.headers["cache-control"] == "no-store"


def test_map_action_returns_authoritative_mutation_envelope(monkeypatch) -> None:
    stored = _session()
    monkeypatch.setattr(rpg_map_routes, "load_session", lambda session_id: deepcopy(stored))
    monkeypatch.setattr(rpg_map_routes, "save_session", lambda session, compact=False: session)
    client = TestClient(create_gateway_app())
    overlay = client.get(f"/api/rpg/sessions/session:test/maps/{FROST_HAVEN_MAP_ID}/overlay").json()

    response = client.post(
        f"/api/rpg/sessions/session:test/maps/{FROST_HAVEN_MAP_ID}/map-actions",
        json={
            "action": "travel",
            "target_object_id": "building:frost_haven_market",
            "route_id": "route:frost_haven:market_inn",
            "definition_revision": overlay["definition_revision"],
            "overlay_revision": overlay["overlay_revision"],
            "client_action_id": "action:route-test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["action_result"]["changed"] is True
    assert payload["game"]["map_state"]["current_location_id"] == "market_district"
    assert payload["overlay"]["current_location_id"] == "market_district"
    assert payload["overlay_revision"] == 1


def test_map_action_rejects_stale_and_locked_requests(monkeypatch) -> None:
    stored = _session()
    monkeypatch.setattr(rpg_map_routes, "load_session", lambda session_id: deepcopy(stored))
    monkeypatch.setattr(rpg_map_routes, "save_session", lambda session, compact=False: session)
    client = TestClient(create_gateway_app())
    overlay = client.get(f"/api/rpg/sessions/session:test/maps/{FROST_HAVEN_MAP_ID}/overlay").json()
    path = f"/api/rpg/sessions/session:test/maps/{FROST_HAVEN_MAP_ID}/map-actions"

    stale = client.post(path, json={
        "action": "inspect",
        "target_object_id": "building:frost_haven_inn",
        "definition_revision": overlay["definition_revision"],
        "overlay_revision": 99,
    })
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "stale_overlay_revision"

    stored["state"]["map_state"]["route_states"]["route:frost_haven:market_inn"] = {
        "status": "locked", "known": True, "safe": True
    }
    locked = client.post(path, json={
        "action": "travel",
        "target_object_id": "building:frost_haven_market",
        "route_id": "route:frost_haven:market_inn",
        "definition_revision": overlay["definition_revision"],
        "overlay_revision": 0,
    })
    assert locked.status_code == 409
    assert locked.json()["detail"]["error"] == "route_locked"


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
