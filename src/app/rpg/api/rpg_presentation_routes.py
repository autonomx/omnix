"""Phase 10 — Presentation API routes.

Provides read-only builders for presentation payloads:
- Scene presentation
- Dialogue presentation
- Speaker cards
- Character UI state (canonical)
- Setup flow (product layer A1)
- Intro scene (product layer A2)
- Save/load UX (product layer A5)
- Narrative recap (product layer A6)
"""
from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, jsonify, request

from app.rpg.player import ensure_player_party, ensure_player_state
from app.rpg.presentation import (
    build_dialogue_presentation_payload,
    build_dialogue_ux_payload,
    build_intro_scene_payload,
    build_live_provider_presentation_payload,
    build_narrative_recap_payload,
    build_orchestration_presentation_payload,
    build_player_inspector_overlay_payload,
    build_runtime_presentation_payload,
    build_save_load_ux_payload,
    build_scene_presentation_payload,
    build_setup_flow_payload,
)
from app.rpg.presentation.personality_state import ensure_personality_state
from app.rpg.presentation.speaker_cards import build_speaker_cards
from app.rpg.ui.character_builder import build_character_inspector_state, build_character_ui_state
from app.rpg.ui.world_builder import build_world_inspector_state
from app.rpg.memory.actor_memory_state import ensure_actor_memory_state
from app.rpg.memory.world_memory_state import ensure_world_memory_state
from app.rpg.presentation.visual_state import (
    append_appearance_event,
    append_image_request,
    append_scene_illustration,
    append_visual_asset,
    apply_visual_fallback,
    build_default_appearance_profile,
    build_default_character_visual_identity,
    build_visual_asset_record,
    ensure_visual_state,
    normalize_visual_status,
    stable_visual_seed_from_text,
    upsert_appearance_profile,
    upsert_character_visual_identity,
    validate_visual_prompt,
)
from app.rpg.compat.character_cards import (
    export_canonical_character_card,
    import_external_character_card,
)
from app.rpg.packaging.package_io import (
    export_session_package,
    import_session_package,
)
from app.rpg.modding.content_packs import (
    apply_content_pack,
    build_pack_application_preview,
    build_pack_bootstrap_payload,
    ensure_content_pack_state,
    list_content_packs,
)
from app.rpg.creator.pack_authoring import (
    build_pack_draft_export,
    build_pack_draft_preview,
    validate_pack_draft,
)
from datetime import datetime

from app.rpg.templates.campaign_templates import (
    build_campaign_template,
    build_template_start_payload,
    list_campaign_templates,
)

# Phase 12.10 — Visual worker executor
from app.rpg.visual.worker import process_pending_image_requests

# Phase 12.12 — ComfyUI provider
from app.rpg.visual.providers import get_image_provider

# Phase 12.13.5 — Visual queue management with hardening
from app.rpg.visual.job_queue import (
    enqueue_visual_job,
    list_visual_jobs,
    normalize_visual_queue,
    prune_completed_visual_jobs,
)
from app.rpg.visual.queue_runner import run_one_queued_job

# Phase 12.14 — Asset dedupe and cleanup
from app.rpg.visual.asset_store import cleanup_unused_assets, get_asset_manifest

# Phase 13.4 — New Adventure Wizard UI
from app.rpg.setup.wizard_state import (
    build_wizard_preview_payload,
    build_wizard_setup_payload,
    normalize_wizard_state,
)

# Phase 13.5 — Session lifecycle + persistence
from app.rpg.session.session_store import (
    archive_session,
    ensure_session_registry,
    get_session,
    list_sessions,
    save_session,
)

# Phase 14.0 — Memory system
from app.rpg.memory.memory_state import (
    append_long_term_memory,
    append_short_term_memory,
    append_world_memory,
    ensure_memory_state,
)

# Phase 14.3 — Memory → Dialogue Injection
from app.rpg.memory.dialogue_memory_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)

# Phase 14.4 — Memory Decay / Reinforcement
from app.rpg.memory.memory_decay import apply_memory_decay

# Phase 15.0 — Durable persistence
from app.rpg.session.durable_store import (
    list_sessions_from_disk,
    load_session_from_disk,
    save_session_to_disk,
)

# Phase 15.1 — Session ↔ Package Unification
from app.rpg.packaging.session_package_bridge import (
    package_to_session,
    session_to_package,
)

rpg_presentation_bp = Blueprint("rpg_presentation_bp", __name__)


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _safe_character_ui_state(v: Any) -> Dict[str, Any]:
    if not isinstance(v, dict):
        return {"characters": [], "count": 0}
    raw_characters = v.get("characters")
    if not isinstance(raw_characters, list):
        raw_characters = []

    characters = [item for item in raw_characters if isinstance(item, dict)]

    raw_count = v.get("count", len(characters))
    count = raw_count if isinstance(raw_count, int) else len(characters)

    return {
        "characters": characters,
        "count": count,
    }


def _get_simulation_state(setup_payload: Dict[str, Any]) -> Dict[str, Any]:
    setup_payload = _safe_dict(setup_payload)
    return _safe_dict(setup_payload.get("simulation_state"))


def _ensure_character_ui_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Attach fresh canonical character_ui_state at presentation boundary."""
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state")
    if not isinstance(presentation_state, dict):
        presentation_state = {}
        simulation_state["presentation_state"] = presentation_state

    presentation_state["character_ui_state"] = build_character_ui_state(simulation_state)
    return simulation_state


def _extract_character_ui_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract character_ui_state from simulation state."""
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state") or {}
    if not isinstance(presentation_state, dict):
        presentation_state = {}
    character_ui_state = presentation_state.get("character_ui_state") or {"characters": [], "count": 0}
    return _safe_character_ui_state(character_ui_state)


