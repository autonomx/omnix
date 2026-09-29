"""Functional tests for the FastAPI player-facing RPG routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.rpg_player_routes import rpg_player_bp


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(rpg_player_bp)
    return app


@pytest.fixture
def app() -> FastAPI:
    return _make_test_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestPlayerStateEndpoint:
    """Tests for /api/rpg/player/state endpoint."""

    def test_player_state_returns_initialized_state(self, client):
        """Player state endpoint returns initialized player state."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            }
        }
        resp = client.post("/api/rpg/player/state", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        ps = data["player_state"]
        assert "current_scene_id" in ps
        assert "current_mode" in ps
        assert "journal_entries" in ps
        assert "codex" in ps

    def test_player_state_preserves_tick(self, client):
        """Player state preserves tick from simulation state."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 42}
                }
            }
        }
        resp = client.post("/api/rpg/player/state", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_state"]["current_mode"] == "scene"


class TestPlayerJournalEndpoint:
    """Tests for /api/rpg/player/journal endpoint."""

    def test_journal_returns_bounded_entries(self, client):
        """Journal endpoint returns bounded journal entries."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            }
        }
        resp = client.post("/api/rpg/player/journal", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "journal_entries" in data
        assert isinstance(data["journal_entries"], list)


class TestPlayerCodexEndpoint:
    """Tests for /api/rpg/player/codex endpoint."""

    def test_codex_returns_codex_structure(self, client):
        """Codex endpoint returns codex structure with all buckets."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            }
        }
        resp = client.post("/api/rpg/player/codex", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        codex = data["codex"]
        assert "npcs" in codex
        assert "factions" in codex
        assert "locations" in codex
        assert "threads" in codex


class TestPlayerObjectivesEndpoint:
    """Tests for /api/rpg/player/objectives endpoint."""

    def test_objectives_returns_active_objectives(self, client):
        """Objectives endpoint returns active objectives list."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            }
        }
        resp = client.post("/api/rpg/player/objectives", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "active_objectives" in data
        assert isinstance(data["active_objectives"], list)


class TestPlayerDialogueEndpoint:
    """Tests for dialogue enter/exit endpoints."""

    def test_dialogue_enter_updates_mode_and_active_npc(self, client):
        """Dialogue enter updates mode to dialogue and sets active_npc_id."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            },
            "npc_id": "npc_merchant",
            "scene_id": "s_town_square",
        }
        resp = client.post("/api/rpg/player/dialogue/enter", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        ps = data["player_state"]
        assert ps["current_mode"] == "dialogue"
        assert ps["active_npc_id"] == "npc_merchant"

    def test_dialogue_exit_resets_mode(self, client):
        """Dialogue exit resets mode back to scene."""
        # First enter dialogue
        enter_payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            },
            "npc_id": "npc_merchant",
            "scene_id": "s_town_square",
        }
        resp = client.post("/api/rpg/player/dialogue/enter", json=enter_payload)
        enter_data = resp.json()

        # Then exit
        exit_payload = {
            "setup_payload": enter_data["setup_payload"],
        }
        resp = client.post("/api/rpg/player/dialogue/exit", json=exit_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        ps = data["player_state"]
        assert ps["current_mode"] == "scene"
        assert ps["active_npc_id"] == ""

    def test_dialogue_exit_custom_fallback(self, client):
        """Dialogue exit supports custom fallback mode."""
        # First enter dialogue
        enter_payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            },
            "npc_id": "npc_guard",
            "scene_id": "s_gate",
        }
        resp = client.post("/api/rpg/player/dialogue/enter", json=enter_payload)
        enter_data = resp.json()

        # Exit with custom fallback
        exit_payload = {
            "setup_payload": enter_data["setup_payload"],
            "fallback_mode": "travel",
        }
        resp = client.post("/api/rpg/player/dialogue/exit", json=exit_payload)
        assert resp.status_code == 200
        data = resp.json()
        ps = data["player_state"]
        assert ps["current_mode"] == "travel"


class TestPlayerEncounterEndpoint:
    """Tests for /api/rpg/player/encounter endpoint."""

    def test_encounter_builds_payload_from_scene(self, client):
        """Encounter endpoint builds encounter payload from a scene."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            },
            "scene": {
                "scene_id": "s_ambush",
                "title": "Ambush!",
                "actors": [
                    {"id": "npc_bandit1", "name": "Bandit Leader"},
                    {"id": "npc_bandit2", "name": "Bandit Thug"},
                ],
                "choices": [
                    {"id": "c_fight", "text": "Fight"},
                    {"id": "c_flee", "text": "Flee"},
                ],
                "summary": "Bandits jump out from behind trees",
            },
        }
        resp = client.post("/api/rpg/player/encounter", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        encounter = data["encounter"]
        assert encounter["scene_id"] == "s_ambush"
        assert len(encounter["actors"]) == 2
        assert len(encounter["choices"]) == 2
        assert "encounter_state" in encounter

    def test_encounter_bounded_actors_and_choices(self, client):
        """Encounter endpoint returns bounded actors and choices."""
        actors = [{"id": f"n{i}", "name": f"NPC {i}"} for i in range(15)]
        choices = [{"id": f"c{i}", "text": f"Choice {i}"} for i in range(10)]
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 1}
                }
            },
            "scene": {
                "scene_id": "s_battle",
                "actors": actors,
                "choices": choices,
            },
        }
        resp = client.post("/api/rpg/player/encounter", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        encounter = data["encounter"]
        # Actors are bounded to 8 by implementation
        assert len(encounter["actors"]) <= 8
        # Choices are bounded by implementation
        assert len(encounter["choices"]) <= 8
