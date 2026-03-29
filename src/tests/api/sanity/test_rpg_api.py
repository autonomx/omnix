"""
RPG API endpoint tests – healthcheck, sanity, and game creation.

These tests use the Flask test client (no running server needed) to verify
that RPG HTTP routes respond correctly and game lifecycle operations work.

Run with:
    PYTHONPATH="src" python -m pytest src/tests/api/sanity/test_rpg_api.py -v --noconftest
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from unittest.mock import patch, MagicMock

# Ensure src/ is on the path so ``import app`` resolves to the package,
# not the root-level ``app.py`` script.
_SRC_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir)
_SRC_DIR = os.path.normpath(_SRC_DIR)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def flask_app():
    """Create a Flask test application for API tests."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def flask_client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_WORLD_DATA = {
    "name": "Eldoria",
    "description": "A land of ancient forests and crumbling towers.",
    "lore": "Long ago the Elders sealed the gates of shadow.",
    "genre": "medieval fantasy",
    "rules": {
        "technology_level": "pre-industrial",
        "magic_system": "limited",
        "allowed_items": ["swords", "bows"],
        "forbidden_items": ["guns"],
        "custom_rules": [],
        "existing_creatures": ["goblin", "dragon"],
    },
    "locations": [
        {
            "name": "Town Square",
            "description": "A bustling town square.",
            "connected_to": ["Forest", "Inn"],
        }
    ],
    "factions": [],
    "npcs": [
        {
            "name": "Greta",
            "role": "merchant",
            "personality": ["friendly"],
            "goals": ["sell goods"],
            "stats": {},
            "relationships": {},
            "inventory": ["healing potion"],
            "location": "Town Square",
        }
    ],
    "items_catalog": [],
    "starting_location": "Town Square",
    "agent_profiles": {},
}


def _patch_build_world():
    """Return a mock patch that makes build_world return MOCK_WORLD_DATA."""
    return patch("app.rpg.pipeline.agents.build_world", return_value=MOCK_WORLD_DATA)


def _patch_persistence():
    """Patch persistence so tests don't touch the filesystem."""
    return patch("app.rpg.pipeline.save_game")


# ---------------------------------------------------------------------------
# Health / Sanity
# ---------------------------------------------------------------------------


class TestHealthSanity:
    """Verify the health endpoint is reachable and returns a valid response."""

    def test_health_endpoint_returns_200(self, flask_client):
        resp = flask_client.get("/api/health")
        assert resp.status_code in (200, 503)

    def test_health_endpoint_returns_json(self, flask_client):
        resp = flask_client.get("/api/health")
        assert resp.content_type.startswith("application/json")


# ---------------------------------------------------------------------------
# RPG Game Listing
# ---------------------------------------------------------------------------


class TestRPGListGames:
    """GET /api/rpg/games – listing games."""

    def test_list_games_returns_200(self, flask_client):
        resp = flask_client.get("/api/rpg/games")
        assert resp.status_code == 200

    def test_list_games_returns_success(self, flask_client):
        resp = flask_client.get("/api/rpg/games")
        data = resp.get_json()
        assert data["success"] is True
        assert isinstance(data["games"], list)


# ---------------------------------------------------------------------------
# RPG Game Creation
# ---------------------------------------------------------------------------


