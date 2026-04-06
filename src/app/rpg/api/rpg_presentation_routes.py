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
    ensure_content_pack_state,
    list_content_packs,
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


def _ensure_world_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
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
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

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
        "character_ui_state": _extract_character_ui_state(simulation_state),
        "character_inspector_state": _extract_character_inspector_state(simulation_state),
        "world_inspector_state": _extract_world_inspector_state(simulation_state),
        "visual_state": _extract_visual_state(simulation_state),
    })


@rpg_presentation_bp.post("/api/rpg/presentation/dialogue")
def presentation_dialogue():
    """Build a presentation-ready dialogue payload."""
    data = request.get_json(silent=True) or {}
    setup_payload = _safe_dict(data.get("setup_payload"))
    dialogue_state = _safe_dict(data.get("dialogue_state"))

    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

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
        "character_ui_state": _extract_character_ui_state(simulation_state),
        "character_inspector_state": _extract_character_inspector_state(simulation_state),
        "world_inspector_state": _extract_world_inspector_state(simulation_state),
        "visual_state": _extract_visual_state(simulation_state),
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
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    runtime_payload = build_runtime_presentation_payload(simulation_state)
    payload = build_narrative_recap_payload(simulation_state, runtime_payload)
    return jsonify({
        "ok": True,
        "presentation": payload,
        "character_ui_state": _extract_character_ui_state(simulation_state),
        "character_inspector_state": _extract_character_inspector_state(simulation_state),
        "world_inspector_state": _extract_world_inspector_state(simulation_state),
        "visual_state": _extract_visual_state(simulation_state),
    })


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
        },
    )

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


@rpg_presentation_bp.post("/api/rpg/scene_illustration/request")
def request_scene_illustration():
    """Create a scene illustration generation request."""
    data = request.get_json(silent=True) or {}
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
        },
    )

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
