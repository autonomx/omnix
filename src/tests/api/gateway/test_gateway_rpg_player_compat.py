"""RPG player-facing compatibility routes exposed through the gateway."""
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


def _setup_payload(simulation_state: dict) -> dict:
    return {"setup_payload": {"metadata": {"simulation_state": simulation_state}}}


def test_gateway_rpg_player_state_returns_initialized_state() -> None:
    response = _client().post("/api/rpg/player/state", json=_setup_payload({"tick": 42}))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    player_state = payload["player_state"]
    assert player_state["current_mode"] == "scene"
    assert "journal_entries" in player_state
    assert "codex" in player_state


def test_gateway_rpg_player_journal_returns_bounded_entries() -> None:
    entries = [{"id": str(index)} for index in range(60)]
    response = _client().post(
        "/api/rpg/player/journal",
        json=_setup_payload({"player_state": {"journal_entries": entries}}),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["journal_entries"]) == 50
    assert payload["journal_entries"][0]["id"] == "10"


def test_gateway_rpg_player_codex_returns_default_buckets() -> None:
    response = _client().post("/api/rpg/player/codex", json=_setup_payload({"tick": 1}))

    assert response.status_code == 200
    codex = response.json()["codex"]
    assert "npcs" in codex
    assert "factions" in codex
    assert "locations" in codex
    assert "threads" in codex


def test_gateway_rpg_player_objectives_returns_bounded_objectives() -> None:
    objectives = [{"id": str(index)} for index in range(30)]
    response = _client().post(
        "/api/rpg/player/objectives",
        json=_setup_payload({"player_state": {"active_objectives": objectives}}),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["active_objectives"]) == 20
    assert payload["active_objectives"][0]["id"] == "10"


def test_gateway_rpg_player_encounter_builds_bounded_payload() -> None:
    response = _client().post(
        "/api/rpg/player/encounter",
        json={
            **_setup_payload({"tick": 1}),
            "scene": {
                "scene_id": "s_ambush",
                "title": "Ambush",
                "actors": [{"id": f"npc-{index}", "name": f"NPC {index}"} for index in range(12)],
                "choices": [{"id": f"choice-{index}", "text": f"Choice {index}"} for index in range(12)],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    encounter = payload["encounter"]
    assert encounter["scene_id"] == "s_ambush"
    assert len(encounter["actors"]) == 8
    assert len(encounter["choices"]) == 8
    assert "encounter_state" in encounter
