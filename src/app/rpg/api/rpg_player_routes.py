"""Phase 8 — Player-facing API routes.

Exposes the lightweight player state layer via stable JSON endpoints
for UI integration.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.rpg.player import (
    ensure_player_state,
    enter_dialogue_mode,
    exit_dialogue_mode,
)
from app.rpg.player.player_encounter import build_encounter_view


rpg_player_bp = Blueprint("rpg_player_bp", __name__)


def _load_setup_payload() -> dict:
    data = request.get_json(silent=True) or {}
    return dict(data.get("setup_payload") or {})


def _get_simulation_state(setup_payload: dict) -> dict:
    meta = dict((setup_payload or {}).get("metadata") or {})
    return dict(meta.get("simulation_state") or {})


def _write_simulation_state(setup_payload: dict, simulation_state: dict) -> dict:
    setup_payload = dict(setup_payload or {})
    meta = dict(setup_payload.get("metadata") or {})
    meta["simulation_state"] = dict(simulation_state or {})
    setup_payload["metadata"] = meta
    return setup_payload


@rpg_player_bp.post("/api/rpg/player/state")
def player_state():
    """Return the current player-facing state."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "player_state": state.get("player_state", {}),
    })


@rpg_player_bp.post("/api/rpg/player/journal")
def player_journal():
    """Return the player journal entries (last 50)."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "journal_entries": list((state.get("player_state") or {}).get("journal_entries") or [])[-50:],
    })


@rpg_player_bp.post("/api/rpg/player/codex")
def player_codex():
    """Return the player codex."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "codex": dict((state.get("player_state") or {}).get("codex") or {}),
    })


@rpg_player_bp.post("/api/rpg/player/objectives")
def player_objectives():
    """Return the player active objectives (last 20)."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "active_objectives": list((state.get("player_state") or {}).get("active_objectives") or [])[-20:],
    })


@rpg_player_bp.post("/api/rpg/player/dialogue/enter")
def player_dialogue_enter():
    """Enter dialogue mode with the specified NPC."""
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    scene_id = str(data.get("scene_id") or "")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = enter_dialogue_mode(state, npc_id=npc_id, scene_id=scene_id)
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "player_state": state.get("player_state", {}),
    })


@rpg_player_bp.post("/api/rpg/player/dialogue/exit")
def player_dialogue_exit():
    """Exit dialogue mode and return to the fallback mode."""
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    fallback_mode = str(data.get("fallback_mode") or "scene")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = exit_dialogue_mode(state, fallback_mode=fallback_mode)
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "player_state": state.get("player_state", {}),
    })


@rpg_player_bp.post("/api/rpg/player/encounter")
def player_encounter():
    """Build and return an encounter view for a given scene."""
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    scene = dict(data.get("scene") or {})
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "encounter": build_encounter_view(scene, state),
    })