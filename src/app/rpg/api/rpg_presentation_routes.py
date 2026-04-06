"""Phase 10 — Presentation API routes.

Provides read-only builders for presentation payloads:
- Scene presentation
- Dialogue presentation
- Speaker cards
- Setup flow (product layer A1)
- Intro scene (product layer A2)
- Save/load UX (product layer A5)
- Narrative recap (product layer A6)
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
    build_live_provider_presentation_payload,
    build_setup_flow_payload,
    build_intro_scene_payload,
    build_dialogue_ux_payload,
    build_player_inspector_overlay_payload,
    build_save_load_ux_payload,
    build_narrative_recap_payload,
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
    live_provider_payload = build_live_provider_presentation_payload(simulation_state)
    inspector_overlay_payload = build_player_inspector_overlay_payload(
        simulation_state,
        runtime_payload,
        orchestration_payload,
        live_provider_payload,
    )
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["runtime"] = runtime_payload
        payload["orchestration"] = orchestration_payload
        payload["live_provider"] = live_provider_payload
        payload["player_overlay"] = inspector_overlay_payload.get("player_overlay", {})
    else:
        payload = {
            "content": payload,
            "runtime": runtime_payload,
            "orchestration": orchestration_payload,
            "live_provider": live_provider_payload,
            "player_overlay": inspector_overlay_payload.get("player_overlay", {}),
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
    live_provider_payload = build_live_provider_presentation_payload(simulation_state)
    dialogue_ux_payload = build_dialogue_ux_payload(
        payload,
        runtime_payload,
        orchestration_payload,
    )
    inspector_overlay_payload = build_player_inspector_overlay_payload(
        simulation_state,
        runtime_payload,
        orchestration_payload,
        live_provider_payload,
    )
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["runtime"] = runtime_payload
        payload["orchestration"] = orchestration_payload
        payload["live_provider"] = live_provider_payload
        payload["dialogue_ux"] = dialogue_ux_payload.get("dialogue_ux", {})
        payload["player_overlay"] = inspector_overlay_payload.get("player_overlay", {})
    else:
        payload = {
            "content": payload,
            "runtime": runtime_payload,
            "orchestration": orchestration_payload,
            "live_provider": live_provider_payload,
            "dialogue_ux": dialogue_ux_payload.get("dialogue_ux", {}),
            "player_overlay": inspector_overlay_payload.get("player_overlay", {}),
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
    live_provider_payload = build_live_provider_presentation_payload(simulation_state)
    inspector_overlay_payload = build_player_inspector_overlay_payload(
        simulation_state,
        runtime_payload,
        orchestration_payload,
        live_provider_payload,
    )

    return jsonify({
        "ok": True,
        "speaker_cards": cards,
        "runtime": runtime_payload,
        "orchestration": orchestration_payload,
        "live_provider": live_provider_payload,
        "player_overlay": inspector_overlay_payload.get("player_overlay", {}),
    })


@rpg_presentation_bp.post("/setup-flow")
def presentation_setup_flow():
    """Build deterministic setup-flow payload for player-facing world creation."""
    body = request.get_json(silent=True) or {}
    user_input = body.get("user_input") or {}
    payload = build_setup_flow_payload(user_input)
    return jsonify({
        "ok": True,
        "presentation": payload,
    })


@rpg_presentation_bp.post("/session-bootstrap")
def presentation_session_bootstrap():
    """Build session bootstrap payload from setup flow."""
    body = request.get_json(silent=True) or {}
    user_input = body.get("user_input") or {}
    setup_payload = build_setup_flow_payload(user_input)
    setup_flow = setup_payload.get("setup_flow") or {}

    response_payload = {
        "session_bootstrap": {
            "world_seed": dict(setup_flow.get("world_seed") or {}),
            "rules": dict(setup_flow.get("rules") or {}),
            "player_role": (setup_flow.get("selected") or {}).get("player_role", "wanderer"),
            "tone_tags": list(setup_flow.get("tone_tags") or []),
            "seed_prompt": (setup_flow.get("selected") or {}).get("seed_prompt", ""),
        }
    }
    return jsonify({
        "ok": True,
        "presentation": response_payload,
    })


@rpg_presentation_bp.post("/intro-scene")
def presentation_intro_scene():
    """Build deterministic intro scene payload for first 60 seconds experience."""
    body = request.get_json(silent=True) or {}
    session_bootstrap = body.get("session_bootstrap") or {}
    payload = build_intro_scene_payload(session_bootstrap)
    return jsonify({
        "ok": True,
        "presentation": payload,
    })


@rpg_presentation_bp.post("/save-load-ux")
def presentation_save_load_ux():
    """Build save/load UX payload with sorted slots and rewind preview."""
    body = request.get_json(silent=True) or {}
    save_snapshots = body.get("save_snapshots") or []
    current_tick = body.get("current_tick") or 0
    payload = build_save_load_ux_payload(
        save_snapshots=save_snapshots,
        current_tick=current_tick,
    )
    return jsonify({
        "ok": True,
        "presentation": payload,
    })


@rpg_presentation_bp.post("/narrative-recap")
def presentation_narrative_recap():
    """Build narrative recap payload with recent dialogue and codex surfacing."""
    body = request.get_json(silent=True) or {}
    setup_payload = body.get("setup_payload") or {}
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    runtime_payload = build_runtime_presentation_payload(simulation_state)
    payload = build_narrative_recap_payload(simulation_state, runtime_payload)
    return jsonify({
        "ok": True,
        "presentation": payload,
    })