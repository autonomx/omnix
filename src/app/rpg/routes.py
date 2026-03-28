"""
Flask Blueprint for the AI Role-Playing System API routes.

Provides REST endpoints for game management, turn execution, and state queries.
"""

import logging

from flask import Blueprint, jsonify, request

from app.rpg.models import GameSession
from app.rpg.persistence import delete_game, list_games, load_game, save_game
from app.rpg.pipeline import create_new_game, execute_turn

logger = logging.getLogger(__name__)

rpg_bp = Blueprint("rpg", __name__)


# ---------------------------------------------------------------------------
# Game Management
# ---------------------------------------------------------------------------

@rpg_bp.route("/api/rpg/games", methods=["GET"])
def list_rpg_games():
    """List all saved RPG game sessions."""
    games = list_games()
    return jsonify({"success": True, "games": games})


@rpg_bp.route("/api/rpg/games", methods=["POST"])
def create_rpg_game():
    """Create a new RPG game session."""
    data = request.get_json() or {}
    seed = data.get("seed")
    genre = data.get("genre", "medieval fantasy")
    player_name = data.get("player_name", "Player")

    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Seed must be an integer"}), 400

    session = create_new_game(seed=seed, genre=genre, player_name=player_name)
    if not session:
        return jsonify({"success": False, "error": "Failed to generate game world"}), 500

    # Build opening narration
    opening = session.world.description
    if session.world.lore:
        opening += "\n\n" + session.world.lore

    return jsonify({
        "success": True,
        "session_id": session.session_id,
        "world": {
            "name": session.world.name,
            "genre": session.world.genre,
            "description": session.world.description,
        },
        "player": session.player.to_dict(),
        "opening": opening,
    }), 201


@rpg_bp.route("/api/rpg/games/<session_id>", methods=["GET"])
def get_rpg_game(session_id):
    """Get the full state of an RPG game session."""
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    return jsonify({
        "success": True,
        "game": session.to_dict(),
    })


@rpg_bp.route("/api/rpg/games/<session_id>", methods=["DELETE"])
def delete_rpg_game(session_id):
    """Delete an RPG game session."""
    if delete_game(session_id):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Game not found"}), 404


# ---------------------------------------------------------------------------
# Turn Execution
# ---------------------------------------------------------------------------

@rpg_bp.route("/api/rpg/games/<session_id>/turn", methods=["POST"])
def execute_rpg_turn(session_id):
    """Execute a player turn in an RPG game."""
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    data = request.get_json() or {}
    player_input = data.get("input", "").strip()
    if not player_input:
        return jsonify({"success": False, "error": "No input provided"}), 400

    result = execute_turn(session, player_input)

    response = {
        "success": result.error is None,
        "narration": result.narration,
        "turn": session.turn_count,
        "state_changes": result.state_changes,
        "events": [e.to_dict() for e in result.events],
    }
    if result.choices:
        response["choices"] = result.choices
    if result.error:
        response["error"] = result.error

    return jsonify(response)


# ---------------------------------------------------------------------------
# State Queries
# ---------------------------------------------------------------------------

@rpg_bp.route("/api/rpg/games/<session_id>/player", methods=["GET"])
def get_player_state(session_id):
    """Get the current player state."""
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    return jsonify({
        "success": True,
        "player": session.player.to_dict(),
    })


@rpg_bp.route("/api/rpg/games/<session_id>/world", methods=["GET"])
def get_world_state(session_id):
    """Get the current world state."""
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    return jsonify({
        "success": True,
        "world": session.world.to_dict(),
    })


@rpg_bp.route("/api/rpg/games/<session_id>/npcs", methods=["GET"])
def get_npcs(session_id):
    """Get all NPCs, optionally filtered by location."""
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    location = request.args.get("location")
    if location:
        npcs = session.get_npcs_at_location(location)
    else:
        npcs = session.npcs

    return jsonify({
        "success": True,
        "npcs": [npc.to_dict() for npc in npcs],
    })


@rpg_bp.route("/api/rpg/games/<session_id>/quests", methods=["GET"])
def get_quests(session_id):
    """Get quests, optionally filtered by status."""
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    status = request.args.get("status")
    if status == "active":
        quests = session.get_active_quests()
    else:
        quests = session.quests

    return jsonify({
        "success": True,
        "quests": [q.to_dict() for q in quests],
    })


@rpg_bp.route("/api/rpg/games/<session_id>/history", methods=["GET"])
def get_history(session_id):
    """Get the game history log."""
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    limit = request.args.get("limit", type=int)
    history = session.history
    if limit and limit > 0:
        history = history[-limit:]

    return jsonify({
        "success": True,
        "history": [h.to_dict() for h in history],
        "turn_count": session.turn_count,
    })
