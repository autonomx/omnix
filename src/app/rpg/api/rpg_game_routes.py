"""Phase 1 — RPG Game Management API routes (FastAPI).

Provides REST endpoints for game management, turn execution, and state queries.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.rpg.models import GameSession
from app.rpg.pipeline import (
    build_game_context,
    create_new_game,
    delete_game,
    execute_turn,
    finalize_game,
    list_games,
    load_game,
    replay_turn,
    save_game,
    stage_environment,
    stage_factions,
    stage_npcs,
    stage_story,
    stage_world,
)

logger = logging.getLogger(__name__)

rpg_game_bp = APIRouter()


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _jsonify(data: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    """FastAPI-compatible JSON response."""
    return JSONResponse(content=data, status_code=status_code)


async def _get_json(request: Request) -> Dict[str, Any]:
    """Get JSON body from request, returning empty dict on failure."""
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event data line."""
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Game Management
# ---------------------------------------------------------------------------

@rpg_game_bp.get("/api/rpg/games")
async def list_rpg_games():
    """List all saved RPG game sessions."""
    try:
        games = list_games()
        return _jsonify({"success": True, "games": games})
    except Exception as e:
        logger.error(f"Error listing games: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.post("/api/rpg/games")
async def create_rpg_game(request: Request):
    """Create a new RPG game session.

    Deprecated: new adventures should use ``/api/rpg/adventure/start`` backed by
    the structured ``AdventureSetup`` creator flow.
    """
    try:
        data = await _get_json(request)
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
                return _jsonify({"success": False, "error": "Seed must be an integer"}, status_code=400)

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
            return _jsonify({"success": False, "error": "Failed to generate game world"}, status_code=500)

        # Build opening narration
        opening_parts = []
        if session.world.name:
            opening_parts.append(session.world.name)
        if session.world.description:
            opening_parts.append(session.world.description)
        if session.world.lore:
            opening_parts.append(session.world.lore)
        opening = "\n\n".join(opening_parts) if opening_parts else "Your adventure begins\u2026"

        response = {
            "success": True,
            "session_id": session.session_id,
            "world": {
                "name": session.world.name,
                "genre": session.world.genre,
                "description": session.world.description,
            },
            "player": session.player.to_dict(),
            "opening": opening,
        }
        return _jsonify(response, status_code=201)
    except Exception as e:
        logger.error(f"Error creating game: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.post("/api/rpg/games/stream")
async def stream_game_creation(request: Request):
    """Create a new RPG game session with streamed progress via SSE.

    Events emitted during creation:
        ``{"stage": "...", "progress": N}`` — progress update (1-5)
        ``{"stage": "Done", "progress": 6, "result": {...}}`` — final result
        ``{"error": "..."}`` — on failure
    """
    try:
        data = await _get_json(request)

        async def generate():
            ctx = build_game_context(data)

            yield _sse({"stage": "Building world", "progress": 1})
            stage_world(ctx)

            if not ctx.get("world_data"):
                yield _sse({"error": "World generation failed"})
                return

            yield _sse({"stage": "Generating environment", "progress": 2})
            stage_environment(ctx)

            yield _sse({"stage": "Creating factions", "progress": 3})
            stage_factions(ctx)

            yield _sse({"stage": "Spawning NPCs", "progress": 4})
            stage_npcs(ctx)

            yield _sse({"stage": "Creating story", "progress": 5})
            stage_story(ctx)

            session = finalize_game(ctx)
            if not session:
                yield _sse({"error": "Failed to finalize game"})
                return

            # Build opening narration
            opening_parts = []
            if session.world.name:
                opening_parts.append(session.world.name)
            if session.world.description:
                opening_parts.append(session.world.description)
            if session.world.lore:
                opening_parts.append(session.world.lore)
            opening = "\n\n".join(opening_parts) if opening_parts else "Your adventure begins\u2026"

            yield _sse({
                "stage": "Done",
                "progress": 6,
                "result": {
                    "session_id": session.session_id,
                    "world": {
                        "name": session.world.name,
                        "genre": session.world.genre,
                        "description": session.world.description,
                    },
                    "player": session.player.to_dict(),
                    "opening": opening,
                },
            })

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error(f"Error streaming game creation: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.get("/api/rpg/games/{session_id}")
async def get_rpg_game(session_id: str):
    """Get the full state of an RPG game session."""
    try:
        session = load_game(session_id)
        if not session:
            return _jsonify({"success": False, "error": "Game not found"}, status_code=404)

        return _jsonify({
            "success": True,
            "game": session.to_dict(),
        })
    except Exception as e:
        logger.error(f"Error getting game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.delete("/api/rpg/games/{session_id}")
async def delete_rpg_game(session_id: str):
    """Delete an RPG game session."""
    try:
        if delete_game(session_id):
            return _jsonify({"success": True})
        return _jsonify({"success": False, "error": "Game not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error deleting game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Turn Execution
# ---------------------------------------------------------------------------

@rpg_game_bp.post("/api/rpg/games/{session_id}/turn")
async def execute_rpg_turn(session_id: str, request: Request):
    """Execute a player turn in an RPG game."""
    try:
        session = load_game(session_id)
        if not session:
            return _jsonify({"success": False, "error": "Game not found"}, status_code=404)

        data = await _get_json(request)
        player_input = data.get("input", "").strip()
        if not player_input:
            return _jsonify({"success": False, "error": "No input provided"}, status_code=400)

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

        return _jsonify(response)
    except Exception as e:
        logger.error(f"Error executing turn for game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.post("/api/rpg/games/{session_id}/turn/stream")
async def execute_rpg_turn_stream(session_id: str, request: Request):
    """Execute a player turn and stream the narration via Server-Sent Events.

    Events emitted:
        ``{"type": "token", "text": "..."}``   – narration chunk (word by word)
        ``{"type": "done",  ...full payload}``  – final response identical to
                                                  the non-streaming turn endpoint
        ``{"type": "error", "error": "..."}``   – on failure
    """
    try:
        session = load_game(session_id)
        if not session:
            async def _not_found():
                yield f"data: {json.dumps({'type': 'error', 'error': 'Game not found'})}\n\n"
            return StreamingResponse(_not_found(), media_type="text/event-stream", status_code=404)

        data = await _get_json(request)
        player_input = data.get("input", "").strip()
        if not player_input:
            async def _bad_input():
                yield f"data: {json.dumps({'type': 'error', 'error': 'No input provided'})}\n\n"
            return StreamingResponse(_bad_input(), media_type="text/event-stream", status_code=400)

        # Execute the full turn (blocking) then stream narration token-by-token
        result = execute_turn(session, player_input)

        async def generate():
            if result.error:
                yield f"data: {json.dumps({'type': 'error', 'error': result.error})}\n\n"
                return

            # Stream narration word by word
            words = result.narration.split()
            for i, word in enumerate(words):
                chunk = word + (' ' if i < len(words) - 1 else '')
                yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"

            # Final event: full structured payload
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

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error(f"Error streaming turn for game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# State Queries
# ---------------------------------------------------------------------------

@rpg_game_bp.get("/api/rpg/games/{session_id}/player")
async def get_player_state(session_id: str):
    """Get the current player state."""
    try:
        session = load_game(session_id)
        if not session:
            return _jsonify({"success": False, "error": "Game not found"}, status_code=404)

        return _jsonify({
            "success": True,
            "player": session.player.to_dict(),
        })
    except Exception as e:
        logger.error(f"Error getting player state for game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.get("/api/rpg/games/{session_id}/world")
async def get_world_state(session_id: str):
    """Get the current world state."""
    try:
        session = load_game(session_id)
        if not session:
            return _jsonify({"success": False, "error": "Game not found"}, status_code=404)

        return _jsonify({
            "success": True,
            "world": session.world.to_dict(),
        })
    except Exception as e:
        logger.error(f"Error getting world state for game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.get("/api/rpg/games/{session_id}/npcs")
async def get_npcs(session_id: str, location: Optional[str] = None):
    """Get all NPCs, optionally filtered by location."""
    try:
        session = load_game(session_id)
        if not session:
            return _jsonify({"success": False, "error": "Game not found"}, status_code=404)

        if location:
            npcs = session.get_npcs_at_location(location)
        else:
            npcs = session.npcs

        return _jsonify({
            "success": True,
            "npcs": [npc.to_dict() for npc in npcs],
        })
    except Exception as e:
        logger.error(f"Error getting NPCs for game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.get("/api/rpg/games/{session_id}/quests")
async def get_quests(session_id: str, status: Optional[str] = None):
    """Get quests, optionally filtered by status."""
    try:
        session = load_game(session_id)
        if not session:
            return _jsonify({"success": False, "error": "Game not found"}, status_code=404)

        if status == "active":
            quests = session.get_active_quests()
        else:
            quests = session.quests

        return _jsonify({
            "success": True,
            "quests": [q.to_dict() for q in quests],
        })
    except Exception as e:
        logger.error(f"Error getting quests for game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.get("/api/rpg/games/{session_id}/history")
async def get_history(session_id: str, limit: Optional[int] = None):
    """Get the game history log."""
    try:
        session = load_game(session_id)
        if not session:
            return _jsonify({"success": False, "error": "Game not found"}, status_code=404)

        history = session.history
        if limit and limit > 0:
            history = history[-limit:]

        return _jsonify({
            "success": True,
            "history": [h.to_dict() for h in history],
            "turn_count": session.turn_count,
        })
    except Exception as e:
        logger.error(f"Error getting history for game {session_id}: {e}", exc_info=True)
        return _jsonify({"success": False, "error": str(e)}, status_code=500)


@rpg_game_bp.get("/api/rpg/games/{session_id}/replay")
async def get_replay(session_id: str, turn: Optional[int] = None):
    return _jsonify(
        {
            "success": False,
            "error": "replay_disabled",
            "message": (
                "This RPG build is save/load-stable rather than replay-deterministic. "
                "Use manual saves to branch from important choices."
            ),
        },
        status_code=410,
    )


@rpg_game_bp.post("/api/rpg/games/{session_id}/replay")
async def run_replay(session_id: str, request: Request):
    return _jsonify(
        {
            "success": False,
            "error": "replay_disabled",
            "message": (
                "Replay is disabled in save/load-stable mode. "
                "Load a save to explore alternate story branches."
            ),
        },
        status_code=410,
    )