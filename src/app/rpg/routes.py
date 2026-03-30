"""
Flask Blueprint for the AI Role-Playing System API routes.

Provides REST endpoints for game management, turn execution, and state queries.
"""

import json
import logging

from flask import Blueprint, Response, jsonify, request

from app.rpg.models import GameSession
from app.rpg.persistence import delete_game, list_games, load_game, save_game
from app.rpg.pipeline import create_new_game, execute_turn, replay_turn

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
    character_class = data.get("character_class", "")

    # Custom world-building inputs
    custom_lore = data.get("lore") or data.get("custom_lore")
    custom_rules = data.get("rules") or data.get("custom_rules")
    custom_story = data.get("story") or data.get("custom_story")
    world_prompt = data.get("world_prompt")

    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Seed must be an integer"}), 400

    session = create_new_game(
        seed=seed,
        genre=genre,
        player_name=player_name,
        character_class=character_class,
        custom_lore=custom_lore,
        custom_rules=custom_rules,
        custom_story=custom_story,
        world_prompt=world_prompt,
    )
    if not session:
        return jsonify({"success": False, "error": "Failed to generate game world"}), 500

    # Build opening narration
    opening_parts = []
    if session.world.name:
        opening_parts.append(session.world.name)
    if session.world.description:
        opening_parts.append(session.world.description)
    if session.world.lore:
        opening_parts.append(session.world.lore)
    opening = "\n\n".join(opening_parts) if opening_parts else "Your adventure begins\u2026"

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
        "player": session.player.to_dict(),
    }
    if result.choices:
        response["choices"] = result.choices
    if result.error:
        response["error"] = result.error
    if result.dice_roll:
        response["dice_roll"] = result.dice_roll
    if result.fail_state:
        response["fail_state"] = result.fail_state

    return jsonify(response)


@rpg_bp.route("/api/rpg/games/<session_id>/turn/stream", methods=["POST"])
def execute_rpg_turn_stream(session_id):
    """Execute a player turn and stream the narration via Server-Sent Events.

    Events emitted:
        ``{"type": "token", "text": "..."}``   – narration chunk (word by word)
        ``{"type": "done",  ...full payload}``  – final response identical to
                                                  the non-streaming turn endpoint
        ``{"type": "error", "error": "..."}``   – on failure
    """
    session = load_game(session_id)
    if not session:
        def _not_found():
            yield f"data: {json.dumps({'type': 'error', 'error': 'Game not found'})}\n\n"
        return Response(_not_found(), mimetype="text/event-stream"), 404

    data = request.get_json() or {}
    player_input = data.get("input", "").strip()
    if not player_input:
        def _bad_input():
            yield f"data: {json.dumps({'type': 'error', 'error': 'No input provided'})}\n\n"
        return Response(_bad_input(), mimetype="text/event-stream"), 400

    # Execute the full turn (blocking) then stream narration token-by-token so
    # the client can start rendering text without waiting for the full JSON.
    result = execute_turn(session, player_input)

    def generate():
        if result.error:
            yield f"data: {json.dumps({'type': 'error', 'error': result.error})}\n\n"
            return

        # Stream narration word by word (split on any whitespace for robustness)
        words = result.narration.split()
        for i, word in enumerate(words):
            chunk = word + (' ' if i < len(words) - 1 else '')
            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"

        # Final event: full structured payload (mirrors regular turn endpoint)
        final: dict = {
            "type": "done",
            "success": True,
            "narration": result.narration,
            "turn": session.turn_count,
            "state_changes": result.state_changes,
            "events": [e.to_dict() for e in result.events],
            "player": session.player.to_dict(),
        }
        if result.choices:
            final["choices"] = result.choices
        if result.dice_roll:
            final["dice_roll"] = result.dice_roll
        if result.fail_state:
            final["fail_state"] = result.fail_state

        yield f"data: {json.dumps(final)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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


@rpg_bp.route("/api/rpg/games/<session_id>/replay", methods=["GET"])
def get_replay(session_id):
    """Get the deterministic replay log for a game session.

    Query parameters:
        turn (int, optional): Return only the log for a specific turn number.
    """
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    turn = request.args.get("turn", type=int)
    if turn is not None:
        logs = [tl for tl in session.turn_logs if tl.turn == turn]
        if not logs:
            return jsonify({"success": False, "error": f"No log for turn {turn}"}), 404
        return jsonify({
            "success": True,
            "turn_log": logs[0].to_dict(),
        })

    return jsonify({
        "success": True,
        "turn_logs": [tl.to_dict() for tl in session.turn_logs],
        "turn_count": session.turn_count,
    })


@rpg_bp.route("/api/rpg/games/<session_id>/replay", methods=["POST"])
def run_replay(session_id):
    """Re-execute a turn deterministically from its stored TurnLog.

    Request body:
        turn (int, required): The turn number to replay.
    """
    session = load_game(session_id)
    if not session:
        return jsonify({"success": False, "error": "Game not found"}), 404

    data = request.get_json() or {}
    turn = data.get("turn")
    if turn is None:
        return jsonify({"success": False, "error": "Missing 'turn' in request body"}), 400

    try:
        turn = int(turn)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "'turn' must be an integer"}), 400

    logs = [tl for tl in session.turn_logs if tl.turn == turn]
    if not logs:
        return jsonify({"success": False, "error": f"No log for turn {turn}"}), 404

    result = replay_turn(logs[0], session)
    save_game(session)

    response = {
        "success": result.error is None,
        "narration": result.narration,
        "turn": turn,
        "state_changes": result.state_changes,
        "events": [e.to_dict() for e in result.events],
    }
    if result.dice_roll:
        response["dice_roll"] = result.dice_roll
    if result.error:
        response["error"] = result.error

    return jsonify(response)