def _safe_character_inspector_state(v: Any) -> Dict[str, Any]:
    if not isinstance(v, dict):
        return {"characters": [], "count": 0}
    raw_characters = v.get("characters")
    if not isinstance(raw_characters, list):
        raw_characters = []

    characters = [item for item in raw_characters if isinstance(item, dict)]

    raw_count = v.get("count", len(characters))
    count = raw_count if isinstance(raw_count, int) else len(characters)

    return {
        "characters": characters,
        "count": count,
    }


def _ensure_character_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Attach fresh canonical character_inspector_state at presentation boundary."""
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state")
    if not isinstance(presentation_state, dict):
        presentation_state = {}
        simulation_state["presentation_state"] = presentation_state

    presentation_state["character_inspector_state"] = build_character_inspector_state(simulation_state)
    return simulation_state


def _extract_character_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract character_inspector_state from simulation state."""
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state") or {}
    if not isinstance(presentation_state, dict):
        presentation_state = {}
    inspector_state = presentation_state.get("character_inspector_state") or {"characters": [], "count": 0}
    return _safe_character_inspector_state(inspector_state)


def _safe_world_inspector_state(v: Any) -> Dict[str, Any]:
    if not isinstance(v, dict):
        return {
            "summary": {},
            "threads": [],
            "thread_count": 0,
            "factions": {"factions": [], "count": 0},
            "locations": {"locations": [], "count": 0},
        }

    summary = v.get("summary")
    if not isinstance(summary, dict):
        summary = {}

    raw_threads = v.get("threads")
    if not isinstance(raw_threads, list):
        raw_threads = []
    threads = [item for item in raw_threads if isinstance(item, dict)]

    thread_count = v.get("thread_count", len(threads))
    if not isinstance(thread_count, int):
        thread_count = len(threads)

    factions = v.get("factions")
    if not isinstance(factions, dict):
        factions = {"factions": [], "count": 0}

    locations = v.get("locations")
    if not isinstance(locations, dict):
        locations = {"locations": [], "count": 0}

    return {
        "summary": summary,
        "threads": threads,
        "thread_count": thread_count,
        "factions": factions,
        "locations": locations,
    }


def _ensure_actor_memory_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure actor memory state is initialized."""
    simulation_state = _safe_dict(simulation_state)
    return ensure_actor_memory_state(simulation_state)


def _ensure_world_memory_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure world memory state is initialized."""
    simulation_state = _safe_dict(simulation_state)
    return ensure_world_memory_state(simulation_state)


def _ensure_world_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    simulation_state = _ensure_world_memory_state(simulation_state)
    presentation_state = simulation_state.get("presentation_state")
    if not isinstance(presentation_state, dict):
        presentation_state = {}
        simulation_state["presentation_state"] = presentation_state

    presentation_state["world_inspector_state"] = build_world_inspector_state(simulation_state)
    return simulation_state


def _extract_world_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state") or {}
    if not isinstance(presentation_state, dict):
        presentation_state = {}
    world_inspector_state = presentation_state.get("world_inspector_state") or {}
    return _safe_world_inspector_state(world_inspector_state)


def _safe_visual_state(v: Any) -> Dict[str, Any]:
    if not isinstance(v, dict):
        return {
            "character_visual_identities": {},
            "scene_illustrations": [],
            "image_requests": [],
            "visual_assets": [],
            "appearance_profiles": {},
            "appearance_events": {},
            "defaults": {},
        }

    identities = v.get("character_visual_identities")
    if not isinstance(identities, dict):
        identities = {}

    illustrations = v.get("scene_illustrations")
    if not isinstance(illustrations, list):
        illustrations = []
    illustrations = [item for item in illustrations if isinstance(item, dict)]

    requests = v.get("image_requests")
    if not isinstance(requests, list):
        requests = []
    requests = [item for item in requests if isinstance(item, dict)]

    assets = v.get("visual_assets")
    if not isinstance(assets, list):
        assets = []
    assets = [item for item in assets if isinstance(item, dict)]

    appearance_profiles = v.get("appearance_profiles")
    if not isinstance(appearance_profiles, dict):
        appearance_profiles = {}

    appearance_events = v.get("appearance_events")
    if not isinstance(appearance_events, dict):
        appearance_events = {}

    defaults = v.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {}

    return {
        "character_visual_identities": identities,
        "scene_illustrations": illustrations,
        "image_requests": requests,
        "visual_assets": assets,
        "appearance_profiles": appearance_profiles,
        "appearance_events": appearance_events,
        "defaults": defaults,
    }


def _extract_visual_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = ensure_visual_state(_safe_dict(simulation_state))
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    return _safe_visual_state(visual_state)


