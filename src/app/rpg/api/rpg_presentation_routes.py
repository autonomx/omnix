"""Phase 10 — Presentation API routes.

Provides read-only builders for presentation payloads:
- Scene presentation
- Dialogue presentation
- Speaker cards
"""
from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, jsonify, request

from app.rpg.player import ensure_player_state, ensure_player_party
from app.rpg.presentation import (
    build_scene_presentation_payload,
    build_dialogue_presentation_payload,
    build_runtime_presentation_payload,
    build_orchestration_presentation_payload,
)
from app.rpg.presentation.speaker_cards import build_speaker_cards


rpg_presentation_bp = Blueprint("rpg_presentation_bp", __name__)


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _get_simulation_state(setup_payload: Dict[str, Any]) -> Dict[str, Any]:
    setup_payload = _safe_dict(setup_payload)
    return _safe_dict(setup_payload.get("simulation_state"))


@rpg_presentation_bp.post("/api/rpg/presentation/scene")
def presentation_scene():
    """Build a presentation-ready scene payload."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    scene_state = _safe_dict(data.get("scene_state"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)

    payload = build_scene_presentation_payload(simulation_state, scene_state)
    runtime_payload = build_runtime_presentation_payload(simulation_state)
    orchestration_payload = build_orchestration_presentation_payload(simulation_state)
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["runtime"] = runtime_payload
        payload["orchestration"] = orchestration_payload
    else:
        payload = {
            "content": payload,
            "runtime": runtime_payload,
            "orchestration": orchestration_payload,
        }

    return jsonify({
        "ok": True,
        "presentation": payload,
    })


@rpg_presentation_bp.post("/api/rpg/presentation/dialogue")
def presentation_dialogue():
    """Build a presentation-ready dialogue payload."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    dialogue_state = _safe_dict(data.get("dialogue_state"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)

    payload = build_dialogue_presentation_payload(simulation_state, dialogue_state)
    runtime_payload = build_runtime_presentation_payload(simulation_state)
    orchestration_payload = build_orchestration_presentation_payload(simulation_state)
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["runtime"] = runtime_payload
        payload["orchestration"] = orchestration_payload
    else:
        payload = {
            "content": payload,
            "runtime": runtime_payload,
            "orchestration": orchestration_payload,
        }

    return jsonify({
        "ok": True,
        "presentation": payload,
    })


@rpg_presentation_bp.post("/api/rpg/presentation/speakers")
def presentation_speakers():
    """Return speaker card data for a scene."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    scene_state = _safe_dict(data.get("scene_state"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)

    cards = build_speaker_cards(simulation_state, scene_state)
    runtime_payload = build_runtime_presentation_payload(simulation_state)
    orchestration_payload = build_orchestration_presentation_payload(simulation_state)

    return jsonify({
        "ok": True,
        "speaker_cards": cards,
        "runtime": runtime_payload,
        "orchestration": orchestration_payload,
    })
