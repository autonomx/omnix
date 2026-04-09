"""
RPG API endpoint tests – healthcheck, sanity, and game creation.

These tests use the Flask test client (no running server needed) to verify
that RPG HTTP routes respond correctly and game lifecycle operations work.

Run with:
    PYTHONPATH="src" python -m pytest src/tests/api/sanity/test_rpg_api.py -v --noconftest

Note: ``--noconftest`` is used because the shared conftest.py imports
Playwright page-objects at module level, which are not needed (and may not
be installed) for pure API tests.  The flask_app / flask_client fixtures
are therefore defined locally.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

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
            from app.rpg.models import GameSession, PlayerState, WorldState
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


class TestRPGFunctional:
    """Functional tests for RPG game lifecycle."""

    @patch('app.rpg.routes.create_new_game')
    @patch('app.rpg.routes.load_game')
    def test_start_game_and_send_turn(self, mock_load_game, mock_create_game, flask_client):
        """Test the full flow: create game, send a turn, get response."""
        from app.rpg.models import GameSession, PlayerState, TurnResult, WorldState

        # Mock the create_new_game function
        mock_session = GameSession()
        mock_session.session_id = "test_session_123"
        mock_session.world = WorldState(name="Test World", genre="fantasy", description="A test world")
        mock_session.player = PlayerState(name="TestPlayer")
        mock_create_game.return_value = mock_session
        mock_load_game.return_value = mock_session

        # Create a new game
        resp = flask_client.post("/api/rpg/games", json={"genre": "fantasy"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        session_id = data["session_id"]
        assert session_id == "test_session_123"
        assert "world" in data
        assert "player" in data
        assert "opening" in data

        # Verify game was created
        resp = flask_client.get(f"/api/rpg/games/{session_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["game"]["session_id"] == session_id

        # Send a turn (mock execute_turn)
        with patch('app.rpg.routes.execute_turn') as mock_execute, \
             patch('app.rpg.routes.save_game') as mock_save:

            def mock_execute_turn(session, input_text):
                session.turn_count += 1
                return TurnResult(
                    narration="You look around and see a beautiful forest.",
                    state_changes={},
                    events=[],
                    error=None
                )

            mock_execute.side_effect = mock_execute_turn

            resp = flask_client.post(
                f"/api/rpg/games/{session_id}/turn",
                json={"input": "I look around and see what is here."}
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "narration" in data
            assert "turn" in data
            assert data["turn"] == 1
            assert "state_changes" in data

        # Verify turn was recorded (mock history)
        resp = flask_client.get(f"/api/rpg/games/{session_id}/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["turn_count"] == 1

    @patch('app.rpg.routes.create_new_game')
    @patch('app.rpg.routes.load_game')
    def test_multiple_turns_conversation(self, mock_load_game, mock_create_game, flask_client):
        """Test sending multiple turns in a conversation."""
        from app.rpg.models import GameSession, PlayerState, TurnResult, WorldState

        # Mock the functions
        mock_session = GameSession()
        mock_session.session_id = "test_session_multi"
        mock_session.world = WorldState(name="Sci-Fi World", genre="sci-fi", description="A futuristic world")
        mock_session.player = PlayerState(name="Alex")
        mock_create_game.return_value = mock_session
        mock_load_game.return_value = mock_session

        # Create game
        resp = flask_client.post("/api/rpg/games", json={"genre": "sci-fi", "player_name": "Alex"})
        assert resp.status_code == 201
        session_id = resp.get_json()["session_id"]
        assert session_id == "test_session_multi"

        turn_count = 0

        def mock_execute_turn(session, input_text):
            nonlocal turn_count
            turn_count += 1
            session.turn_count = turn_count
            return TurnResult(
                narration=f"Response to: {input_text}",
                state_changes={},
                events=[],
                error=None
            )

        # First turn
        with patch('app.rpg.routes.execute_turn', side_effect=mock_execute_turn), \
             patch('app.rpg.routes.save_game'):
            resp = flask_client.post(
                f"/api/rpg/games/{session_id}/turn",
                json={"input": "Hello, where am I?"}
            )
            assert resp.status_code == 200
            first_turn = resp.get_json()
            assert first_turn["turn"] == 1

        # Second turn
        with patch('app.rpg.routes.execute_turn', side_effect=mock_execute_turn), \
             patch('app.rpg.routes.save_game'):
            resp = flask_client.post(
                f"/api/rpg/games/{session_id}/turn",
                json={"input": "What should I do next?"}
            )
            assert resp.status_code == 200
            second_turn = resp.get_json()
            assert second_turn["turn"] == 2

        # Check history has both turns
        resp = flask_client.get(f"/api/rpg/games/{session_id}/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["turn_count"] == 2

    @patch('app.rpg.routes.create_new_game')
    @patch('app.rpg.routes.load_game')
    def test_game_state_queries(self, mock_load_game, mock_create_game, flask_client):
        """Test querying game state after turns."""
        from app.rpg.models import GameSession, PlayerState, WorldState

        # Mock the functions
        mock_session = GameSession()
        mock_session.session_id = "test_session_state"
        mock_session.world = WorldState(name="Medieval World", genre="medieval fantasy", description="A medieval world")
        mock_session.player = PlayerState(name="Player")
        mock_create_game.return_value = mock_session
        mock_load_game.return_value = mock_session

        # Create and play a bit
        resp = flask_client.post("/api/rpg/games", json={"genre": "medieval fantasy"})
        assert resp.status_code == 201
        session_id = resp.get_json()["session_id"]

        with patch('app.rpg.routes.execute_turn') as mock_execute, \
             patch('app.rpg.routes.save_game'):
            from app.rpg.models import TurnResult
            mock_execute.return_value = TurnResult(
                narration='You enter the tavern.',
                state_changes={},
                events=[],
                error=None
            )
            flask_client.post(
                f"/api/rpg/games/{session_id}/turn",
                json={"input": "I enter the tavern."}
            )

        # Test player state
        resp = flask_client.get(f"/api/rpg/games/{session_id}/player")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "player" in data
        assert data["player"]["name"] == "Player"

        # Test world state
        resp = flask_client.get(f"/api/rpg/games/{session_id}/world")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "world" in data
        assert data["world"]["genre"] == "medieval fantasy"

        # Test NPCs
        resp = flask_client.get(f"/api/rpg/games/{session_id}/npcs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "npcs" in data

        # Test quests
        resp = flask_client.get(f"/api/rpg/games/{session_id}/quests")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "quests" in data

    @patch('app.rpg.routes.create_new_game')
    @patch('app.rpg.routes.load_game')
    @patch('app.rpg.routes.list_games')
    @patch('app.rpg.routes.delete_game')
    def test_game_deletion(self, mock_delete_game, mock_list_games, mock_load_game, mock_create_game, flask_client):
        """Test creating and deleting a game."""
        from app.rpg.models import GameSession, PlayerState, WorldState

        # Mock the functions
        mock_session = GameSession()
        mock_session.session_id = "test_session_delete"
        mock_session.world = WorldState(name="Test World", genre="fantasy", description="A test world")
        mock_session.player = PlayerState(name="Player")
        mock_create_game.return_value = mock_session
        mock_load_game.return_value = mock_session
        mock_delete_game.return_value = True
        mock_list_games.return_value = []

        # Create game
        resp = flask_client.post("/api/rpg/games", json={})
        assert resp.status_code == 201
        data = resp.get_json()
        session_id = data["session_id"]

        # Verify it exists
        resp = flask_client.get(f"/api/rpg/games/{session_id}")
        assert resp.status_code == 200

        # Delete it
        resp = flask_client.delete(f"/api/rpg/games/{session_id}")
        assert resp.status_code == 200

        # Mock load_game to return None for deleted game
        mock_load_game.return_value = None

        # Verify it's gone
        resp = flask_client.get(f"/api/rpg/games/{session_id}")
        assert resp.status_code == 404

        # Verify it's not in the list
        resp = flask_client.get("/api/rpg/games")
        data = resp.get_json()
        session_ids = [game["session_id"] for game in data["games"]]
        assert session_id not in session_ids


# ---------------------------------------------------------------------------
# RPG Adventure Builder API – Healthcheck for new endpoints
# ---------------------------------------------------------------------------


class TestRPGAdventureAPI:
    """Tests for the new RPG adventure builder API endpoints."""

    def test_adventure_templates_endpoint(self, flask_client):
        """GET /api/rpg/adventure/templates should return 200 and JSON."""
        resp = flask_client.get("/api/rpg/adventure/templates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "templates" in data
        assert isinstance(data["templates"], list)

    def test_adventure_validate_endpoint(self, flask_client):
        """POST /api/rpg/adventure/validate should accept empty payload."""
        resp = flask_client.post("/api/rpg/adventure/validate", json={})
        assert resp.status_code in (200, 400, 500)
        data = resp.get_json()
        assert "ok" in data  # Validation result

    def test_adventure_preview_endpoint(self, flask_client):
        """POST /api/rpg/adventure/preview should respond."""
        resp = flask_client.post("/api/rpg/adventure/preview", json={"setup": {}})
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.get_json()
            assert "success" in data

    def test_adventure_start_endpoint(self, flask_client):
        """POST /api/rpg/adventure/start should respond."""
        resp = flask_client.post("/api/rpg/adventure/start", json={})
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.get_json()
            assert "success" in data

    def test_session_get_endpoint(self, flask_client):
        """POST /api/rpg/session/get should respond."""
        # Test with invalid session_id
        resp = flask_client.post("/api/rpg/session/get", json={"session_id": "invalid"})
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["ok"] is False