@rpg_presentation_bp.post("/api/rpg/presentation/scene")
def presentation_scene():
    """Build a presentation-ready scene payload."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    scene_state = _safe_dict(data.get("scene_state"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_actor_memory_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)

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

    response = {
        "ok": True,
        "presentation": payload,
        "character_ui_state": _extract_character_ui_state(simulation_state),
        "character_inspector_state": _extract_character_inspector_state(simulation_state),
        "world_inspector_state": _extract_world_inspector_state(simulation_state),
        "visual_state": _extract_visual_state(simulation_state),
        "memory_state": _safe_dict(simulation_state.get("memory_state")),
    }
    return jsonify(_add_content_pack_data(response, simulation_state))


@rpg_presentation_bp.post("/api/rpg/presentation/dialogue")
def presentation_dialogue():
    """Build a presentation-ready dialogue payload."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    dialogue_state = _safe_dict(data.get("dialogue_state"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_actor_memory_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)

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

    # Phase 14.3 — integrate memory context into dialogue response
    # Ensure memory state is fully initialized before building memory context
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)

    actor_ids = []

    # Prefer current speaker/turn actor from payload if available
    speaker = payload.get("speaker") if isinstance(payload, dict) else None
    if isinstance(speaker, dict):
        speaker_id = _safe_str(speaker.get("actor_id")).strip()
        if speaker_id:
            actor_ids.append(speaker_id)

    # Fall back to visible characters from canonical character UI state
    character_ui_state = _extract_character_ui_state(simulation_state)
    characters = character_ui_state.get("characters") if isinstance(character_ui_state, dict) else []
    if isinstance(characters, list):
        for character in characters:
            if not isinstance(character, dict):
                continue
            actor_id = _safe_str(character.get("id")).strip()
            if actor_id and actor_id not in actor_ids:
                actor_ids.append(actor_id)
            if len(actor_ids) >= 6:
                break

    dialogue_memory_context = build_dialogue_memory_context(simulation_state, actor_ids)
    memory_prompt_block = build_llm_memory_prompt_block(dialogue_memory_context)

    response = {
        "ok": True,
        "presentation": payload,
        "character_ui_state": _extract_character_ui_state(simulation_state),
        "character_inspector_state": _extract_character_inspector_state(simulation_state),
        "world_inspector_state": _extract_world_inspector_state(simulation_state),
        "visual_state": _extract_visual_state(simulation_state),
        "memory_state": _safe_dict(simulation_state.get("memory_state")),
        "dialogue_memory_context": dialogue_memory_context,
        "llm_memory_prompt_block": memory_prompt_block,
    }
    return jsonify(_add_content_pack_data(response, simulation_state))


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
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)
    runtime_payload = build_runtime_presentation_payload(simulation_state)
    payload = build_narrative_recap_payload(simulation_state, runtime_payload)
    response = {
        "ok": True,
        "presentation": payload,
        "character_ui_state": _extract_character_ui_state(simulation_state),
        "character_inspector_state": _extract_character_inspector_state(simulation_state),
        "world_inspector_state": _extract_world_inspector_state(simulation_state),
        "visual_state": _extract_visual_state(simulation_state),
        "memory_state": _safe_dict(simulation_state.get("memory_state")),
    }
    return jsonify(_add_content_pack_data(response, simulation_state))


