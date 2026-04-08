"""
Flask Blueprint for the AI Role-Playing System API routes.

All /api/rpg/games* endpoints are deprecated and return 410 Gone.
Clients should migrate to /api/rpg/adventure/start and /api/rpg/session/turn.
"""

import json
import logging

from flask import Blueprint, Response, jsonify, request

logger = logging.getLogger(__name__)

rpg_bp = Blueprint("rpg", __name__)


_DEPRECATION_BODY = {
    "success": False,
    "error": "legacy_rpg_games_api_removed",
    "recommended_create": "/api/rpg/adventure/start",
    "recommended_turn": "/api/rpg/session/turn",
}


def _gone_response():
    """Return a 410 Gone JSON response with deprecation headers."""
    response = jsonify(_DEPRECATION_BODY)
    response.headers["X-Omnix-RPG-Recommended-Create"] = "/api/rpg/adventure/start"
    response.headers["X-Omnix-RPG-Recommended-Turn"] = "/api/rpg/session/turn"
    return response, 410


def _gone_sse():
    """Return a 410 Gone SSE response for streaming endpoints."""
    def generate():
        yield f"data: {json.dumps({'type': 'error', 'error': 'legacy_rpg_games_api_removed'})}\n\n"
    return Response(generate(), mimetype="text/event-stream"), 410


# ---------------------------------------------------------------------------
# Game Management
# ---------------------------------------------------------------------------

@rpg_bp.route("/api/rpg/games", methods=["GET"])
def list_rpg_games():
    """List all saved RPG game sessions. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games", methods=["POST"])
def create_rpg_game():
    """Create a new RPG game session. **Deprecated: returns 410.**"""
    return _gone_response()


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event data line."""
    return f"data: {json.dumps(data)}\n\n"


@rpg_bp.route("/api/rpg/games/stream", methods=["POST"])
def stream_game_creation():
    """Create a new RPG game session with streamed progress via SSE. **Deprecated: returns 410.**"""
    return _gone_sse()


@rpg_bp.route("/api/rpg/games/<session_id>", methods=["GET"])
def get_rpg_game(session_id):
    """Get the full state of an RPG game session. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>", methods=["DELETE"])
def delete_rpg_game(session_id):
    """Delete an RPG game session. **Deprecated: returns 410.**"""
    return _gone_response()


# ---------------------------------------------------------------------------
# Turn Execution
# ---------------------------------------------------------------------------

@rpg_bp.route("/api/rpg/games/<session_id>/turn", methods=["POST"])
def execute_rpg_turn(session_id):
    """Execute a player turn in an RPG game. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>/turn/stream", methods=["POST"])
def execute_rpg_turn_stream(session_id):
    """Execute a player turn and stream narration via SSE. **Deprecated: returns 410.**"""
    return _gone_sse()


# ---------------------------------------------------------------------------
# State Queries
# ---------------------------------------------------------------------------

@rpg_bp.route("/api/rpg/games/<session_id>/player", methods=["GET"])
def get_player_state(session_id):
    """Get the current player state. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>/world", methods=["GET"])
def get_world_state(session_id):
    """Get the current world state. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>/npcs", methods=["GET"])
def get_npcs(session_id):
    """Get all NPCs. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>/quests", methods=["GET"])
def get_quests(session_id):
    """Get quests. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>/history", methods=["GET"])
def get_history(session_id):
    """Get the game history log. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>/replay", methods=["GET"])
def get_replay(session_id):
    """Get the deterministic replay log. **Deprecated: returns 410.**"""
    return _gone_response()


@rpg_bp.route("/api/rpg/games/<session_id>/replay", methods=["POST"])
def run_replay(session_id):
    """Re-execute a turn deterministically. **Deprecated: returns 410.**"""
    return _gone_response()
