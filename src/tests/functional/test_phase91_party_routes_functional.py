"""Phase 9.1 — Functional tests for Party / Companion API routes."""
from __future__ import annotations

import pytest


SIMULATION_STATE_TEMPLATE = {
    "tick": 1,
    "player_state": {
        "current_scene_id": "scene_1",
        "current_mode": "scene",
        "active_npc_id": "",
        "scene_history": [],
        "journal_entries": [],
        "codex": {"npcs": {}, "factions": {}, "locations": {}, "threads": {}},
        "active_objectives": [],
        "last_player_view": {},
        "inventory_state": {
            "items": [],
            "equipment": {},
            "capacity": 50,
            "currency": {},
            "last_loot": [],
        },
        "party_state": {
            "companions": [],
            "max_size": 3,
        },
    },
}


def _make_setup_payload(simulation_state=None):
    return {
        "metadata": {
            "simulation_state": simulation_state or SIMULATION_STATE_TEMPLATE,
        }
    }


class TestPartyRoutes:
    def test_party_returns_party_state(self, client):
        resp = client.post(
            "/api/rpg/player/party",
            json={"setup_payload": _make_setup_payload()},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "party_state" in data

    def test_recruit_adds_companion(self, client):
        resp = client.post(
            "/api/rpg/player/party/recruit",
            json={"setup_payload": _make_setup_payload(), "npc_id": "npc_1", "name": "Alice"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        companions = data["party_state"]["companions"]
        assert len(companions) == 1
        assert companions[0]["npc_id"] == "npc_1"

    def test_recruit_reject_duplicate(self, client):
        payload = _make_setup_payload()
        resp = client.post(
            "/api/rpg/player/party/recruit",
            json={"setup_payload": payload, "npc_id": "npc_1", "name": "Alice"},
        )
        assert resp.get_json()["ok"] is True

        same_setup = _make_setup_payload()
        same_setup["metadata"]["simulation_state"]["player_state"]["party_state"]["companions"] = [
            {"npc_id": "npc_1", "name": "Alice", "hp": 100, "loyalty": 0.5, "role": "ally"}
        ]
        resp = client.post(
            "/api/rpg/player/party/recruit",
            json={"setup_payload": same_setup, "npc_id": "npc_1", "name": "Alice"},
        )
        data = resp.get_json()
        assert len(data["party_state"]["companions"]) == 1

    def test_remove_companion(self, client):
        setup = _make_setup_payload()
        setup["metadata"]["simulation_state"]["player_state"]["party_state"]["companions"] = [
            {"npc_id": "npc_1", "name": "Alice", "hp": 100, "loyalty": 0.5, "role": "ally"}
        ]
        resp = client.post(
            "/api/rpg/player/party/remove",
            json={"setup_payload": setup, "npc_id": "npc_1"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["party_state"]["companions"]) == 0

    def test_remove_nonexistent_companion(self, client):
        resp = client.post(
            "/api/rpg/player/party/remove",
            json={"setup_payload": _make_setup_payload(), "npc_id": "npc_99"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True