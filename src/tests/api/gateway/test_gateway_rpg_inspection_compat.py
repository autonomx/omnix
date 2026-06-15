"""RPG inspection compatibility routes exposed through the gateway."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from app.gateway.main import create_gateway_app

    return TestClient(create_gateway_app(), raise_server_exceptions=False)


def test_gateway_rpg_inspect_timeline_returns_legacy_envelope() -> None:
    response = _client().post("/api/rpg/inspect/timeline", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "schema_version" in payload
    assert "timeline" in payload
    assert "latest_diff" in payload


def test_gateway_rpg_inspect_timeline_tick_returns_tick_view() -> None:
    response = _client().post("/api/rpg/inspect/timeline_tick", json={"tick": 0})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "tick_view" in payload


def test_gateway_rpg_inspect_tick_diff_returns_diff() -> None:
    response = _client().post(
        "/api/rpg/inspect/tick_diff",
        json={"before_state": {}, "after_state": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "tick_diff" in payload


def test_gateway_rpg_inspect_npc_reasoning_returns_reasoning_view() -> None:
    response = _client().post("/api/rpg/inspect/npc_reasoning", json={"npc_id": "npc-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "npc_reasoning" in payload


def test_gateway_rpg_inspect_world_events_returns_events_view() -> None:
    response = _client().post("/api/rpg/inspect/world_events", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "world_events" in payload
