from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

import app.gateway.rpg_map_routes as rpg_map_routes
from app.gateway.main import create_gateway_app
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_hierarchy_fixtures import FROSTED_FLAGON_INTERIOR_MAP_ID
from app.rpg.map_projection import initial_map_session_state


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:test", "session_id": "session:test"},
        "state": {
            "session_id": "session:test",
            "current_turn": 2,
            "player": {"location_id": "rusty_flagon_tavern"},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
    }


def test_enter_action_returns_child_definition_and_overlay(monkeypatch) -> None:
    stored = _session()
    monkeypatch.setattr(rpg_map_routes, "load_session", lambda session_id: deepcopy(stored))
    monkeypatch.setattr(rpg_map_routes, "save_session", lambda session, compact=False: session)
    client = TestClient(create_gateway_app())
    overlay_path = f"/api/rpg/sessions/session:test/maps/{FROST_HAVEN_MAP_ID}/overlay"
    overlay = client.get(overlay_path).json()

    response = client.post(
        f"/api/rpg/sessions/session:test/maps/{FROST_HAVEN_MAP_ID}/map-actions",
        json={
            "action": "enter",
            "target_object_id": "building:frost_haven_inn",
            "definition_revision": overlay["definition_revision"],
            "overlay_revision": overlay["overlay_revision"],
            "client_action_id": "action:enter-inn",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["map_id"] == FROSTED_FLAGON_INTERIOR_MAP_ID
    assert payload["action_result"]["previous_map_id"] == FROST_HAVEN_MAP_ID
    assert payload["game"]["map_state"]["current_map_id"] == FROSTED_FLAGON_INTERIOR_MAP_ID
    assert payload["overlay"]["map_id"] == FROSTED_FLAGON_INTERIOR_MAP_ID
    assert payload["overlay"]["availability"] == "ready"