@rpg_presentation_bp.post("/api/rpg/character_ui")
def presentation_character_ui():
    """Return canonical character UI state for current simulation."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)

    character_ui_state = _extract_character_ui_state(simulation_state)

    return jsonify({
        "ok": True,
        "character_ui_state": character_ui_state,
    })


@rpg_presentation_bp.post("/api/rpg/character_inspector")
def presentation_character_inspector():
    """Return canonical character inspector state for current simulation."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)

    return jsonify({
        "ok": True,
        "character_inspector_state": _extract_character_inspector_state(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/character_inspector/detail")
def presentation_character_inspector_detail():
    """Return inspector detail for one character."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_id = str(data.get("actor_id") or "").strip()

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)

    inspector_state = _extract_character_inspector_state(simulation_state)
    characters = inspector_state.get("characters") if isinstance(inspector_state, dict) else []
    if not isinstance(characters, list):
        characters = []

    for character in characters:
        if isinstance(character, dict) and str(character.get("id") or "").strip() == actor_id:
            return jsonify({
                "ok": True,
                "character": character,
            })

    return jsonify({
        "ok": False,
        "error": "character_not_found",
        "character": None,
    }), 404


@rpg_presentation_bp.post("/api/rpg/world_inspector")
def presentation_world_inspector():
    """Return canonical world inspector state for current simulation."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)

    return jsonify({
        "ok": True,
        "world_inspector_state": _extract_world_inspector_state(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/character_portrait/request")
def request_character_portrait():
    """Create/update a portrait generation request for a character."""
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id") or "").strip()
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_id = _safe_str(data.get("actor_id")).strip()
    style = _safe_str(data.get("style")).strip()
    model = _safe_str(data.get("model")).strip()
    prompt_override = _safe_str(data.get("prompt")).strip()

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    character_ui_state = _extract_character_ui_state(simulation_state)
    characters = character_ui_state.get("characters") if isinstance(character_ui_state, dict) else []
    if not isinstance(characters, list):
        characters = []

    target = None
    for character in characters:
        if isinstance(character, dict) and _safe_str(character.get("id")).strip() == actor_id:
            target = character
            break

    if not target:
        return jsonify({
            "ok": False,
            "error": "character_not_found",
        }), 404

    existing_visual = _safe_dict(target.get("visual_identity"))
    portrait_style = _first_non_empty(style, existing_visual.get("style"), "rpg-portrait")
    portrait_model = _first_non_empty(model, existing_visual.get("model"), "default")

    identity = build_default_character_visual_identity(
        actor_id=actor_id,
        name=_safe_str(target.get("name")).strip(),
        role=_safe_str(target.get("role")).strip(),
        description=_safe_str(target.get("description")).strip(),
        personality_summary=_safe_str(_safe_dict(target.get("personality")).get("summary")).strip(),
        style=portrait_style,
        model=portrait_model,
    )

    identity.update(existing_visual)
    if prompt_override:
        identity["base_prompt"] = prompt_override
    identity["style"] = portrait_style
    identity["model"] = portrait_model

    prompt_check = validate_visual_prompt(identity.get("base_prompt", ""))
    identity["status"] = "pending" if prompt_check.get("ok") else "blocked"

    current_version = identity.get("version")
    identity["version"] = current_version + 1 if isinstance(current_version, int) and current_version > 0 else 1

    # Phase 12.4 — initialize appearance profile
    profile_payload = build_default_appearance_profile(
        actor_id=actor_id,
        name=_safe_str(target.get("name")).strip(),
        role=_safe_str(target.get("role")).strip(),
        description=_safe_str(target.get("description")).strip(),
    )
    simulation_state = upsert_appearance_profile(
        simulation_state,
        actor_id=actor_id,
        profile=profile_payload,
    )

    simulation_state = upsert_character_visual_identity(
        simulation_state,
        actor_id=actor_id,
        identity=identity,
    )

    # Phase 12.4 — record appearance event
    simulation_state = append_appearance_event(
        simulation_state,
        actor_id=actor_id,
        event={
            "event_id": f"appearance:{actor_id}:{identity['version']}",
            "reason": "manual_refresh" if prompt_override else "initial",
            "summary": "Portrait refresh requested",
            "tick": 0,
        },
    )

    request_id = f"portrait:{actor_id}:{identity['version']}"
    now_ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": request_id,
            "kind": "character_portrait",
            "target_id": actor_id,
            "prompt": identity.get("base_prompt", ""),
            "seed": identity.get("seed"),
            "style": identity.get("style", ""),
            "model": identity.get("model", ""),
            "status": "pending" if prompt_check.get("ok") else "blocked",
            "attempts": 0,
            "max_attempts": 3,
            "error": "",
            "created_at": now_ts,
            "updated_at": "",
            "completed_at": "",
        },
    )

    # Phase 12.13.5 — Auto-enqueue on request creation
    if session_id and request_id:
        try:
            enqueue_visual_job(session_id=session_id, request_id=request_id)
        except Exception:
            # Queueing is best-effort; request remains inspectable in simulation state.
            pass

    return jsonify({
        "ok": True,
        "request_id": request_id,
        "moderation": {
            "status": "approved" if prompt_check.get("ok") else "blocked",
            "reason": _safe_str(prompt_check.get("reason")).strip(),
        },
        "visual_state": _extract_visual_state(simulation_state),
        "character_ui_state": _extract_character_ui_state(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/character_portrait/result")
def complete_character_portrait():
    """Record completed portrait asset metadata for a character."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_id = _safe_str(data.get("actor_id")).strip()
    image_url = _safe_str(data.get("image_url")).strip()
    asset_id = _safe_str(data.get("asset_id")).strip()
    status = normalize_visual_status(data.get("status"), default="complete")
    request_id = _safe_str(data.get("request_id")).strip()
    local_path = _safe_str(data.get("local_path")).strip()
    moderation_status = _first_non_empty(data.get("moderation_status"), "approved")
    moderation_reason = _safe_str(data.get("moderation_reason")).strip()

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    visual_state = _extract_visual_state(simulation_state)
    identities = _safe_dict(visual_state.get("character_visual_identities"))
    identity = _safe_dict(identities.get(actor_id))

    if not identity:
        return jsonify({
            "ok": False,
            "error": "character_not_found",
        }), 404

    # Apply returned fields first, then fallback if needed.
    # This avoids fallback being overwritten by an empty image_url.
    if image_url:
        identity["portrait_url"] = image_url
    identity["portrait_asset_id"] = asset_id
    identity["status"] = status

    # Phase 12.5 — apply fallback for failed/blocked results
    visual_state_defaults = _safe_dict(_extract_visual_state(simulation_state).get("defaults"))
    if status in {"failed", "blocked"}:
        identity = apply_visual_fallback(
            identity,
            visual_state_defaults.get("fallback_portrait_url"),
        )

    simulation_state = upsert_character_visual_identity(
        simulation_state,
        actor_id=actor_id,
        identity=identity,
    )
    simulation_state = _ensure_character_ui_state(simulation_state)

    # Phase 12.3 — register asset in visual asset registry
    version = identity.get("version")
    if not isinstance(version, int) or version < 1:
        version = 1

    simulation_state = append_visual_asset(
        simulation_state,
        build_visual_asset_record(
            kind="character_portrait",
            target_id=actor_id,
            version=version,
            seed=identity.get("seed") if isinstance(identity.get("seed"), int) else None,
            style=_safe_str(identity.get("style")).strip(),
            model=_safe_str(identity.get("model")).strip(),
            prompt=_safe_str(identity.get("base_prompt")).strip(),
            url=_safe_str(identity.get("portrait_url")).strip(),
            local_path=local_path,
            status=status,
            created_from_request_id=request_id,
            moderation_status=moderation_status,
            moderation_reason=moderation_reason,
        ),
    )

    # Phase 12.4 — record appearance event
    simulation_state = append_appearance_event(
        simulation_state,
        actor_id=actor_id,
        event={
            "event_id": f"appearance-result:{actor_id}:{version}",
            "reason": "manual_refresh",
            "summary": f"Portrait result recorded ({status})",
            "tick": 0,
        },
    )

    return jsonify({
        "ok": True,
        "visual_state": _extract_visual_state(simulation_state),
        "character_ui_state": _extract_character_ui_state(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/visual/queue/normalize")
def normalize_visual_queue_route():
    """Reclaim stale leases and dedupe active jobs into canonical form."""
    result = normalize_visual_queue()
    return jsonify(
        {
            "ok": True,
            "total": result.get("total", 0),
            "jobs": result.get("jobs", []),
        }
    )


@rpg_presentation_bp.post("/api/rpg/visual/queue/run_one")
def run_one_queued_job_route():
    """Process one queued job with request-state awareness."""
    payload = request.get_json(force=True, silent=True) or {}
    lease_seconds = int(payload.get("lease_seconds") or 300)
    result = run_one_queued_job(lease_seconds=lease_seconds)
    code = 200 if result.get("ok") else 500
    return jsonify(result), code


@rpg_presentation_bp.post("/api/rpg/scene_illustration/request")
def request_scene_illustration():
    """Create a scene illustration generation request."""
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id") or "").strip()
    setup_payload = _safe_dict(data.get("setup_payload"))
    scene_id = _safe_str(data.get("scene_id")).strip()
    event_id = _safe_str(data.get("event_id")).strip()
    title = _safe_str(data.get("title")).strip()
    prompt = _safe_str(data.get("prompt")).strip()
    style = _safe_str(data.get("style")).strip()
    model = _safe_str(data.get("model")).strip()

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    visual_state = _extract_visual_state(simulation_state)
    defaults = _safe_dict(visual_state.get("defaults"))
    scene_style = _first_non_empty(style, defaults.get("scene_style"), "rpg-scene")
    scene_model = _first_non_empty(model, defaults.get("model"), "default")

    resolved_target = _first_non_empty(event_id, scene_id, title, "scene")
    seed = data.get("seed")
    if not isinstance(seed, int):
        seed = stable_visual_seed_from_text(
            f"{scene_id}|{event_id}|{title}|{scene_style}|{scene_model}"
        )

    # Phase 12.5 — validate prompt
    prompt_check = validate_visual_prompt(prompt)

    request_id = f"scene:{resolved_target}:{seed}"
    now_ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    simulation_state = append_image_request(
        simulation_state,
        {
            "request_id": request_id,
            "kind": "scene_illustration",
            "target_id": resolved_target,
            "prompt": prompt,
            "seed": seed,
            "style": scene_style,
            "model": scene_model,
            "status": "pending" if prompt_check.get("ok") else "blocked",
            "attempts": 0,
            "max_attempts": 3,
            "error": "",
            "created_at": now_ts,
            "updated_at": "",
            "completed_at": "",
        },
    )

    # Phase 12.13.5 — Auto-enqueue on request creation
    if session_id and request_id:
        try:
            enqueue_visual_job(session_id=session_id, request_id=request_id)
        except Exception:
            # Queueing is best-effort; request remains inspectable in simulation state.
            pass

    return jsonify({
        "ok": True,
        "request_id": request_id,
        "moderation": {
            "status": "approved" if prompt_check.get("ok") else "blocked",
            "reason": _safe_str(prompt_check.get("reason")).strip(),
        },
        "visual_state": _extract_visual_state(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/scene_illustration/result")
def complete_scene_illustration():
    """Record completed scene illustration asset metadata."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    request_id = _safe_str(data.get("request_id")).strip()
    status = normalize_visual_status(data.get("status"), default="complete")
    local_path = _safe_str(data.get("local_path")).strip()
    moderation_status = _first_non_empty(data.get("moderation_status"), "approved")
    moderation_reason = _safe_str(data.get("moderation_reason")).strip()

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    scene_id = _safe_str(data.get("scene_id")).strip()
    event_id = _safe_str(data.get("event_id")).strip()
    title = _safe_str(data.get("title")).strip()
    image_url = _safe_str(data.get("image_url")).strip()
    asset_id = _safe_str(data.get("asset_id")).strip()
    seed = data.get("seed") if isinstance(data.get("seed"), int) else None
    style = _safe_str(data.get("style")).strip()
    prompt = _safe_str(data.get("prompt")).strip()
    model = _safe_str(data.get("model")).strip()

    visual_defaults = _safe_dict(_extract_visual_state(simulation_state).get("defaults"))
    illustration_payload = {
        "scene_id": scene_id,
        "event_id": event_id,
        "title": title,
        "image_url": image_url,
        "asset_id": asset_id,
        "seed": seed,
        "style": style,
        "prompt": prompt,
        "model": model,
        "status": status,
    }
    # Phase 12.5 — apply fallback for failed/blocked
    if status in {"failed", "blocked"}:
        illustration_payload = apply_visual_fallback(illustration_payload, visual_defaults.get("fallback_scene_url"))

    simulation_state = append_scene_illustration(
        simulation_state,
        illustration_payload,
    )

    # Phase 12.3 — register asset in visual asset registry
    simulation_state = append_visual_asset(
        simulation_state,
        build_visual_asset_record(
            kind="scene_illustration",
            target_id=_first_non_empty(event_id, scene_id, title, "scene"),
            version=1,
            seed=seed,
            style=style,
            model=model,
            prompt=prompt,
            url=_safe_str(illustration_payload.get("image_url")).strip(),
            local_path=local_path,
            status=status,
            created_from_request_id=request_id,
            moderation_status=moderation_status,
            moderation_reason=moderation_reason,
        ),
    )

    return jsonify({
        "ok": True,
        "visual_state": _extract_visual_state(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/visual_assets")
def presentation_visual_assets():
    """Return replay-safe visual asset registry."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    visual_state = _extract_visual_state(simulation_state)
    return jsonify({
        "ok": True,
        "visual_assets": visual_state.get("visual_assets", []),
        "appearance_profiles": visual_state.get("appearance_profiles", {}),
        "appearance_events": visual_state.get("appearance_events", {}),
    })


# ---------------------------------------------------------------------------
# Phase 12.10 — Visual worker executor route
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/visual/process_requests")
def process_rpg_visual_requests():
    """Process pending visual generation requests through provider worker."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    limit = data.get("limit") if isinstance(data.get("limit"), int) else 8

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = process_pending_image_requests(simulation_state, limit=limit)

    # Persist updated state back to setup_payload (CRITICAL for state continuity)
    if isinstance(setup_payload, dict):
        setup_payload["simulation_state"] = simulation_state

    return jsonify({
        "ok": True,
        "simulation_state": simulation_state,
        "visual_state": _extract_visual_state(simulation_state),
    })


# ---------------------------------------------------------------------------
# Phase 12.6 — Character Card Import / Export
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/character/import")
def import_character_card():
    """Import external character card into canonical RPG seed payload."""
    data = request.get_json(silent=True) or {}
    card = _safe_dict(data.get("card"))
    imported = import_external_character_card(card)
    return jsonify({
        "ok": True,
        "imported": imported,
    })


@rpg_presentation_bp.post("/api/rpg/character/export")
def export_character_card():
    """Export canonical character UI object into portable card format."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_id = _safe_str(data.get("actor_id")).strip()

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    character_ui_state = _extract_character_ui_state(simulation_state)
    characters = character_ui_state.get("characters") if isinstance(character_ui_state, dict) else []
    if not isinstance(characters, list):
        characters = []

    for character in characters:
        if isinstance(character, dict) and _safe_str(character.get("id")).strip() == actor_id:
            return jsonify({
                "ok": True,
                "card": export_canonical_character_card(character),
            })

    return jsonify({
        "ok": False,
        "error": "character_not_found",
    }), 404


# ---------------------------------------------------------------------------
# Phase 12.8 — GM Trace Route
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/gm_trace")
def presentation_gm_trace():
    """Return converged GM trace payload for visuals + appearance + world state."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_id = _safe_str(data.get("actor_id")).strip()

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    visual_state = _extract_visual_state(simulation_state)
    character_ui_state = _extract_character_ui_state(simulation_state)
    character_inspector_state = _extract_character_inspector_state(simulation_state)

    characters = character_ui_state.get("characters") if isinstance(character_ui_state, dict) else []
    if not isinstance(characters, list):
        characters = []

    inspector_characters = character_inspector_state.get("characters") if isinstance(character_inspector_state, dict) else []
    if not isinstance(inspector_characters, list):
        inspector_characters = []

    selected_character = None
    for character in characters:
        if isinstance(character, dict) and _safe_str(character.get("id")).strip() == actor_id:
            selected_character = character
            break

    selected_inspector = None
    for character in inspector_characters:
        if isinstance(character, dict) and _safe_str(character.get("id")).strip() == actor_id:
            selected_inspector = character
            break

    appearance_events = _safe_dict(visual_state.get("appearance_events")).get(actor_id, [])
    if not isinstance(appearance_events, list):
        appearance_events = []

    visual_assets = [
        item for item in _safe_list(visual_state.get("visual_assets"))
        if isinstance(item, dict) and _safe_str(item.get("target_id")).strip() == actor_id
    ]

    image_requests = [
        item for item in _safe_list(visual_state.get("image_requests"))
        if isinstance(item, dict) and _safe_str(item.get("target_id")).strip() == actor_id
    ]

    return jsonify({
        "ok": True,
        "trace": {
            "character": selected_character,
            "inspector": selected_inspector,
            "appearance_events": appearance_events,
            "visual_assets": visual_assets,
            "image_requests": image_requests,
        },
    })


# ---------------------------------------------------------------------------
# Phase 12.9 — Save / Export / Packaging Layer
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/package/export")
def export_rpg_package():
    """Export current RPG session to portable package format."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    title = _safe_str(data.get("title")).strip() or "RPG Session Export"
    description = _safe_str(data.get("description")).strip()
    created_by = _safe_str(data.get("created_by")).strip() or "unknown"

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    package_data = export_session_package(
        simulation_state,
        title=title,
        description=description,
        created_by=created_by,
    )

    return jsonify({
        "ok": True,
        "package": package_data,
    })


@rpg_presentation_bp.post("/api/rpg/package/import")
def import_rpg_package():
    """Import portable RPG package into canonical normalized state."""
    data = request.get_json(silent=True) or {}
    package_data = _safe_dict(data.get("package"))

    imported = import_session_package(package_data)
    return jsonify({
        "ok": True,
        "imported": imported,
    })


# ---------------------------------------------------------------------------
# Phase 13.0 — Modding / Extension System / Content Pack Pipeline
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/packs/list")
def list_rpg_packs():
    """List installed RPG content packs."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)

    return jsonify({
        "ok": True,
        "packs": list_content_packs(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/packs/preview")
def preview_rpg_pack():
    """Preview a content pack before installation/application."""
    data = request.get_json(silent=True) or {}
    pack = _safe_dict(data.get("pack"))
    preview = build_pack_application_preview(pack)
    return jsonify({
        "ok": True,
        "preview": preview,
    })


@rpg_presentation_bp.post("/api/rpg/packs/apply")
def apply_rpg_pack():
    """Apply a content pack to current simulation presentation/modding state."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    pack = _safe_dict(data.get("pack"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)
    simulation_state = apply_content_pack(simulation_state, pack)

    return jsonify({
        "ok": True,
        "packs": list_content_packs(simulation_state),
        "visual_state": _extract_visual_state(simulation_state),
    })


# ---------------------------------------------------------------------------
# Phase 13.1 — Scenario Packs + Start-from-Pack flow
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/packs/bootstrap")
def bootstrap_rpg_pack():
    """Build deterministic new-session bootstrap payload from a content pack."""
    data = request.get_json(silent=True) or {}
    pack = _safe_dict(data.get("pack"))
    bootstrap = build_pack_bootstrap_payload(pack)
    return jsonify({
        "ok": True,
        "bootstrap": bootstrap,
    })


@rpg_presentation_bp.post("/api/rpg/packs/start")
def start_rpg_from_pack():
    """Return normalized new-session setup payload from a scenario/content pack."""
    data = request.get_json(silent=True) or {}
    pack = _safe_dict(data.get("pack"))
    bootstrap = build_pack_bootstrap_payload(pack)

    simulation_state = {
        "presentation_state": {
            "visual_state": {
                "defaults": _safe_dict(bootstrap.get("visual_defaults")),
            }
        },
        "world_state": {
            "scenario_title": _safe_str(bootstrap.get("title")).strip(),
            "scenario_summary": _safe_str(bootstrap.get("summary")).strip(),
            "opening": _safe_str(bootstrap.get("opening")).strip(),
            "world_seed": _safe_dict(bootstrap.get("world_seed")),
        },
    }

    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    return jsonify({
        "ok": True,
        "setup_payload": {
            "simulation_state": simulation_state,
            "bootstrap": bootstrap,
        },
    })


# ---------------------------------------------------------------------------
# Phase 13.2 — Creator Pack Authoring / Validation / Preview
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/creator/pack/validate")
def validate_rpg_pack_draft():
    """Validate creator pack draft without mutating live state."""
    data = request.get_json(silent=True) or {}
    draft = _safe_dict(data.get("draft"))
    validation = validate_pack_draft(draft)
    return jsonify({
        "ok": True,
        "validation": validation,
    })


@rpg_presentation_bp.post("/api/rpg/creator/pack/preview")
def preview_rpg_pack_draft():
    """Preview creator pack draft application/export."""
    data = request.get_json(silent=True) or {}
    draft = _safe_dict(data.get("draft"))
    preview = build_pack_draft_preview(draft)
    return jsonify({
        "ok": True,
        "preview": preview,
    })


@rpg_presentation_bp.post("/api/rpg/creator/pack/export")
def export_rpg_pack_draft():
    """Export validated pack draft as data-only content pack payload."""
    data = request.get_json(silent=True) or {}
    draft = _safe_dict(data.get("draft"))
    exported = build_pack_draft_export(draft)
    return jsonify({
        "ok": True,
        "pack": exported,
    })


# ---------------------------------------------------------------------------
# Phase 13.3 — Campaign Template / Adventure Bootstrap
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/templates/build")
def build_rpg_template():
    """Build reusable campaign template from bootstrap payload."""
    data = request.get_json(silent=True) or {}
    template_id = _safe_str(data.get("template_id")).strip() or "template:default"
    title = _safe_str(data.get("title")).strip() or "Campaign Template"
    description = _safe_str(data.get("description")).strip()
    bootstrap = _safe_dict(data.get("bootstrap"))

    template = build_campaign_template(
        template_id=template_id,
        title=title,
        description=description,
        bootstrap=bootstrap,
    )
    return jsonify({
        "ok": True,
        "template": template,
    })


@rpg_presentation_bp.post("/api/rpg/templates/start")
def start_rpg_template():
    """Build start-session payload from campaign template."""
    data = request.get_json(silent=True) or {}
    template = _safe_dict(data.get("template"))
    start_payload = build_template_start_payload(template)

    setup_payload = _safe_dict(start_payload.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    setup_payload["simulation_state"] = simulation_state
    start_payload["setup_payload"] = setup_payload

    return jsonify({
        "ok": True,
        "start": start_payload,
    })


@rpg_presentation_bp.post("/api/rpg/templates/list")
def list_rpg_templates():
    """Normalize/list provided campaign templates."""
    data = request.get_json(silent=True) or {}
    templates = _safe_list(data.get("templates"))
    return jsonify({
        "ok": True,
        "templates": list_campaign_templates(templates),
    })


# ---------------------------------------------------------------------------
# Phase 13.4 — New Adventure Wizard UI
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/wizard/preview")
def preview_rpg_wizard():
    """Preview wizard-composed adventure bootstrap."""
    data = request.get_json(silent=True) or {}
    wizard_state = normalize_wizard_state(data.get("wizard_state"))
    return jsonify({
        "ok": True,
        "preview": build_wizard_preview_payload(wizard_state),
    })


@rpg_presentation_bp.post("/api/rpg/wizard/build")
def build_rpg_wizard_setup():
    """Build normalized setup payload from wizard state."""
    data = request.get_json(silent=True) or {}
    wizard_state = normalize_wizard_state(data.get("wizard_state"))
    setup_payload = build_wizard_setup_payload(wizard_state)

    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    setup_payload["simulation_state"] = simulation_state

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
    })


# ---------------------------------------------------------------------------
# Phase 13.5 — Session lifecycle + persistence
# ---------------------------------------------------------------------------

_RPG_SESSION_ROOT_STATE: Dict[str, Any] = {"sessions": []}


@rpg_presentation_bp.post("/api/rpg/session/save")
def save_rpg_session():
    """Save normalized RPG session snapshot into in-memory registry and disk."""
    global _RPG_SESSION_ROOT_STATE
    data = request.get_json(silent=True) or {}
    session = _safe_dict(data.get("session"))
    _RPG_SESSION_ROOT_STATE = save_session(_RPG_SESSION_ROOT_STATE, session)
    save_session_to_disk(session)
    return jsonify({
        "ok": True,
        "sessions": list_sessions(_RPG_SESSION_ROOT_STATE),
    })


@rpg_presentation_bp.post("/api/rpg/session/list")
def list_rpg_sessions():
    """List saved RPG sessions from disk, falling back to in-memory."""
    global _RPG_SESSION_ROOT_STATE
    _RPG_SESSION_ROOT_STATE = ensure_session_registry(_RPG_SESSION_ROOT_STATE)
    disk_sessions = list_sessions_from_disk()
    return jsonify({
        "ok": True,
        "sessions": disk_sessions or list_sessions(_RPG_SESSION_ROOT_STATE),
    })


@rpg_presentation_bp.post("/api/rpg/session/load")
def load_rpg_session():
    """Load a saved RPG session by id from disk or in-memory."""
    global _RPG_SESSION_ROOT_STATE
    data = request.get_json(silent=True) or {}
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_session_from_disk(session_id) or get_session(_RPG_SESSION_ROOT_STATE, session_id)
    if not session:
        return jsonify({"ok": False, "error": "session_not_found"}), 404
    return jsonify({
        "ok": True,
        "session": session,
    })


@rpg_presentation_bp.post("/api/rpg/session/archive")
def archive_rpg_session():
    """Archive a saved RPG session."""
    global _RPG_SESSION_ROOT_STATE
    data = request.get_json(silent=True) or {}
    session_id = _safe_str(data.get("session_id")).strip()
    _RPG_SESSION_ROOT_STATE = archive_session(_RPG_SESSION_ROOT_STATE, session_id)
    return jsonify({
        "ok": True,
        "sessions": list_sessions(_RPG_SESSION_ROOT_STATE),
    })


# ---------------------------------------------------------------------------
# Phase 14.0 — Memory system
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/memory/get")
def get_rpg_memory():
    """Return normalized memory state for current simulation."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    return jsonify({
        "ok": True,
        "memory_state": _safe_dict(simulation_state.get("memory_state")),
    })


@rpg_presentation_bp.post("/api/rpg/memory/add")
def add_rpg_memory():
    """Append memory entry to selected memory lane."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    lane = _safe_str(data.get("lane")).strip() or "short_term"
    entry = _safe_dict(data.get("entry"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)

    if lane == "long_term":
        simulation_state = append_long_term_memory(simulation_state, entry)
    elif lane == "world_memory":
        simulation_state = append_world_memory(simulation_state, entry)
    else:
        simulation_state = append_short_term_memory(simulation_state, entry)

    return jsonify({
        "ok": True,
        "memory_state": _safe_dict(simulation_state.get("memory_state")),
    })


# ---------------------------------------------------------------------------
# Part 1/16 — content-pack state in main presentation routes
# ---------------------------------------------------------------------------

def _add_content_pack_data(response_dict: Dict[str, Any], simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Add content_packs and package_manifest to a response dict."""
    response_dict["content_packs"] = list_content_packs(simulation_state)
    response_dict["package_manifest"] = {
        "package_version": "1.0",
        "title": "",
        "description": "",
        "created_by": "",
    }
    return response_dict


# ---------------------------------------------------------------------------
# Phase 14.3 — Memory → Dialogue Injection routes
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/memory/dialogue_context")
def get_rpg_memory_dialogue_context():
    """Return dialogue memory context for given actors."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_ids = data.get("actor_ids") if isinstance(data.get("actor_ids"), list) else []
    actor_ids = [_safe_str(aid).strip() for aid in actor_ids if _safe_str(aid).strip()][:6]

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)

    memory_context = build_dialogue_memory_context(simulation_state, actor_ids)
    memory_prompt_block = build_llm_memory_prompt_block(memory_context)

    return jsonify({
        "ok": True,
        "dialogue_memory_context": memory_context,
        "llm_memory_prompt_block": memory_prompt_block,
    })


# ---------------------------------------------------------------------------
# Phase 14.4 — Memory Decay / Reinforcement route
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/memory/decay")
def decay_rpg_memory():
    """Apply deterministic decay/reinforcement pass to memory state."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    current_tick = data.get("current_tick") if isinstance(data.get("current_tick"), int) else 0

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)
    simulation_state = apply_memory_decay(simulation_state, current_tick=current_tick)

    return jsonify({
        "ok": True,
        "memory_state": _safe_dict(simulation_state.get("memory_state")),
    })


# ---------------------------------------------------------------------------
# Phase 15.1 — Session ↔ Package Unification routes
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/session/export_package")
def export_session_as_package():
    """Export a saved session as portable package."""
    data = request.get_json(silent=True) or {}
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_session_from_disk(session_id) or get_session(_RPG_SESSION_ROOT_STATE, session_id)
    if not session:
        return jsonify({"ok": False, "error": "session_not_found"}), 404

    package_data = session_to_package(session)
    return jsonify({
        "ok": True,
        "package": package_data,
    })


@rpg_presentation_bp.post("/api/rpg/session/import_package")
def import_package_as_session():
    """Import portable package as new saved session."""
    global _RPG_SESSION_ROOT_STATE
    data = request.get_json(silent=True) or {}
    package_data = _safe_dict(data.get("package"))
    session_id = _safe_str(data.get("session_id")).strip() or "imported_session"
    title = _safe_str(data.get("title")).strip() or "Imported Session"

    session = package_to_session(package_data, session_id=session_id, title=title)
    _RPG_SESSION_ROOT_STATE = save_session(_RPG_SESSION_ROOT_STATE, session)
    save_session_to_disk(session)

    return jsonify({
        "ok": True,
        "session": session,
    })


# ---------------------------------------------------------------------------
# Phase 12.13 — Visual Queue Management routes
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/visual/queue/enqueue")
def queue_visual_job_route():
    """Enqueue a visual generation job for background processing."""
    payload = request.get_json(force=True, silent=True) or {}
    session_id = str(payload.get("session_id") or "").strip()
    request_id = str(payload.get("request_id") or "").strip()
    if not session_id or not request_id:
        return jsonify({"ok": False, "error": "session_id_and_request_id_required"}), 400
    job = enqueue_visual_job(session_id=session_id, request_id=request_id)
    return jsonify({"ok": True, "job": job})


@rpg_presentation_bp.post("/api/rpg/visual/queue/run_once")
def run_visual_queue_once_route():
    """Process one visual job from the queue."""
    payload = request.get_json(force=True, silent=True) or {}
    lease_seconds = int(payload.get("lease_seconds") or 300)
    result = run_one_visual_job(lease_seconds=lease_seconds)
    code = 200 if result.get("ok") else 500
    return jsonify(result), code


@rpg_presentation_bp.get("/api/rpg/visual/queue/stats")
def visual_queue_stats_route():
    """Return visual queue statistics and job list."""
    return jsonify({"ok": True, "stats": get_visual_queue_stats(), "jobs": list_visual_jobs()})


@rpg_presentation_bp.post("/api/rpg/visual/queue/prune")
def prune_visual_queue_route():
    """Prune completed jobs from the queue."""
    payload = request.get_json(force=True, silent=True) or {}
    keep_last = int(payload.get("keep_last") or 200)
    result = prune_completed_visual_jobs(keep_last=keep_last)
    return jsonify({"ok": True, "result": result, "jobs": list_visual_jobs()})


# ---------------------------------------------------------------------------
# Phase 12.14 — Asset cleanup route
# ---------------------------------------------------------------------------

@rpg_presentation_bp.post("/api/rpg/visual/assets/cleanup")
def cleanup_visual_assets_route():
    """Cleanup unused visual assets for a session."""
    payload = request.get_json(force=True, silent=True) or {}
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"ok": False, "error": "session_id_required"}), 400

    from app.rpg.session.durable_store import load_session_from_disk, save_session_to_disk

    session_data = load_session_from_disk(session_id) or {}
    simulation_state = session_data.get("simulation_state") or {}
    result = cleanup_unused_assets(simulation_state)
    session_data["simulation_state"] = result["simulation_state"]
    save_session_to_disk(session_data)
    return jsonify(
        {
            "ok": True,
            "deleted_asset_ids": result["deleted_asset_ids"],
            "deleted_files": result["deleted_files"],
        }
    )