class TestRPGCreateGame:
    """POST /api/rpg/games – creating a new game session."""

    def test_create_game_returns_201(self, flask_client):
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post(
                "/api/rpg/games",
                json={"seed": 42, "genre": "medieval fantasy", "player_name": "Hero"},
            )
            assert resp.status_code == 201

    def test_create_game_response_shape(self, flask_client):
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post(
                "/api/rpg/games",
                json={"seed": 42},
            )
            data = resp.get_json()
            assert data["success"] is True
            assert "session_id" in data
            assert "world" in data
            assert "player" in data
            assert "opening" in data

    def test_create_game_world_fields(self, flask_client):
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post("/api/rpg/games", json={"seed": 42})
            world = resp.get_json()["world"]
            assert world["name"] == "Eldoria"
            assert world["genre"] == "medieval fantasy"

    def test_create_game_player_name(self, flask_client):
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post(
                "/api/rpg/games",
                json={"seed": 42, "player_name": "Aria"},
            )
            player = resp.get_json()["player"]
            assert player["name"] == "Aria"

    def test_create_game_default_player_name(self, flask_client):
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post("/api/rpg/games", json={"seed": 42})
            player = resp.get_json()["player"]
            assert player["name"] == "Player"

    def test_create_game_opening_contains_lore(self, flask_client):
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post("/api/rpg/games", json={"seed": 42})
            opening = resp.get_json()["opening"]
            assert "Eldoria" in opening
            assert "Elders" in opening

    def test_create_game_no_body(self, flask_client):
        """POST with empty JSON body should still succeed (uses defaults)."""
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post(
                "/api/rpg/games",
                json={},
            )
            assert resp.status_code == 201

    def test_create_game_bad_seed_returns_400(self, flask_client):
        resp = flask_client.post(
            "/api/rpg/games",
            json={"seed": "not_a_number"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "Seed" in data["error"]

    def test_create_game_world_builder_failure_returns_500(self, flask_client):
        with patch("app.rpg.pipeline.agents.build_world", return_value=None):
            resp = flask_client.post("/api/rpg/games", json={"seed": 42})
            assert resp.status_code == 500
            data = resp.get_json()
            assert data["success"] is False

    def test_create_game_custom_genre(self, flask_client):
        with _patch_build_world(), _patch_persistence():
            resp = flask_client.post(
                "/api/rpg/games",
                json={"seed": 42, "genre": "sci-fi"},
            )
            assert resp.status_code == 201

    def test_create_game_with_custom_lore(self, flask_client):
        with _patch_build_world() as mock_bw, _patch_persistence():
            resp = flask_client.post(
                "/api/rpg/games",
                json={"seed": 42, "lore": "Dragons once ruled"},
            )
            assert resp.status_code == 201
            mock_bw.assert_called_once()
            _, kwargs = mock_bw.call_args
            assert kwargs["custom_lore"] == "Dragons once ruled"

    def test_create_game_with_world_prompt(self, flask_client):
        with _patch_build_world() as mock_bw, _patch_persistence():
            resp = flask_client.post(
                "/api/rpg/games",
                json={"seed": 42, "world_prompt": "Make it spooky"},
            )
            assert resp.status_code == 201
            _, kwargs = mock_bw.call_args
            assert kwargs["world_prompt"] == "Make it spooky"


# ---------------------------------------------------------------------------
# RPG Game Retrieval
# ---------------------------------------------------------------------------


class TestRPGGetGame:
    """GET /api/rpg/games/<session_id> – retrieving a game."""

    def test_get_nonexistent_game_returns_404(self, flask_client):
        resp = flask_client.get("/api/rpg/games/nonexistent_id_xyz")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False

    def test_get_created_game(self, flask_client):
        with _patch_build_world(), \
             patch("app.rpg.pipeline.save_game"), \
             patch("app.rpg.routes.load_game") as mock_load:
            # First create a game to get a session_id
            create_resp = flask_client.post(
                "/api/rpg/games", json={"seed": 42}
            )
            session_id = create_resp.get_json()["session_id"]

            # Build a GameSession to return from load_game
            from app.rpg.models import GameSession, WorldState, PlayerState
            fake_session = GameSession(
                session_id=session_id,
                world=WorldState(name="Eldoria", genre="medieval fantasy"),
                player=PlayerState(name="Player"),
            )
            mock_load.return_value = fake_session

            resp = flask_client.get(f"/api/rpg/games/{session_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "game" in data
            assert data["game"]["session_id"] == session_id


# ---------------------------------------------------------------------------
# RPG Game Deletion
# ---------------------------------------------------------------------------


class TestRPGDeleteGame:
    """DELETE /api/rpg/games/<session_id> – deleting a game."""

    def test_delete_nonexistent_game_returns_404(self, flask_client):
        resp = flask_client.delete("/api/rpg/games/nonexistent_id_xyz")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False

    def test_delete_existing_game(self, flask_client):
        with patch("app.rpg.routes.delete_game", return_value=True):
            resp = flask_client.delete("/api/rpg/games/some_session_id")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True


# ---------------------------------------------------------------------------
# RPG State Query Endpoints – 404 for missing games
# ---------------------------------------------------------------------------


class TestRPGStateEndpoints:
    """Verify state-query endpoints return 404 for non-existent games."""

    @pytest.mark.parametrize("path", [
        "/api/rpg/games/bad_id/player",
        "/api/rpg/games/bad_id/world",
        "/api/rpg/games/bad_id/npcs",
        "/api/rpg/games/bad_id/quests",
        "/api/rpg/games/bad_id/history",
        "/api/rpg/games/bad_id/replay",
    ])
    def test_state_endpoints_return_404_for_missing_game(self, flask_client, path):
        resp = flask_client.get(path)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RPG Turn Execution
# ---------------------------------------------------------------------------


class TestRPGTurnExecution:
    """POST /api/rpg/games/<id>/turn – turn execution edge cases."""

    def test_turn_missing_game_returns_404(self, flask_client):
        resp = flask_client.post(
            "/api/rpg/games/nonexistent/turn",
            json={"input": "look around"},
        )
        assert resp.status_code == 404

    def test_turn_empty_input_returns_400(self, flask_client):
        with patch("app.rpg.routes.load_game") as mock_load:
            from app.rpg.models import GameSession
            mock_load.return_value = GameSession()
            resp = flask_client.post(
                "/api/rpg/games/some_id/turn",
                json={"input": ""},
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data["success"] is False

    def test_turn_no_input_field_returns_400(self, flask_client):
        with patch("app.rpg.routes.load_game") as mock_load:
            from app.rpg.models import GameSession
            mock_load.return_value = GameSession()
            resp = flask_client.post(
                "/api/rpg/games/some_id/turn",
                json={},
            )
            assert resp.status_code == 400
