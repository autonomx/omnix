"""Phase 1 — Functional tests for RPG Game Management API routes.

Tests the FastAPI game routes against a running server or using TestClient.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import the FastAPI app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server_fastapi import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestGameRoutesHealth:
    """Test basic route availability."""

    def test_list_games_route_exists(self, client):
        """GET /api/rpg/games should return 200 (even if empty)."""
        with patch("app.rpg.api.rpg_game_routes.list_games") as mock_list:
            mock_list.return_value = []
            response = client.get("/api/rpg/games")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "games" in data

    def test_create_game_route_exists(self, client):
        """POST /api/rpg/games should accept a valid request."""
        with patch("app.rpg.api.rpg_game_routes.create_new_game") as mock_create:
            mock_session = MagicMock()
            mock_session.session_id = "test-session-123"
            mock_session.world.name = "Test World"
            mock_session.world.genre = "fantasy"
            mock_session.world.description = "A test world"
            mock_session.world.lore = ""
            mock_session.player.to_dict.return_value = {"name": "Player"}
            mock_create.return_value = mock_session

            response = client.post(
                "/api/rpg/games",
                json={"genre": "fantasy", "player_name": "Player"}
            )
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert data["session_id"] == "test-session-123"

    def test_create_game_missing_seed_validation(self, client):
        """POST /api/rpg/games should reject non-integer seeds."""
        response = client.post(
            "/api/rpg/games",
            json={"seed": "not-a-number"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "Seed must be an integer" in data["error"]

    def test_create_game_failure(self, client):
        """POST /api/rpg/games should return 500 when creation fails."""
        with patch("app.rpg.api.rpg_game_routes.create_new_game") as mock_create:
            mock_create.return_value = None

            response = client.post(
                "/api/rpg/games",
                json={"genre": "fantasy"}
            )
            assert response.status_code == 500
            data = response.json()
            assert "Failed to generate game world" in data["error"]

    def test_get_game_not_found(self, client):
        """GET /api/rpg/games/{id} should return 404 for unknown session."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.get("/api/rpg/games/nonexistent-session")
            assert response.status_code == 404
            data = response.json()
            # FastAPI HTTPException returns {"detail": "..."}
            assert "Game not found" in data.get("detail", data.get("error", ""))

    def test_delete_game_not_found(self, client):
        """DELETE /api/rpg/games/{id} should return 404 for unknown session."""
        with patch("app.rpg.api.rpg_game_routes.delete_game") as mock_delete:
            mock_delete.return_value = False

            response = client.delete("/api/rpg/games/nonexistent-session")
            assert response.status_code == 404

    def test_get_player_state_not_found(self, client):
        """GET /api/rpg/games/{id}/player should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.get("/api/rpg/games/nonexistent-session/player")
            assert response.status_code == 404

    def test_get_world_state_not_found(self, client):
        """GET /api/rpg/games/{id}/world should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.get("/api/rpg/games/nonexistent-session/world")
            assert response.status_code == 404

    def test_get_npcs_not_found(self, client):
        """GET /api/rpg/games/{id}/npcs should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.get("/api/rpg/games/nonexistent-session/npcs")
            assert response.status_code == 404

    def test_get_quests_not_found(self, client):
        """GET /api/rpg/games/{id}/quests should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.get("/api/rpg/games/nonexistent-session/quests")
            assert response.status_code == 404

    def test_get_history_not_found(self, client):
        """GET /api/rpg/games/{id}/history should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.get("/api/rpg/games/nonexistent-session/history")
            assert response.status_code == 404

    def test_get_replay_not_found(self, client):
        """GET /api/rpg/games/{id}/replay should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.get("/api/rpg/games/nonexistent-session/replay")
            assert response.status_code == 404

    def test_execute_turn_not_found(self, client):
        """POST /api/rpg/games/{id}/turn should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.post(
                "/api/rpg/games/nonexistent-session/turn",
                json={"input": "hello"}
            )
            assert response.status_code == 404

    def test_execute_turn_missing_input(self, client):
        """POST /api/rpg/games/{id}/turn should return 400 for empty input."""
        mock_session = MagicMock()
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.post(
                "/api/rpg/games/test-session/turn",
                json={"input": ""}
            )
            assert response.status_code == 400

    def test_run_replay_not_found(self, client):
        """POST /api/rpg/games/{id}/replay should return 404."""
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = None

            response = client.post(
                "/api/rpg/games/nonexistent-session/replay",
                json={"turn": 1}
            )
            assert response.status_code == 404

    def test_run_replay_missing_turn(self, client):
        """POST /api/rpg/games/{id}/replay should return 400 without turn."""
        mock_session = MagicMock()
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.post(
                "/api/rpg/games/test-session/replay",
                json={}
            )
            assert response.status_code == 400

    def test_run_replay_invalid_turn(self, client):
        """POST /api/rpg/games/{id}/replay should return 400 for non-int turn."""
        mock_session = MagicMock()
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.post(
                "/api/rpg/games/test-session/replay",
                json={"turn": "not-a-number"}
            )
            assert response.status_code == 400


class TestGameRoutesSuccess:
    """Test successful responses with mocked dependencies."""

    def test_list_games_success(self, client):
        """GET /api/rpg/games should return list of games."""
        with patch("app.rpg.api.rpg_game_routes.list_games") as mock_list:
            mock_list.return_value = [
                {"session_id": "game1", "title": "Game 1"},
                {"session_id": "game2", "title": "Game 2"},
            ]
            response = client.get("/api/rpg/games")
            assert response.status_code == 200
            data = response.json()
            assert len(data["games"]) == 2

    def test_get_game_success(self, client):
        """GET /api/rpg/games/{id} should return game state."""
        mock_session = MagicMock()
        mock_session.to_dict.return_value = {"session_id": "test-123"}
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123")
            assert response.status_code == 200
            data = response.json()
            assert data["game"]["session_id"] == "test-123"

    def test_delete_game_success(self, client):
        """DELETE /api/rpg/games/{id} should succeed."""
        with patch("app.rpg.api.rpg_game_routes.delete_game") as mock_delete:
            mock_delete.return_value = True

            response = client.delete("/api/rpg/games/test-123")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_get_player_state_success(self, client):
        """GET /api/rpg/games/{id}/player should return player state."""
        mock_session = MagicMock()
        mock_session.player.to_dict.return_value = {"name": "Hero", "level": 5}
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/player")
            assert response.status_code == 200
            data = response.json()
            assert data["player"]["name"] == "Hero"

    def test_get_world_state_success(self, client):
        """GET /api/rpg/games/{id}/world should return world state."""
        mock_session = MagicMock()
        mock_session.world.to_dict.return_value = {"name": "Test World"}
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/world")
            assert response.status_code == 200
            data = response.json()
            assert data["world"]["name"] == "Test World"

    def test_get_npcs_success(self, client):
        """GET /api/rpg/games/{id}/npcs should return NPC list."""
        mock_session = MagicMock()
        mock_session.npcs = []
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/npcs")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_get_npcs_with_location_filter(self, client):
        """GET /api/rpg/games/{id}/npcs?location=X should filter by location."""
        mock_session = MagicMock()
        mock_session.get_npcs_at_location.return_value = []
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/npcs?location=tavern")
            assert response.status_code == 200
            mock_session.get_npcs_at_location.assert_called_once_with("tavern")

    def test_get_quests_success(self, client):
        """GET /api/rpg/games/{id}/quests should return quest list."""
        mock_session = MagicMock()
        mock_session.quests = []
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/quests")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_get_quests_active_filter(self, client):
        """GET /api/rpg/games/{id}/quests?status=active should filter."""
        mock_session = MagicMock()
        mock_session.get_active_quests.return_value = []
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/quests?status=active")
            assert response.status_code == 200
            mock_session.get_active_quests.assert_called_once()

    def test_get_history_success(self, client):
        """GET /api/rpg/games/{id}/history should return history."""
        mock_session = MagicMock()
        mock_session.history = []
        mock_session.turn_count = 5
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/history")
            assert response.status_code == 200
            data = response.json()
            assert data["turn_count"] == 5

    def test_get_history_with_limit(self, client):
        """GET /api/rpg/games/{id}/history?limit=N should limit results."""
        mock_session = MagicMock()
        mock_session.history = []
        mock_session.turn_count = 0
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/history?limit=10")
            assert response.status_code == 200

    def test_get_replay_success(self, client):
        """GET /api/rpg/games/{id}/replay should return replay logs."""
        mock_session = MagicMock()
        mock_session.turn_logs = []
        mock_session.turn_count = 3
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/replay")
            assert response.status_code == 200
            data = response.json()
            assert data["turn_count"] == 3

    def test_get_replay_by_turn(self, client):
        """GET /api/rpg/games/{id}/replay?turn=N should return specific turn."""
        mock_session = MagicMock()
        mock_turn_log = MagicMock()
        mock_turn_log.turn = 1
        mock_turn_log.to_dict.return_value = {"turn": 1}
        mock_session.turn_logs = [mock_turn_log]
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/replay?turn=1")
            assert response.status_code == 200
            data = response.json()
            assert data["turn_log"]["turn"] == 1

    def test_get_replay_turn_not_found(self, client):
        """GET /api/rpg/games/{id}/replay?turn=N should return 404 for missing turn."""
        mock_session = MagicMock()
        mock_session.turn_logs = []
        with patch("app.rpg.api.rpg_game_routes.load_game") as mock_load:
            mock_load.return_value = mock_session

            response = client.get("/api/rpg/games/test-123/replay?turn=99")
            assert response.status_code == 404