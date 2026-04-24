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

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rpg.compat.character_cards import (
    export_canonical_character_card,
    import_external_character_card,
)
from app.rpg.creator.pack_authoring import (
    build_pack_draft_export,
    build_pack_draft_preview,
    validate_pack_draft,
)
from app.rpg.memory.actor_memory_state import ensure_actor_memory_state

# Phase 14.4 — Memory decay (canonical decay engine)
from app.rpg.memory.decay import decay_memory_state, reinforce_actor_memory

# Phase 14.3 — Memory → Dialogue Injection (canonical)
from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)

# Phase 16.1 — Memory lifecycle automation
from app.rpg.memory.lifecycle import apply_dialogue_memory_hooks

# Phase 14.4 — Memory Decay / Reinforcement

# Phase 14.0 — Memory system
from app.rpg.memory.memory_state import (
    append_long_term_memory,
    append_short_term_memory,
    append_world_memory,
    ensure_memory_state,
)
from app.rpg.memory.world_memory_state import ensure_world_memory_state
from app.rpg.modding.content_packs import (
    apply_content_pack,
    build_pack_application_preview,
    build_pack_bootstrap_payload,
    ensure_content_pack_state,
    list_content_packs,
)
from app.rpg.packaging.package_io import (
    export_session_package,
    import_session_package,
)
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

# Phase 18.0 — Unified GM tooling
from app.rpg.presentation.gm_tooling import build_gm_tooling_payload

# Phase 16.2 — Memory inspector
from app.rpg.presentation.memory_inspector import build_memory_inspector_payload
from app.rpg.presentation.personality_state import ensure_personality_state
from app.rpg.presentation.speaker_cards import build_speaker_cards

# Phase 12.15 — Visual inspector
from app.rpg.presentation.visual_inspector import build_visual_inspector_payload
from app.rpg.presentation.visual_state import (
    append_appearance_event,
    append_image_request,
    append_scene_illustration,
    append_visual_asset,
    build_visual_asset_record,
    ensure_visual_state,
    mark_image_request_complete,
    normalize_visual_status,
    update_image_request,
    stable_visual_seed_from_text,
    upsert_appearance_profile,
    upsert_character_visual_identity,
    validate_visual_prompt,
)
from app.rpg.visual.worker import (
    _complete_character_portrait,
    _complete_scene_illustration,
)

# Phase 15.0 — Durable persistence
from app.rpg.session.durable_store import (
    list_sessions_from_disk,
    load_session_from_disk,
    save_session_to_disk,
)
from app.rpg.session.runtime import (
    load_runtime_session,
    save_runtime_session,
)
from app.rpg.session.migrations import migrate_session_payload

# Phase 15.2 — Session/package bridge with validation and normalization

# Phase 15.3 — Canonical session service
from app.rpg.session.service import (
    export_session_as_package,
    import_session_from_package,
)

# Phase 13.5 — Session lifecycle + persistence
from app.rpg.session.session_store import (
    archive_session,
    ensure_session_registry,
    get_session,
    list_sessions,
    save_session,
)

# Phase 13.4 — New Adventure Wizard UI
from app.rpg.setup.wizard_state import (
    build_wizard_preview_payload,
    build_wizard_setup_payload,
    normalize_wizard_state,
)
from app.rpg.social.conversation_presentation import build_conversation_payload
from app.rpg.templates.campaign_templates import (
    build_campaign_template,
    build_template_start_payload,
    list_campaign_templates,
)
from app.rpg.ui.character_builder import (
    build_character_inspector_state,
    build_character_ui_state,
)
from app.rpg.ui.world_builder import build_world_inspector_state

# Phase 17.0 — Integrity validation
from app.rpg.validation.integrity import (
    validate_memory_state,
    validate_package_integrity,
    validate_session_integrity,
    validate_simulation_state,
    validate_visual_state,
)

# Phase 12.14 — Asset dedupe and cleanup
from app.rpg.visual.asset_store import cleanup_unused_assets, get_asset_manifest
from app.image.downloads import download_flux_klein_model, get_flux_local_model_status
from app.image.lifecycle import load_image_provider, unload_image_provider
from app.image.settings_api import get_image_settings_payload

# Phase 12.13.5 — Visual queue management with hardening
from app.rpg.visual.job_queue import (
    enqueue_visual_job,
    list_visual_jobs,
    normalize_visual_queue,
    prune_completed_visual_jobs,
)

# Phase 12.12 — ComfyUI provider
from app.rpg.visual.providers import (
    get_loaded_image_provider_name,
    get_visual_provider_status_payload,
    is_image_provider_loaded,
    preload_image_provider,
    switch_image_provider_runtime,
)
from app.rpg.visual.providers import unload_image_provider_cache
from app.shared import load_settings, save_settings
from app.rpg.visual.queue_runner import run_one_queued_job

# Phase 12.10 — Visual worker executor
from app.rpg.visual.worker import process_pending_image_requests

rpg_presentation_bp = APIRouter()


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


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def _request_nonce() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")


def _drop_visual_requests_for_target(simulation_state: Dict[str, Any], *, kind: str, target_id: str) -> Dict[str, Any]:
    simulation_state = ensure_visual_state(_safe_dict(simulation_state))
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    requests = _safe_list(visual_state.get("image_requests"))
    visual_state["image_requests"] = [
        item for item in requests
        if not (isinstance(item, dict) and _safe_str(item.get("kind")).strip() == kind and _safe_str(item.get("target_id")).strip() == target_id)
    ]
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


def _load_visual_request_simulation_state(session_id: str, setup_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prefer the persisted session simulation_state for visual requests.
    Falling back to setup_payload is only for non-session / preview flows.
    """
    session_id = _safe_str(session_id).strip()
    setup_payload = _safe_dict(setup_payload)

    if session_id:
        try:
            session = load_runtime_session(session_id)
            if isinstance(session, dict):
                persisted = session.get("simulation_state")
                if persisted:
                    return _safe_dict(persisted)
        except Exception:
            pass

    return _safe_dict(_get_simulation_state(setup_payload))


def _persist_visual_session(session_id, simulation_state, *, expected_request_id: str = "") -> bool:
    session_id = _safe_str(session_id).strip()
    if not session_id:
        return False
    try:
        session = load_runtime_session(session_id)
        if not isinstance(session, dict):
            return False

        updated = dict(session)
        updated["simulation_state"] = _safe_dict(simulation_state)
        save_runtime_session(updated)

        reloaded = load_runtime_session(session_id)
        if not isinstance(reloaded, dict):
            return False

        reloaded_state = _safe_dict(reloaded.get("simulation_state"))
        if not expected_request_id:
            return bool(reloaded_state)

        visual_state = _safe_dict(_safe_dict(reloaded_state.get("presentation_state")).get("visual_state"))
        requests = _safe_list(visual_state.get("image_requests"))
        return any(
            isinstance(item, dict)
            and _safe_str(item.get("request_id")).strip() == expected_request_id
            for item in requests
        )
    except Exception:
        return False


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _safe_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    if isinstance(v, int):
        return v
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _clip_visual_prompt_text(value: Any, limit: int = 320) -> str:
    text = " ".join(_safe_str(value).replace("\n", " ").split()).strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _is_generic_scene_visual_prompt(prompt: str) -> bool:
    text = _safe_str(prompt).strip().lower()
    if not text:
        return True
    generic_markers = [
        "fantasy scene, fantasy location",
        "fantasy location, medieval setting",
        "scene illustration of scene:",
        "scene illustration of the current scene",
        "detailed environment, cinematic composition",
    ]
    return any(marker in text for marker in generic_markers)


def _lookup_location_record(simulation_state: Dict[str, Any], location_id: str) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    location_id = _safe_str(location_id).strip()
    if not location_id:
        return {}

    candidates = [
        _safe_dict(simulation_state.get("locations")),
        _safe_dict(_safe_dict(simulation_state.get("world_state")).get("locations")),
        _safe_dict(_safe_dict(simulation_state.get("world")).get("locations")),
    ]

    for locations in candidates:
        direct = _safe_dict(locations.get(location_id))
        if direct:
            return direct
        for item in locations.values():
            row = _safe_dict(item)
            if _safe_str(row.get("id")).strip() == location_id or _safe_str(row.get("location_id")).strip() == location_id:
                return row

    return {}


def _humanize_visual_id(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    if text.startswith("scene:") or text.startswith("portrait:") or text.startswith("job:"):
        return ""
    return text.replace("loc_", "").replace("scene_", "").replace("_", " ").replace("-", " ").strip().title()


def _derive_scene_visual_context(simulation_state: Dict[str, Any], *, scene_id: str, event_id: str, title: str) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(simulation_state.get("runtime_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene") or simulation_state.get("current_scene"))
    player_state = _safe_dict(simulation_state.get("player_state"))

    location_id = _first_non_empty(
        current_scene.get("location_id"),
        player_state.get("location_id"),
        scene_id,
    )
    location = _lookup_location_record(simulation_state, location_id)

    scene_title = _first_non_empty(
        title,
        current_scene.get("title"),
        current_scene.get("name"),
        location.get("title"),
        location.get("name"),
        _humanize_visual_id(location_id),
        _humanize_visual_id(scene_id),
        "Current fantasy scene",
    )

    scene_description = _first_non_empty(
        current_scene.get("description"),
        current_scene.get("summary"),
        current_scene.get("scene"),
        location.get("description"),
        location.get("summary"),
        location.get("flavor"),
    )

    npc_index = _safe_dict(simulation_state.get("npc_index"))
    present_ids = []
    seen = set()
    for raw_id in (
        _safe_list(current_scene.get("present_npc_ids"))
        + _safe_list(player_state.get("nearby_npc_ids"))
    ):
        npc_id = _safe_str(raw_id).strip()
        if npc_id and npc_id not in seen:
            seen.add(npc_id)
            present_ids.append(npc_id)

    if not present_ids and location_id:
        for npc_id, raw_npc in npc_index.items():
            npc = _safe_dict(raw_npc)
            if _safe_str(npc.get("location_id")).strip() == location_id:
                npc_id = _safe_str(npc_id).strip()
                if npc_id and npc_id not in seen:
                    seen.add(npc_id)
                    present_ids.append(npc_id)

    npc_names = []
    for npc_id in present_ids[:6]:
        npc = _safe_dict(npc_index.get(npc_id))
        npc_name = _first_non_empty(npc.get("name"), npc.get("title"), _humanize_visual_id(npc_id))
        if npc_name:
            npc_names.append(npc_name)

    return {
        "title": scene_title,
        "description": scene_description,
        "location_id": location_id,
        "location_type": _first_non_empty(location.get("type"), current_scene.get("type"), "fantasy location"),
        "present_npc_names": npc_names,
    }


def _scene_type_visual_details(title: str, location_type: str) -> str:
    text = f"{title} {location_type}".lower()
    if "tavern" in text or "inn" in text or "flagon" in text:
        return (
            "medieval tavern interior, worn wooden tables, rough timber beams, "
            "warm lantern light, smoky hearth, mugs and bottles behind the bar, "
            "shadowed corners with patrons watching"
        )
    if "market" in text or "shop" in text or "merchant" in text:
        return "busy medieval market details, stacked goods, hanging signs, cloth awnings, trade stalls"
    if "forest" in text or "woods" in text:
        return "ancient forest details, mossy roots, dense trees, filtered light, mysterious undergrowth"
    if "road" in text or "street" in text:
        return "weathered medieval road, stone and mud textures, distant buildings, travel-worn atmosphere"
    return "detailed fantasy environment, grounded physical layout, believable props, clear sense of place"


def build_grounded_scene_illustration_prompt(
    simulation_state: Dict[str, Any],
    *,
    scene_id: str,
    event_id: str,
    title: str,
    prompt: str,
) -> str:
    context = _derive_scene_visual_context(
        simulation_state,
        scene_id=scene_id,
        event_id=event_id,
        title=title,
    )
    scene_title = _clip_visual_prompt_text(context.get("title"), 120)
    description = _clip_visual_prompt_text(context.get("description"), 360)
    location_type = _clip_visual_prompt_text(context.get("location_type"), 80)
    npc_names = [
        _clip_visual_prompt_text(name, 80)
        for name in _safe_list(context.get("present_npc_names"))
        if _clip_visual_prompt_text(name, 80)
    ]

    parts = []
    if scene_title:
        parts.append(scene_title)
    if location_type and location_type.lower() not in {"fantasy location", scene_title.lower()}:
        parts.append(f"Location type: {location_type}")
    if description:
        parts.append(description)
    if npc_names:
        parts.append(f"Present characters: {', '.join(npc_names)}")

    prompt_hint = _clip_visual_prompt_text(prompt, 260)
    if prompt_hint and not _is_generic_scene_visual_prompt(prompt_hint):
        parts.append(f"Visual request hint: {prompt_hint}")

    parts.append(f"Environment details: {_scene_type_visual_details(scene_title, location_type)}")
    parts.append(
        "High-quality fantasy illustration, cinematic composition, immersive atmosphere, "
        "natural lighting, sharp detail, coherent architecture, no text, no UI, no labels."
    )

    return ". ".join(part.strip(" .") for part in parts if part).strip() + "."


def _derive_present_npc_ids(simulation_state: dict, runtime_state: dict, setup_payload: dict) -> list[str]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    setup_payload = _safe_dict(setup_payload)

    player_state = _safe_dict(simulation_state.get("player_state"))
    opening = _safe_dict(setup_payload.get("opening"))

    nearby_ids = [str(x) for x in _safe_list(player_state.get("nearby_npc_ids")) if str(x).strip()]
    opening_ids = [str(x) for x in _safe_list(opening.get("present_npc_ids")) if str(x).strip()]

    present = []
    seen = set()
    for npc_id in nearby_ids + opening_ids:
        if npc_id and npc_id not in seen:
            seen.add(npc_id)
            present.append(npc_id)
    return present


def _derive_known_npc_ids(simulation_state: dict, runtime_state: dict) -> list[str]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    known_ids = []
    seen = set()

    # Only use runtime known/discovered memory
    discovered = _safe_list(runtime_state.get("known_npc_ids"))
    for npc_id in discovered:
        npc_id = str(npc_id).strip()
        if npc_id and npc_id not in seen:
            seen.add(npc_id)
            known_ids.append(npc_id)

    return known_ids


def _derive_npc_live_state(npc_id: str, simulation_state: dict, runtime_state: dict) -> dict:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    npc_index = _safe_dict(simulation_state.get("npc_index"))
    npc_info = _safe_dict(npc_index.get(npc_id))
    npc_minds = _safe_dict(simulation_state.get("npc_minds"))
    mind = _safe_dict(npc_minds.get(npc_id))
    player_state = _safe_dict(simulation_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))

    nearby_ids = set(str(x) for x in _safe_list(player_state.get("nearby_npc_ids")))
    player_loc = _safe_str(player_state.get("location_id"))
    npc_loc = _safe_str(npc_info.get("location_id"))

    beliefs = _safe_dict(mind.get("beliefs"))
    player_belief = _safe_dict(beliefs.get("player"))
    trust = float(player_belief.get("trust", 0) or 0)
    hostility = float(player_belief.get("hostility", 0) or 0)

    relation = "neutral"
    if hostility > 0.5:
        relation = "hostile"
    elif trust > 0.5:
        relation = "friendly"
    elif trust > 0.2:
        relation = "warm"
    elif hostility > 0.2:
        relation = "uneasy"

    goals = _safe_list(mind.get("goals"))
    current_activity = _safe_str(npc_info.get("current_activity"))
    if not current_activity:
        current_activity = _safe_str(goals[0]) if goals else "observing the situation"

    mood = _safe_str(npc_info.get("mood"))
    if not mood:
        if hostility > 0.6:
            mood = "angry"
        elif hostility > 0.25:
            mood = "suspicious"
        elif trust > 0.5:
            mood = "calm"
        else:
            mood = "guarded"

    focus = _safe_str(npc_info.get("focus"))
    if not focus:
        if hostility > 0.4 or trust > 0.3:
            focus = "player"
        else:
            focus = _safe_str(current_scene.get("scene_id")) or "the area"

    last_action = _safe_str(npc_info.get("last_action"))
    if not last_action:
        last_action = current_activity

    return {
        "is_nearby": npc_id in nearby_ids,
        "is_present": npc_loc == player_loc or npc_id in nearby_ids,
        "location_id": npc_loc,
        "current_activity": current_activity,
        "mood": mood,
        "focus": focus,
        "relation_to_player": relation,
        "last_action": last_action,
    }


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
    return {"characters": characters, "count": count}


def _get_simulation_state(setup_payload: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(setup_payload).get("simulation_state"))


def _ensure_character_ui_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state")
    if not isinstance(presentation_state, dict):
        presentation_state = {}
        simulation_state["presentation_state"] = presentation_state
    presentation_state["character_ui_state"] = build_character_ui_state(simulation_state)
    return simulation_state


def _extract_character_ui_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
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
    return {"characters": characters, "count": count}


def _ensure_character_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state")
    if not isinstance(presentation_state, dict):
        presentation_state = {}
        simulation_state["presentation_state"] = presentation_state
    presentation_state["character_inspector_state"] = build_character_inspector_state(simulation_state)
    return simulation_state


def _extract_character_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    presentation_state = simulation_state.get("presentation_state") or {}
    if not isinstance(presentation_state, dict):
        presentation_state = {}
    inspector_state = presentation_state.get("character_inspector_state") or {"characters": [], "count": 0}
    return _safe_character_inspector_state(inspector_state)


def _safe_world_inspector_state(v: Any) -> Dict[str, Any]:
    if not isinstance(v, dict):
        return {"summary": {}, "threads": [], "thread_count": 0, "factions": {"factions": [], "count": 0}, "locations": {"locations": [], "count": 0}}
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
    return {"summary": summary, "threads": threads, "thread_count": thread_count, "factions": factions, "locations": locations}


def _build_actor_activity_context(runtime_state: dict, actor_id: str) -> dict:
    runtime_state = _safe_dict(runtime_state)
    actor_id = _safe_str(actor_id)
    activity = _safe_dict(_safe_dict(runtime_state.get("actor_activities")).get(actor_id))
    if not activity:
        return {}
    return {
        "activity_id": _safe_str(activity.get("activity_id")),
        "kind": _safe_str(activity.get("kind")),
        "summary": _safe_str(activity.get("summary")),
        "intent": _safe_str(activity.get("intent")),
        "location_id": _safe_str(activity.get("location_id")),
        "started_tick": _safe_int(activity.get("started_tick"), 0),
        "updated_tick": _safe_int(activity.get("updated_tick"), 0),
        "status": _safe_str(activity.get("status")),
        "world_tags": _safe_list(activity.get("world_tags")),
    }


def _build_recent_consequence_context(runtime_state: dict, actor_id: str, location_id: str = "") -> dict:
    runtime_state = _safe_dict(runtime_state)
    actor_id = _safe_str(actor_id)
    location_id = _safe_str(location_id)

    recent = []
    for consequence in _safe_list(runtime_state.get("world_consequences"))[-12:]:
        consequence = _safe_dict(consequence)
        c_actor = _safe_str(consequence.get("source_actor_id"))
        c_loc = _safe_str(consequence.get("location_id"))
        if actor_id and c_actor == actor_id:
            recent.append(consequence)
            continue
        if location_id and c_loc == location_id:
            recent.append(consequence)

    recent = recent[-4:]

    local_pressure = []
    for p in _safe_list(runtime_state.get("world_pressure")):
        p = _safe_dict(p)
        if location_id and _safe_str(p.get("location_id")) == location_id:
            local_pressure.append({
                "kind": _safe_str(p.get("kind")),
                "value": _safe_int(p.get("value"), 0),
                "summary": _safe_str(p.get("summary")),
            })

    local_conditions = []
    for c in _safe_list(runtime_state.get("location_conditions")):
        c = _safe_dict(c)
        if location_id and _safe_str(c.get("location_id")) == location_id:
            local_conditions.append({
                "kind": _safe_str(c.get("kind")),
                "severity": _safe_int(c.get("severity"), 0),
                "summary": _safe_str(c.get("summary")),
            })

    return {
        "recent_consequences": [
            {
                "kind": _safe_str(c.get("kind")),
                "summary": _safe_str(c.get("summary")),
                "tick": _safe_int(c.get("tick"), 0),
                "scope": _safe_str(c.get("scope")),
                "location_id": _safe_str(c.get("location_id")),
            }
            for c in recent
        ],
        "local_pressure": local_pressure[:4],
        "local_conditions": local_conditions[:4],
    }


def _resolve_authoritative_runtime_state(data: dict) -> dict:
    """
    Prefer authoritative runtime state from the active session when possible,
    falling back to request payload runtime_state only when needed.
    """
    data = _safe_dict(data)
    session_id = _safe_str(data.get("session_id")).strip()
    if session_id:
        try:
            from app.rpg.session.runtime import ACTIVE_RPG_SESSIONS
            session = _safe_dict(ACTIVE_RPG_SESSIONS.get(session_id))
            runtime_state = _safe_dict(session.get("runtime_state"))
            if runtime_state:
                return runtime_state
        except Exception:
            pass
    return _safe_dict(data.get("runtime_state"))


def _maybe_answer_from_activity(player_text: str, activity: dict, actor_name: str) -> str:
    t = _safe_str(player_text).lower()
    if not activity:
        return ""
    if any(x in t for x in ["what are you doing", "what're you doing", "what are you watching", "what's going on", "why are you here"]):
        summary = _safe_str(activity.get("summary"))
        intent = _safe_str(activity.get("intent"))
        if summary:
            # short grounded answer
            return summary
        if intent:
            return f"{actor_name} says: {intent}"
    return ""


def _ensure_actor_memory_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return ensure_actor_memory_state(_safe_dict(simulation_state))


def _ensure_world_memory_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return ensure_world_memory_state(_safe_dict(simulation_state))


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
        return {"character_visual_identities": {}, "scene_illustrations": [], "image_requests": [], "visual_assets": [], "appearance_profiles": {}, "appearance_events": {}, "defaults": {}}
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
    return {"character_visual_identities": identities, "scene_illustrations": illustrations, "image_requests": requests, "visual_assets": assets, "appearance_profiles": appearance_profiles, "appearance_events": appearance_events, "defaults": defaults}


def _extract_visual_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = ensure_visual_state(_safe_dict(simulation_state))
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    return _safe_visual_state(visual_state)


def _add_content_pack_data(response_dict: Dict[str, Any], simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    response_dict["content_packs"] = list_content_packs(simulation_state)
    response_dict["package_manifest"] = {"package_version": "1.0", "title": "", "description": "", "created_by": ""}
    return response_dict


def _build_speaker_presentation_meta(simulation_state: dict, runtime_state: dict, speaker_name: str) -> dict:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    speaker_name = _safe_str(speaker_name).strip()

    npc_index = _safe_dict(simulation_state.get("npc_index"))
    player_state = _safe_dict(simulation_state.get("player_state"))
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    identities = _safe_dict(visual_state.get("character_visual_identities"))
    party_state = _safe_dict(player_state.get("party_state"))
    companions = _safe_list(party_state.get("companions"))

    matched_npc = {}
    matched_npc_id = ""
    for npc_id, raw in npc_index.items():
        npc = _safe_dict(raw)
        if _safe_str(npc.get("name")).strip().lower() == speaker_name.lower():
            matched_npc = npc
            matched_npc_id = _safe_str(npc_id).strip()
            break

    is_player = speaker_name.lower() == _safe_str(player_state.get("name") or "Player").strip().lower()
    is_companion = any(_safe_str(c.get("name")).strip().lower() == speaker_name.lower() for c in companions if isinstance(c, dict))

    faction_id = _safe_str(matched_npc.get("faction_id")).strip()
    role = _safe_str(matched_npc.get("role")).strip()
    portrait = _safe_str(_safe_dict(identities.get(matched_npc_id)).get("portrait_url")).strip()

    faction_palette = {
        "faction_kings_guard": {"accent": "#6ea8ff", "label": "King's Guard"},
        "faction_rebels": {"accent": "#ff8a6e", "label": "Rebels"},
        "faction_mages": {"accent": "#c68cff", "label": "Mages"},
        "": {"accent": "#a0a0a0", "label": ""},
    }
    palette = _safe_dict(faction_palette.get(faction_id) or faction_palette.get(""))

    return {
        "speaker_name": speaker_name,
        "speaker_id": matched_npc_id,
        "role": role,
        "faction_id": faction_id,
        "faction_label": _safe_str(palette.get("label")).strip(),
        "accent_color": _safe_str(palette.get("accent")).strip() or "#a0a0a0",
        "portrait_url": portrait,
        "is_player": is_player,
        "is_companion": is_companion,
    }


# ---- Scene Presentation ----

@rpg_presentation_bp.post("/api/rpg/presentation/scene")
async def presentation_scene(request: Request):
    data = await _get_json(request)
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
    inspector_overlay_payload = build_player_inspector_overlay_payload(simulation_state, runtime_payload, orchestration_payload, live_provider_payload)
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["runtime"] = runtime_payload
        payload["orchestration"] = orchestration_payload
        payload["live_provider"] = live_provider_payload
        payload["player_overlay"] = inspector_overlay_payload.get("player_overlay", {})
    else:
        payload = {"content": payload, "runtime": runtime_payload, "orchestration": orchestration_payload, "live_provider": live_provider_payload, "player_overlay": inspector_overlay_payload.get("player_overlay", {})}
    response = {"ok": True, "presentation": payload, "character_ui_state": _extract_character_ui_state(simulation_state), "character_inspector_state": _extract_character_inspector_state(simulation_state), "world_inspector_state": _extract_world_inspector_state(simulation_state), "visual_state": _extract_visual_state(simulation_state), "memory_state": _safe_dict(simulation_state.get("memory_state"))}
    # Inject conversation payload
    runtime_state = _safe_dict(data.get("runtime_state"))
    conv_payload = build_conversation_payload(simulation_state, runtime_state)
    response["active_conversations"] = conv_payload.get("active_conversations", [])
    response["recent_conversations"] = conv_payload.get("recent_conversations", [])
    return _jsonify(_add_content_pack_data(response, simulation_state))


# ---- Dialogue Presentation ----

@rpg_presentation_bp.post("/api/rpg/presentation/dialogue")
async def presentation_dialogue(request: Request):
    data = await _get_json(request)
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
    dialogue_ux_payload = build_dialogue_ux_payload(payload, runtime_payload, orchestration_payload)
    inspector_overlay_payload = build_player_inspector_overlay_payload(simulation_state, runtime_payload, orchestration_payload, live_provider_payload)
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["runtime"] = runtime_payload
        payload["orchestration"] = orchestration_payload
        payload["live_provider"] = live_provider_payload
        payload["dialogue_ux"] = dialogue_ux_payload.get("dialogue_ux", {})
        payload["player_overlay"] = inspector_overlay_payload.get("player_overlay", {})
    else:
        payload = {"content": payload, "runtime": runtime_payload, "orchestration": orchestration_payload, "live_provider": live_provider_payload, "dialogue_ux": dialogue_ux_payload.get("dialogue_ux", {}), "player_overlay": inspector_overlay_payload.get("player_overlay", {})}
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)
    actor_ids = []
    speaker = payload.get("speaker") if isinstance(payload, dict) else None
    speaker_id = ""
    actor_name = ""
    if isinstance(speaker, dict):
        speaker_id = _safe_str(speaker.get("actor_id")).strip()
        actor_name = _safe_str(speaker.get("name")).strip()
        if speaker_id:
            actor_ids.append(speaker_id)
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
    primary_actor_id = actor_ids[0] if actor_ids else ""
    player_text = _safe_str(data.get("text") or data.get("message")).strip()

    runtime_state = _resolve_authoritative_runtime_state(data)
    dialogue_activity_context = _build_actor_activity_context(runtime_state, speaker_id or primary_actor_id)
    payload["dialogue_activity_context"] = dialogue_activity_context

    dialogue_consequence_context = _build_recent_consequence_context(
        runtime_state,
        speaker_id or primary_actor_id,
        _safe_str(dialogue_activity_context.get("location_id")),
    )
    payload["dialogue_consequence_context"] = dialogue_consequence_context

    simulation_state = apply_dialogue_memory_hooks(simulation_state, actor_id=primary_actor_id, player_text=player_text)
    dialogue_memory_context = build_dialogue_memory_context(simulation_state, actor_id=primary_actor_id, actor_ids=actor_ids)
    dialogue_memory_context["activity"] = dialogue_activity_context
    dialogue_memory_context["consequences"] = dialogue_consequence_context
    memory_prompt_block = build_llm_memory_prompt_block(dialogue_memory_context)

    grounded_activity_reply = _maybe_answer_from_activity(
        player_text,
        dialogue_activity_context,
        actor_name or speaker_id or "They",
    )
    response = {"ok": True, "presentation": payload, "character_ui_state": _extract_character_ui_state(simulation_state), "character_inspector_state": _extract_character_inspector_state(simulation_state), "world_inspector_state": _extract_world_inspector_state(simulation_state), "visual_state": _extract_visual_state(simulation_state), "memory_state": _safe_dict(simulation_state.get("memory_state")), "dialogue_memory_context": dialogue_memory_context, "llm_memory_prompt_block": memory_prompt_block, "gm_memory_visibility": {"actor_id": primary_actor_id, "actor_memory_count": len(dialogue_memory_context.get("actor_memory", [])), "world_rumor_count": len(dialogue_memory_context.get("world_rumors", []))}}

    if grounded_activity_reply:
        response["grounded_activity_reply"] = grounded_activity_reply

    return _jsonify(_add_content_pack_data(response, simulation_state))


# ---- Speaker Cards ----

@rpg_presentation_bp.post("/api/rpg/presentation/speakers")
async def presentation_speakers(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    scene_state = _safe_dict(data.get("scene_state"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    all_cards = build_speaker_cards(simulation_state, scene_state)
    runtime_payload = build_runtime_presentation_payload(simulation_state)
    orchestration_payload = build_orchestration_presentation_payload(simulation_state)
    live_provider_payload = build_live_provider_presentation_payload(simulation_state)
    inspector_overlay_payload = build_player_inspector_overlay_payload(simulation_state, runtime_payload, orchestration_payload, live_provider_payload)

    all_cards_by_id = {
        _safe_str(card.get("npc_id")): card
        for card in _safe_list(all_cards)
        if _safe_str(card.get("npc_id"))
    }

    session = _safe_dict(data.get("session"))
    _safe_dict(session.get("runtime_state"))
    present_ids = _derive_present_npc_ids(simulation_state, data.get("runtime_state") or {}, setup_payload)
    known_ids = _derive_known_npc_ids(simulation_state, data.get("runtime_state") or {})

    present_character_cards = []
    for npc_id in present_ids:
        card = dict(_safe_dict(all_cards_by_id.get(npc_id)))
        if not card:
            continue
        card["live_state"] = _derive_npc_live_state(npc_id, simulation_state, data.get("runtime_state") or {})
        present_character_cards.append(card)

    known_character_cards = []
    present_set = set(present_ids)
    for npc_id in known_ids:
        if npc_id in present_set:
            continue
        card = dict(_safe_dict(all_cards_by_id.get(npc_id)))
        if not card:
            continue
        card["live_state"] = _derive_npc_live_state(npc_id, simulation_state, data.get("runtime_state") or {})
        known_character_cards.append(card)

    return _jsonify({
        "ok": True,
        "speaker_cards": present_character_cards,
        "character_cards": present_character_cards,
        "present_character_cards": present_character_cards,
        "known_character_cards": known_character_cards,
        "present_npc_ids": present_ids,
        "known_npc_ids": known_ids,
        "runtime": runtime_payload,
        "orchestration": orchestration_payload,
        "live_provider": live_provider_payload,
        "player_overlay": inspector_overlay_payload.get("player_overlay", {})
    })


# ---- Setup Flow ----

@rpg_presentation_bp.post("/setup-flow")
async def presentation_setup_flow(request: Request):
    body = await _get_json(request)
    user_input = body.get("user_input") or {}
    payload = build_setup_flow_payload(user_input)
    return _jsonify({"ok": True, "presentation": payload})


@rpg_presentation_bp.post("/session-bootstrap")
async def presentation_session_bootstrap(request: Request):
    body = await _get_json(request)
    user_input = body.get("user_input") or {}
    setup_payload = build_setup_flow_payload(user_input)
    setup_flow = setup_payload.get("setup_flow") or {}
    response_payload = {"session_bootstrap": {"world_seed": dict(setup_flow.get("world_seed") or {}), "rules": dict(setup_flow.get("rules") or {}), "player_role": (setup_flow.get("selected") or {}).get("player_role", "wanderer"), "tone_tags": list(setup_flow.get("tone_tags") or []), "seed_prompt": (setup_flow.get("selected") or {}).get("seed_prompt", "")}}
    return _jsonify({"ok": True, "presentation": response_payload})


@rpg_presentation_bp.post("/intro-scene")
async def presentation_intro_scene(request: Request):
    body = await _get_json(request)
    session_bootstrap = body.get("session_bootstrap") or {}
    payload = build_intro_scene_payload(session_bootstrap)
    return _jsonify({"ok": True, "presentation": payload})


@rpg_presentation_bp.post("/save-load-ux")
async def presentation_save_load_ux(request: Request):
    body = await _get_json(request)
    save_snapshots = body.get("save_snapshots") or []
    current_tick = body.get("current_tick") or 0
    payload = build_save_load_ux_payload(save_snapshots=save_snapshots, current_tick=current_tick)
    return _jsonify({"ok": True, "presentation": payload})


@rpg_presentation_bp.post("/narrative-recap")
async def presentation_narrative_recap(request: Request):
    body = await _get_json(request)
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
    response = {"ok": True, "presentation": payload, "character_ui_state": _extract_character_ui_state(simulation_state), "character_inspector_state": _extract_character_inspector_state(simulation_state), "world_inspector_state": _extract_world_inspector_state(simulation_state), "visual_state": _extract_visual_state(simulation_state), "memory_state": _safe_dict(simulation_state.get("memory_state"))}
    return _jsonify(_add_content_pack_data(response, simulation_state))


# ---- Character UI ----

@rpg_presentation_bp.post("/api/rpg/character_ui")
async def presentation_character_ui(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    character_ui_state = _extract_character_ui_state(simulation_state)
    return _jsonify({"ok": True, "character_ui_state": character_ui_state})


@rpg_presentation_bp.post("/api/rpg/character_inspector")
async def presentation_character_inspector(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    return _jsonify({"ok": True, "character_inspector_state": _extract_character_inspector_state(simulation_state)})


@rpg_presentation_bp.post("/api/rpg/character_inspector/detail")
async def presentation_character_inspector_detail(request: Request):
    data = await _get_json(request)
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
            return _jsonify({"ok": True, "character": character})
    return _jsonify({"ok": False, "error": "character_not_found", "character": None}, status_code=404)


@rpg_presentation_bp.post("/api/rpg/world_inspector")
async def presentation_world_inspector(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    simulation_state = _ensure_world_inspector_state(simulation_state)
    return _jsonify({"ok": True, "world_inspector_state": _extract_world_inspector_state(simulation_state)})


# ---- Character Portrait ----

@rpg_presentation_bp.post("/api/rpg/character_portrait/request")
async def request_character_portrait(request: Request):
    data = await _get_json(request)
    session_id = str(data.get("session_id") or "").strip()
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_id = _safe_str(data.get("actor_id")).strip()
    style = _safe_str(data.get("style")).strip()
    model = _safe_str(data.get("model")).strip()
    _safe_str(data.get("reason")).strip() or "manual_request"
    prompt_override = _safe_str(data.get("prompt")).strip()

    simulation_state = ensure_player_state(_load_visual_request_simulation_state(session_id, setup_payload))
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
    
    # Also check npcs array in simulation state directly
    npcs = simulation_state.get("npcs") if isinstance(simulation_state, dict) else []
    npcs = npcs if isinstance(npcs, list) else []
    if npcs:
        for npc in npcs:
            if isinstance(npc, dict) and _safe_str(npc.get("id")).strip() == actor_id:
                characters.append(npc)
    
    target = None
    for character in characters:
        if isinstance(character, dict) and _safe_str(character.get("id")).strip() == actor_id:
            target = character
            break
            
    # Fallback: if NPC exists in rpgState.npcs just create a minimal target
    if not target:
        for npc in npcs:
            if isinstance(npc, dict) and _safe_str(npc.get("id")).strip() == actor_id:
                target = npc
                break
    
    if not target:
        print(f"[PORTRAIT DEBUG] Creating dummy target for {actor_id}")
        target = {
            "id": actor_id,
            "name": actor_id.replace("npc_", "").replace("_", " ").title(),
            "description": "",
            "role": "NPC"
        }
    existing_visual = _safe_dict(target.get("visual_identity"))
    portrait_style = _first_non_empty(style, existing_visual.get("style"), "rpg-portrait")
    settings = load_settings()
    visual_settings = _safe_dict(settings.get("rpg_visual"))
    flux_settings = _safe_dict(visual_settings.get("flux_klein"))
    default_visual_model = _safe_str(flux_settings.get("repo_id")).strip() or "black-forest-labs/FLUX.2-klein-4B"
    portrait_model = _first_non_empty(model, existing_visual.get("model"), default_visual_model)
    identity = build_default_character_visual_identity(actor_id=actor_id, name=_safe_str(target.get("name")).strip(), role=_safe_str(target.get("role")).strip(), description=_safe_str(target.get("description")).strip(), personality_summary=_safe_str(_safe_dict(target.get("personality")).get("summary")).strip(), style=portrait_style, model=portrait_model)
    identity.update(existing_visual)
    if prompt_override:
        identity["base_prompt"] = prompt_override
    identity["style"] = portrait_style
    identity["model"] = portrait_model
    prompt_check = validate_visual_prompt(identity.get("base_prompt", ""))
    identity["status"] = "pending" if prompt_check.get("ok") else "blocked"
    current_version = identity.get("version")
    identity["version"] = current_version + 1 if isinstance(current_version, int) and current_version > 0 else 1
    profile_payload = build_default_appearance_profile(actor_id=actor_id, name=_safe_str(target.get("name")).strip(), role=_safe_str(target.get("role")).strip(), description=_safe_str(target.get("description")).strip())
    simulation_state = upsert_appearance_profile(simulation_state, actor_id=actor_id, profile=profile_payload)
    simulation_state = upsert_character_visual_identity(simulation_state, actor_id=actor_id, identity=identity)
    simulation_state = append_appearance_event(simulation_state, actor_id=actor_id, event={"event_id": f"appearance:{actor_id}:{identity['version']}", "reason": "manual_refresh" if prompt_override else "initial", "summary": "Portrait refresh requested", "tick": 0})

    # Remove stale pending/failed requests for this portrait target before enqueuing a fresh one.
    simulation_state = _drop_visual_requests_for_target(
        simulation_state,
        kind="character_portrait",
        target_id=actor_id,
    )

    now_ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    request_id = f"portrait:{actor_id}:{identity['version']}:{_request_nonce()}"
    simulation_state = append_image_request(simulation_state, {"request_id": request_id, "kind": "character_portrait", "target_id": actor_id, "prompt": identity.get("base_prompt", ""), "seed": identity.get("seed"), "style": identity.get("style", ""), "model": identity.get("model", ""), "status": "pending" if prompt_check.get("ok") else "blocked", "attempts": 0, "max_attempts": 3, "error": "", "created_at": now_ts, "updated_at": "", "completed_at": ""})
    persisted = _persist_visual_session(
        session_id,
        simulation_state,
        expected_request_id=request_id,
    )
    print("[RPG][portrait/request]", {
        "request_id": request_id,
        "persisted": persisted,
        "actor_id": actor_id,
    })
    if session_id and not persisted:
        return _jsonify({
            "ok": False,
            "error": "failed_to_persist_visual_request",
            "request_id": request_id,
        }, status_code=500)

    if session_id and request_id:
        try:
            enqueue_visual_job(session_id=session_id, request_id=request_id)
        except Exception as exc:
            return _jsonify({
                "ok": False,
                "error": "failed_to_enqueue_visual_job",
                "detail": _safe_str(exc).strip()[:300],
                "request_id": request_id,
            }, status_code=500)
    return _jsonify({"ok": True, "request_id": request_id, "moderation": {"status": "approved" if prompt_check.get("ok") else "blocked", "reason": _safe_str(prompt_check.get("reason")).strip()}, "visual_state": _extract_visual_state(simulation_state), "character_ui_state": _extract_character_ui_state(simulation_state)})


@rpg_presentation_bp.post("/api/rpg/character_portrait/result")
async def complete_character_portrait(request: Request):
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
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
        return _jsonify({"ok": False, "error": "character_not_found"}, status_code=404)
    if image_url:
        identity["portrait_url"] = image_url
    identity["portrait_asset_id"] = asset_id
    identity["status"] = status
    visual_state_defaults = _safe_dict(_extract_visual_state(simulation_state).get("defaults"))
    if status in {"failed", "blocked"}:
        identity = apply_visual_fallback(identity, visual_state_defaults.get("fallback_portrait_url"))
    simulation_state = upsert_character_visual_identity(simulation_state, actor_id=actor_id, identity=identity)
    simulation_state = _ensure_character_ui_state(simulation_state)
    version = identity.get("version")
    if not isinstance(version, int) or version < 1:
        version = 1
    simulation_state = append_visual_asset(simulation_state, build_visual_asset_record(kind="character_portrait", target_id=actor_id, version=version, seed=identity.get("seed") if isinstance(identity.get("seed"), int) else None, style=_safe_str(identity.get("style")).strip(), model=_safe_str(identity.get("model")).strip(), prompt=_safe_str(identity.get("base_prompt")).strip(), url=_safe_str(identity.get("portrait_url")).strip(), local_path=local_path, status=status, created_from_request_id=request_id, moderation_status=moderation_status, moderation_reason=moderation_reason))
    simulation_state = append_appearance_event(simulation_state, actor_id=actor_id, event={"event_id": f"appearance-result:{actor_id}:{version}", "reason": "manual_refresh", "summary": f"Portrait result recorded ({status})", "tick": 0})
    _persist_visual_session(session_id, simulation_state)
    return _jsonify({"ok": True, "visual_state": _extract_visual_state(simulation_state), "character_ui_state": _extract_character_ui_state(simulation_state)})


# ---- Scene Illustration ----

@rpg_presentation_bp.post("/api/rpg/scene_illustration/request")
async def request_scene_illustration(request: Request):
    data = await _get_json(request)
    try:
        session_id = str(data.get("session_id") or "").strip()
        setup_payload = _safe_dict(data.get("setup_payload"))
        scene_id = _safe_str(data.get("scene_id")).strip()
        event_id = _safe_str(data.get("event_id")).strip()
        title = _safe_str(data.get("title")).strip()
        prompt = _safe_str(data.get("prompt")).strip()
        style = _safe_str(data.get("style")).strip()
        model = _safe_str(data.get("model")).strip()

        simulation_state = ensure_player_state(_load_visual_request_simulation_state(session_id, setup_payload))
        simulation_state = ensure_player_party(simulation_state)
        simulation_state = ensure_personality_state(simulation_state)
        simulation_state = ensure_visual_state(simulation_state)
        visual_state = _extract_visual_state(simulation_state)
        defaults = _safe_dict(visual_state.get("defaults"))
        scene_style = _first_non_empty(style, defaults.get("scene_style"), "rpg-scene")
        settings = load_settings()
        visual_settings = _safe_dict(settings.get("rpg_visual"))
        flux_settings = _safe_dict(visual_settings.get("flux_klein"))
        default_visual_model = _safe_str(flux_settings.get("repo_id")).strip() or "black-forest-labs/FLUX.2-klein-4B"
        scene_model = _first_non_empty(model, defaults.get("model"), default_visual_model)
        resolved_target = _first_non_empty(event_id, scene_id, title, "scene")
        if ":" not in resolved_target:
            resolved_target = f"scene:manual:{_request_nonce()}"

        if not prompt:
            prompt = f"Scene illustration of {resolved_target or 'the current scene'}"

        prompt = build_grounded_scene_illustration_prompt(
            simulation_state,
            scene_id=scene_id,
            event_id=event_id,
            title=title,
            prompt=prompt,
        )
        print("[IMG PROMPT]", prompt)
        seed = data.get("seed")
        if not isinstance(seed, int):
            seed = stable_visual_seed_from_text(f"{scene_id}|{event_id}|{title}|{prompt}|{scene_style}|{scene_model}")
        prompt_check = validate_visual_prompt(prompt)

        # Remove stale pending/failed requests for this scene target before enqueuing a fresh one.
        simulation_state = _drop_visual_requests_for_target(
            simulation_state,
            kind="scene_illustration",
            target_id=resolved_target,
        )

        # If a completed asset already exists for this exact logical target/prompt/style/model/seed,
        # return it instead of enqueueing/generating again.
        current_visual_state = _extract_visual_state(simulation_state)
        existing_illustrations = _safe_list(current_visual_state.get("scene_illustrations"))
        for item in reversed(existing_illustrations):
            row = _safe_dict(item)
            if (
                _safe_str(row.get("scene_id")).strip() == resolved_target
                and _safe_str(row.get("prompt")).strip() == prompt
                and _safe_str(row.get("style")).strip() == scene_style
                and _safe_str(row.get("model")).strip() == scene_model
                and row.get("seed") == seed
                and _safe_str(row.get("status")).strip() == "complete"
                and _safe_str(row.get("image_url")).strip()
            ):
                return _jsonify({
                    "ok": True,
                    "request_id": _safe_str(row.get("event_id")).strip() or "",
                    "moderation": {
                        "status": "approved" if prompt_check.get("ok") else "blocked",
                        "reason": _safe_str(prompt_check.get("reason")).strip(),
                    },
                    "visual_state": current_visual_state,
                    "reused_existing": True,
                })

        now_ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        request_id = f"scene:{resolved_target}:{seed}:{_request_nonce()}"
        simulation_state = append_image_request(simulation_state, {"request_id": request_id, "kind": "scene_illustration", "target_id": resolved_target, "prompt": prompt, "seed": seed, "style": scene_style, "model": scene_model, "status": "pending" if prompt_check.get("ok") else "blocked", "attempts": 0, "max_attempts": 3, "error": "", "created_at": now_ts, "updated_at": "", "completed_at": ""})
        persisted = _persist_visual_session(
            session_id,
            simulation_state,
            expected_request_id=request_id,
        )
        print("[RPG][scene/request]", {
            "session_id": session_id,
            "request_id": request_id,
            "persisted": persisted,
            "resolved_target": resolved_target,
            "prompt_preview": prompt[:240],
        })
        if session_id and not persisted:
            return _jsonify({
                "ok": False,
                "error": "failed_to_persist_visual_request",
                "request_id": request_id,
            }, status_code=500)

        if session_id and request_id:
            try:
                enqueue_visual_job(session_id=session_id, request_id=request_id)
            except Exception as exc:
                return _jsonify({
                    "ok": False,
                    "error": "failed_to_enqueue_visual_job",
                    "detail": _safe_str(exc).strip()[:300],
                    "request_id": request_id,
                }, status_code=500)
        return _jsonify({"ok": True, "request_id": request_id, "moderation": {"status": "approved" if prompt_check.get("ok") else "blocked", "reason": _safe_str(prompt_check.get("reason")).strip()}, "visual_state": _extract_visual_state(simulation_state)})
    except Exception as exc:
        print("[RPG][scene/request][ERROR]", {
            "session_id": _safe_str(data.get("session_id")).strip(),
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        return _jsonify({"ok": False, "error": str(exc)}, status_code=500)


@rpg_presentation_bp.post("/api/rpg/scene_illustration/result")
async def complete_scene_illustration(request: Request):
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
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
    illustration_payload = {"scene_id": scene_id, "event_id": event_id, "title": title, "image_url": image_url, "asset_id": asset_id, "seed": seed, "style": style, "prompt": prompt, "model": model, "status": status}
    if status in {"failed", "blocked"}:
        illustration_payload = apply_visual_fallback(illustration_payload, visual_defaults.get("fallback_scene_url"))
    simulation_state = append_scene_illustration(simulation_state, illustration_payload)
    simulation_state = append_visual_asset(simulation_state, build_visual_asset_record(kind="scene_illustration", target_id=_first_non_empty(event_id, scene_id, title, "scene"), version=1, seed=seed, style=style, model=model, prompt=prompt, url=_safe_str(illustration_payload.get("image_url")).strip(), local_path=local_path, status=status, created_from_request_id=request_id, moderation_status=moderation_status, moderation_reason=moderation_reason))
    _persist_visual_session(session_id, simulation_state)
    return _jsonify({"ok": True, "visual_state": _extract_visual_state(simulation_state)})


# ---- Visual Assets ----

@rpg_presentation_bp.post("/api/rpg/visual_assets")
async def presentation_visual_assets(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    visual_state = _extract_visual_state(simulation_state)
    return _jsonify({"ok": True, "visual_assets": visual_state.get("visual_assets", []), "appearance_profiles": visual_state.get("appearance_profiles", {}), "appearance_events": visual_state.get("appearance_events", {})})


# ---- Visual Processing ----

@rpg_presentation_bp.post("/api/rpg/visual/process_requests")
async def process_rpg_visual_requests(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    limit = data.get("limit") if isinstance(data.get("limit"), int) else 8
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = process_pending_image_requests(simulation_state, limit=limit)
    if isinstance(setup_payload, dict):
        setup_payload["simulation_state"] = simulation_state
    return _jsonify({"ok": True, "simulation_state": simulation_state, "visual_state": _extract_visual_state(simulation_state)})


# ---- Character Card Import/Export ----

@rpg_presentation_bp.post("/api/rpg/character/import")
async def import_character_card(request: Request):
    data = await _get_json(request)
    card = _safe_dict(data.get("card"))
    imported = import_external_character_card(card)
    return _jsonify({"ok": True, "imported": imported})


@rpg_presentation_bp.post("/api/rpg/character/export")
async def export_character_card(request: Request):
    data = await _get_json(request)
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
            return _jsonify({"ok": True, "card": export_canonical_character_card(character)})
    return _jsonify({"ok": False, "error": "character_not_found"}, status_code=404)


# ---- GM Trace ----

@rpg_presentation_bp.post("/api/rpg/gm_trace")
async def presentation_gm_trace(request: Request):
    data = await _get_json(request)
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
    visual_assets = [item for item in _safe_list(visual_state.get("visual_assets")) if isinstance(item, dict) and _safe_str(item.get("target_id")).strip() == actor_id]
    image_requests = [item for item in _safe_list(visual_state.get("image_requests")) if isinstance(item, dict) and _safe_str(item.get("target_id")).strip() == actor_id]
    return _jsonify({"ok": True, "trace": {"character": selected_character, "inspector": selected_inspector, "appearance_events": appearance_events, "visual_assets": visual_assets, "image_requests": image_requests}})


# ---- Package Export/Import ----

@rpg_presentation_bp.post("/api/rpg/package/export")
async def export_rpg_package(request: Request):
    data = await _get_json(request)
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
    package_data = export_session_package(simulation_state, title=title, description=description, created_by=created_by)
    return _jsonify({"ok": True, "package": package_data})


@rpg_presentation_bp.post("/api/rpg/package/import")
async def import_rpg_package(request: Request):
    data = await _get_json(request)
    package_data = _safe_dict(data.get("package"))
    imported = import_session_package(package_data)
    return _jsonify({"ok": True, "imported": imported})


# ---- Content Packs ----

@rpg_presentation_bp.post("/api/rpg/packs/list")
async def list_rpg_packs(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)
    return _jsonify({"ok": True, "packs": list_content_packs(simulation_state)})


@rpg_presentation_bp.post("/api/rpg/packs/preview")
async def preview_rpg_pack(request: Request):
    data = await _get_json(request)
    pack = _safe_dict(data.get("pack"))
    preview = build_pack_application_preview(pack)
    return _jsonify({"ok": True, "preview": preview})


@rpg_presentation_bp.post("/api/rpg/packs/apply")
async def apply_rpg_pack(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    pack = _safe_dict(data.get("pack"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)
    simulation_state = apply_content_pack(simulation_state, pack)
    return _jsonify({"ok": True, "packs": list_content_packs(simulation_state), "visual_state": _extract_visual_state(simulation_state)})


@rpg_presentation_bp.post("/api/rpg/packs/bootstrap")
async def bootstrap_rpg_pack(request: Request):
    data = await _get_json(request)
    pack = _safe_dict(data.get("pack"))
    bootstrap = build_pack_bootstrap_payload(pack)
    return _jsonify({"ok": True, "bootstrap": bootstrap})


@rpg_presentation_bp.post("/api/rpg/packs/start")
async def start_rpg_from_pack(request: Request):
    data = await _get_json(request)
    pack = _safe_dict(data.get("pack"))
    bootstrap = build_pack_bootstrap_payload(pack)
    simulation_state = {"presentation_state": {"visual_state": {"defaults": _safe_dict(bootstrap.get("visual_defaults"))}}, "world_state": {"scenario_title": _safe_str(bootstrap.get("title")).strip(), "scenario_summary": _safe_str(bootstrap.get("summary")).strip(), "opening": _safe_str(bootstrap.get("opening")).strip(), "world_seed": _safe_dict(bootstrap.get("world_seed"))}}
    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    return _jsonify({"ok": True, "setup_payload": {"simulation_state": simulation_state, "bootstrap": bootstrap}})


# ---- Creator Pack Authoring ----

@rpg_presentation_bp.post("/api/rpg/creator/pack/validate")
async def validate_rpg_pack_draft(request: Request):
    data = await _get_json(request)
    draft = _safe_dict(data.get("draft"))
    validation = validate_pack_draft(draft)
    return _jsonify({"ok": True, "validation": validation})


@rpg_presentation_bp.post("/api/rpg/creator/pack/preview")
async def preview_rpg_pack_draft(request: Request):
    data = await _get_json(request)
    draft = _safe_dict(data.get("draft"))
    preview = build_pack_draft_preview(draft)
    return _jsonify({"ok": True, "preview": preview})


@rpg_presentation_bp.post("/api/rpg/creator/pack/export")
async def export_rpg_pack_draft(request: Request):
    data = await _get_json(request)
    draft = _safe_dict(data.get("draft"))
    exported = build_pack_draft_export(draft)
    return _jsonify({"ok": True, "pack": exported})


# ---- Campaign Templates ----

@rpg_presentation_bp.post("/api/rpg/templates/build")
async def build_rpg_template(request: Request):
    data = await _get_json(request)
    template_id = _safe_str(data.get("template_id")).strip() or "template:default"
    title = _safe_str(data.get("title")).strip() or "Campaign Template"
    description = _safe_str(data.get("description")).strip()
    bootstrap = _safe_dict(data.get("bootstrap"))
    template = build_campaign_template(template_id=template_id, title=title, description=description, bootstrap=bootstrap)
    return _jsonify({"ok": True, "template": template})


@rpg_presentation_bp.post("/api/rpg/templates/start")
async def start_rpg_template(request: Request):
    data = await _get_json(request)
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
    return _jsonify({"ok": True, "start": start_payload})


@rpg_presentation_bp.post("/api/rpg/templates/list")
async def list_rpg_templates(request: Request):
    data = await _get_json(request)
    templates = _safe_list(data.get("templates"))
    return _jsonify({"ok": True, "templates": list_campaign_templates(templates)})


# ---- Wizard ----

@rpg_presentation_bp.post("/api/rpg/wizard/preview")
async def preview_rpg_wizard(request: Request):
    data = await _get_json(request)
    wizard_state = normalize_wizard_state(data.get("wizard_state"))
    return _jsonify({"ok": True, "preview": build_wizard_preview_payload(wizard_state)})


@rpg_presentation_bp.post("/api/rpg/wizard/build")
async def build_rpg_wizard_setup(request: Request):
    data = await _get_json(request)
    wizard_state = normalize_wizard_state(data.get("wizard_state"))
    setup_payload = build_wizard_setup_payload(wizard_state)
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    setup_payload["simulation_state"] = simulation_state
    return _jsonify({"ok": True, "setup_payload": setup_payload})


# ---- Session Lifecycle ----

_RPG_SESSION_ROOT_STATE: Dict[str, Any] = {"sessions": []}


@rpg_presentation_bp.post("/api/rpg/session/save")
async def save_rpg_session(request: Request):
    global _RPG_SESSION_ROOT_STATE
    data = await _get_json(request)
    session = _safe_dict(data.get("session"))
    manifest = _safe_dict(session.get("manifest"))

    save_label = _safe_str(data.get("save_label")).strip()
    branch_note = _safe_str(data.get("branch_note")).strip()
    branch_parent_session_id = _safe_str(data.get("branch_parent_session_id")).strip()

    story_policy = _safe_dict(_safe_dict(session.get("runtime_state")).get("story_policy"))
    if not story_policy:
        story_policy = {
            "save_load_stable": True,
            "strict_replay": False,
            "record_replay_artifacts": False,
        }
        session.setdefault("runtime_state", {})["story_policy"] = story_policy

    manifest["save_kind"] = "manual"
    if save_label:
        manifest["save_label"] = save_label
    if branch_note:
        manifest["branch_note"] = branch_note
    if branch_parent_session_id:
        manifest["branch_parent_session_id"] = branch_parent_session_id
    session["manifest"] = manifest

    _RPG_SESSION_ROOT_STATE = save_session(_RPG_SESSION_ROOT_STATE, session)
    save_session_to_disk(session)
    sessions = list_sessions(_RPG_SESSION_ROOT_STATE)
    for s in sessions:
        runtime_state = _safe_dict(s.get("runtime_state"))
        narration_artifacts = _safe_list(runtime_state.get("narration_artifacts"))
        s["narration_artifacts"] = narration_artifacts[-12:]
        s["latest_narration_by_turn"] = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
        s["narration_jobs"] = _safe_list(runtime_state.get("narration_jobs"))[-12:]
        s["narration_jobs_by_turn"] = _safe_dict(runtime_state.get("narration_jobs_by_turn"))
    return _jsonify({"ok": True, "sessions": sessions})


@rpg_presentation_bp.post("/api/rpg/session/list")
async def list_rpg_sessions(request: Request):
    global _RPG_SESSION_ROOT_STATE
    _RPG_SESSION_ROOT_STATE = ensure_session_registry(_RPG_SESSION_ROOT_STATE)
    disk_sessions = list_sessions_from_disk()
    migrated_sessions = [migrate_session_payload(s) for s in disk_sessions] if disk_sessions else []
    return _jsonify({"ok": True, "sessions": migrated_sessions or list_sessions(_RPG_SESSION_ROOT_STATE)})


@rpg_presentation_bp.post("/api/rpg/session/load")
async def load_rpg_session(request: Request):
    global _RPG_SESSION_ROOT_STATE
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    session = migrate_session_payload(load_session_from_disk(session_id)) or get_session(_RPG_SESSION_ROOT_STATE, session_id)
    if not session:
        return _jsonify({"ok": False, "error": "session_not_found"}, status_code=404)
    return _jsonify({"ok": True, "session": session})


@rpg_presentation_bp.post("/api/rpg/session/archive")
async def archive_rpg_session(request: Request):
    global _RPG_SESSION_ROOT_STATE
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    _RPG_SESSION_ROOT_STATE = archive_session(_RPG_SESSION_ROOT_STATE, session_id)
    return _jsonify({"ok": True, "sessions": list_sessions(_RPG_SESSION_ROOT_STATE)})


# ---- Memory ----

@rpg_presentation_bp.post("/api/rpg/memory/get")
async def get_rpg_memory(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    return _jsonify({"ok": True, "memory_state": _safe_dict(simulation_state.get("memory_state"))})


@rpg_presentation_bp.post("/api/rpg/memory/add")
async def add_rpg_memory(request: Request):
    data = await _get_json(request)
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
    return _jsonify({"ok": True, "memory_state": _safe_dict(simulation_state.get("memory_state"))})


# ---- Memory Dialogue Context ----

@rpg_presentation_bp.post("/api/rpg/memory/dialogue_context")
async def get_rpg_memory_dialogue_context(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    actor_ids = data.get("actor_ids") if isinstance(data.get("actor_ids"), list) else []
    actor_ids = [_safe_str(aid).strip() for aid in actor_ids if _safe_str(aid).strip()][:6]
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)
    memory_context = build_dialogue_memory_context(simulation_state, actor_ids=actor_ids)
    memory_prompt_block = build_llm_memory_prompt_block(memory_context)
    return _jsonify({"ok": True, "dialogue_memory_context": memory_context, "llm_memory_prompt_block": memory_prompt_block})


# ---- Memory Decay ----

@rpg_presentation_bp.post("/api/rpg/memory/decay")
async def memory_decay(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    simulation_state = decay_memory_state(simulation_state)
    setup_payload["simulation_state"] = simulation_state
    return _jsonify({"ok": True, "setup_payload": setup_payload})


# ---- Session Package ----

@rpg_presentation_bp.post("/api/rpg/session/export_package")
async def export_session_as_package_route(request: Request):
    data = await _get_json(request)
    session = _safe_dict(data.get("session"))
    if not session:
        session_id = _safe_str(data.get("session_id")).strip()
        if session_id:
            session = load_session_from_disk(session_id) or get_session(_RPG_SESSION_ROOT_STATE, session_id)
    if not session:
        return _jsonify({"ok": False, "error": "session_not_found"}, status_code=404)
    package_payload = export_session_as_package(session)
    return _jsonify({"ok": True, "package": package_payload})


@rpg_presentation_bp.post("/api/rpg/session/import_package")
async def import_package_as_session(request: Request):
    global _RPG_SESSION_ROOT_STATE
    data = await _get_json(request)
    package_payload = _safe_dict(data.get("package"))
    result = import_session_from_package(package_payload)
    if not result.get("ok"):
        return _jsonify(result, status_code=400)
    session = _safe_dict(result.get("session"))
    _RPG_SESSION_ROOT_STATE = save_session(_RPG_SESSION_ROOT_STATE, session)
    save_session_to_disk(session)
    return _jsonify(result)


# ---- Visual Queue ----

@rpg_presentation_bp.post("/api/rpg/visual/queue/enqueue")
async def queue_visual_job_route(request: Request):
    payload = await _get_json(request)
    session_id = str(payload.get("session_id") or "").strip()
    request_id = str(payload.get("request_id") or "").strip()
    if not session_id or not request_id:
        return _jsonify({"ok": False, "error": "session_id_and_request_id_required"}, status_code=400)
    job = enqueue_visual_job(session_id=session_id, request_id=request_id)
    return _jsonify({"ok": True, "job": job})


@rpg_presentation_bp.post("/api/rpg/visual/queue/run_once")
async def run_visual_queue_once_route(request: Request):
    payload = await _get_json(request)
    lease_seconds = int(payload.get("lease_seconds") or 300)
    result = run_one_queued_job(lease_seconds=lease_seconds)
    code = 200 if result.get("ok") else 500
    return _jsonify(result, status_code=code)


@rpg_presentation_bp.get("/api/rpg/visual/queue/stats")
async def visual_queue_stats_route():
    return _jsonify({"ok": True, "stats": {"jobs": list_visual_jobs()}, "jobs": list_visual_jobs()})


@rpg_presentation_bp.post("/api/rpg/visual/queue/prune")
async def prune_visual_queue_route(request: Request):
    payload = await _get_json(request)
    keep_last = int(payload.get("keep_last") or 200)
    result = prune_completed_visual_jobs(keep_last=keep_last)
    return _jsonify({"ok": True, "result": result, "jobs": list_visual_jobs()})


@rpg_presentation_bp.post("/api/rpg/visual/queue/normalize")
async def normalize_visual_queue_route(request: Request):
    result = normalize_visual_queue()
    return _jsonify({"ok": True, "total": result.get("total", 0), "jobs": result.get("jobs", [])})


@rpg_presentation_bp.post("/api/rpg/visual/queue/run_one")
async def run_one_queued_job_route(request: Request):
    payload = await _get_json(request)
    lease_seconds = int(payload.get("lease_seconds") or 300)
    try:
        result = run_one_queued_job(lease_seconds=lease_seconds)
    except Exception as exc:
        print("[RPG][visual/run_one][ERROR]", {
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        return _jsonify({
            "ok": False,
            "processed": False,
            "error": str(exc) or "run_one_failed",
        }, status_code=200)

    if not result.get("ok"):
        if isinstance(result.get("provider_result"), object) and not isinstance(result.get("provider_result"), dict):
            result["provider_result"] = {
                "error": str(result.get("provider_result")),
            }
        print("[RPG][visual/run_one][RESULT]", result)
        return _jsonify(result, status_code=200)

    # Persist preview/run_one completions back into the live session so the UI
    # can see them through /api/rpg/session/get.
    try:
        if result.get("ok") and result.get("processed") and result.get("request_status") == "complete":
            session_id = str(result.get("session_id") or "").strip()
            request_id = str(result.get("request_id") or "").strip()
            asset_id = str(result.get("asset_id") or "").strip()
            image_url = str(result.get("image_url") or "").strip()
            local_path = str(result.get("local_path") or "").strip()
            kind = str(result.get("kind") or "").strip()
            target_id = str(result.get("target_id") or "").strip()
            prompt = str(result.get("prompt") or "").strip()
            style = str(result.get("style") or "").strip()
            model = str(result.get("model") or "").strip()
            seed = result.get("seed")
            version = result.get("version")

            session = load_runtime_session(session_id)
            if session:
                simulation_state = dict(session.get("simulation_state") or {})

                if not kind:
                    kind = "scene_illustration"
                if not target_id:
                    target_id = "scene"
                if not prompt:
                    prompt = request_id
                if not style:
                    style = "rpg-scene"
                if not model:
                    model = "default"

                simulation_state = append_visual_asset(
                    simulation_state,
                    {
                        "kind": kind,
                        "target_id": target_id,
                        "version": version,
                        "seed": seed,
                        "style": style,
                        "model": model,
                        "prompt": prompt,
                        "url": image_url,
                        "local_path": local_path,
                        "status": "complete",
                        "asset_id": asset_id,
                        "created_from_request_id": request_id,
                    },
                )

                simulation_state = mark_image_request_complete(
                    simulation_state,
                    request_id=request_id,
                    asset_id=asset_id,
                    image_url=image_url,
                    local_path=local_path,
                )

                completed_request = {
                    "request_id": request_id,
                    "kind": kind,
                    "target_id": target_id,
                    "prompt": prompt,
                    "style": style,
                    "model": model,
                    "seed": seed,
                    "version": version,
                }

                if kind == "character_portrait":
                    simulation_state = _complete_character_portrait(
                        simulation_state, request=completed_request, asset_id=asset_id, image_url=image_url, local_path=local_path, status="complete"
                    )
                else:
                    simulation_state = _complete_scene_illustration(
                        simulation_state, request=completed_request, asset_id=asset_id, image_url=image_url, local_path=local_path, status="complete"
                    )

                # Remove the completed request from the pending queue so repeat clicks
                # do not cause duplicate generations for the same work item.
                simulation_state = update_image_request(
                    simulation_state,
                    request_id=request_id,
                    patch={"status": "complete", "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z", "completed_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z"},
                )

                session["simulation_state"] = simulation_state
                save_runtime_session(session)
    except Exception as exc:
        print("[RPG][visual/run_one][PERSIST_ERROR]", {
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        result["session_persist_error"] = str(exc)

    return _jsonify(result, status_code=200)


@rpg_presentation_bp.get("/api/rpg/visual/provider/settings")
async def get_visual_provider_settings_route():
    settings = load_settings()
    visual = _safe_dict(settings.get("rpg_visual"))
    return _jsonify({
        "ok": True,
        "settings": visual,
        "enabled": bool(visual.get("enabled", False)),
        "provider": _safe_str(visual.get("provider")).strip() or "mock",
        "loaded_provider": get_loaded_image_provider_name() or "",
        "provider_loaded": is_image_provider_loaded(),
    })


@rpg_presentation_bp.post("/api/rpg/visual/provider/settings")
async def update_visual_provider_settings_route(request: Request):
    payload = await _get_json(request)
    settings = load_settings()
    visual = _safe_dict(settings.get("rpg_visual"))
    flux = _safe_dict(visual.get("flux_klein"))

    if "enabled" in payload:
        visual["enabled"] = bool(payload.get("enabled"))
    if payload.get("provider") is not None:
        visual["provider"] = _safe_str(payload.get("provider")).strip() or "mock"
    if payload.get("auto_unload_on_disable") is not None:
        visual["auto_unload_on_disable"] = bool(payload.get("auto_unload_on_disable"))

    incoming_flux = _safe_dict(payload.get("flux_klein"))
    if incoming_flux:
        flux.update(incoming_flux)
    visual["flux_klein"] = flux
    settings["rpg_visual"] = visual
    save_settings(settings)

    if not bool(visual.get("enabled", False)):
        unload_image_provider_cache()

    return _jsonify({"ok": True, "settings": visual})


@rpg_presentation_bp.post("/api/rpg/visual/download_flux_klein")
async def download_flux_klein_route(_request: Request):
    result = download_flux_klein_model()
    code = 200 if result.get("ok") else 500
    return _jsonify(result, status_code=code)


@rpg_presentation_bp.get("/api/rpg/visual/download_flux_klein")
async def download_flux_klein_status_route():
    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))
    flux = _safe_dict(image_cfg.get("flux_klein"))
    local_dir = _safe_str(flux.get("local_dir")).strip()
    if not local_dir:
        from app.image.downloads import resolve_flux_local_dir_from_settings
        local_dir = resolve_flux_local_dir_from_settings(settings)
    status = get_flux_local_model_status(local_dir)
    return _jsonify({
        "ok": True,
        "provider": "flux_klein",
        "local_dir": local_dir,
        "local_status": status,
    })


@rpg_presentation_bp.post("/api/rpg/visual/provider/download")
async def download_visual_provider_model_route(request: Request):
    payload = await _get_json(request)
    provider = _safe_str(payload.get("provider")).strip().lower() or "flux_klein"
    if provider != "flux_klein":
        return _jsonify({"ok": False, "error": "unsupported_provider"}, status_code=400)
    result = download_flux_klein_model()
    code = 200 if result.get("ok") else 500
    return _jsonify(result, status_code=code)


@rpg_presentation_bp.post("/api/rpg/visual/provider/load")
async def load_visual_provider_route(request: Request):
    payload = await _get_json(request)
    provider = _safe_str(payload.get("provider")).strip().lower() or "flux_klein"
    image_result = load_image_provider(provider)
    return _jsonify({
        "ok": bool(image_result.get("ok")),
        "enabled": True,
        "provider": provider,
        "settings": get_image_settings_payload().get("settings", {}),
    })


@rpg_presentation_bp.post("/api/rpg/visual/provider/unload")
async def unload_visual_provider_route(request: Request):
    payload = await _get_json(request)
    provider = _safe_str(payload.get("provider")).strip().lower()
    if not provider:
        settings_payload = get_image_settings_payload()
        settings = _safe_dict(settings_payload.get("settings"))
        provider = _safe_str(settings.get("provider")).strip().lower() or "flux_klein"
    unload_image_provider(provider)
    image_settings = get_image_settings_payload().get("settings", {})
    return _jsonify({"ok": True, "enabled": False, "provider": provider, "settings": image_settings})


@rpg_presentation_bp.get("/api/rpg/visual/provider/status")
async def visual_provider_status_route(request: Request):
    settings = load_settings()
    visual = dict(settings.get("rpg_visual") or {})
    selected_provider = (
        visual.get("visual_provider")
        or visual.get("provider")
        or visual.get("image_provider")
        or ("disabled" if not visual.get("enabled", True) else "flux_klein")
    )
    payload = get_visual_provider_status_payload()
    payload.update(
        {
            "ok": True,
            "enabled": bool(visual.get("enabled", True)),
            "selected_provider": str(selected_provider),
            "runtime_validation": validate_visual_runtime(str(selected_provider)),
        }
    )
    return _jsonify(payload)


@rpg_presentation_bp.post("/api/rpg/visual/provider/preload")
async def preload_visual_provider_route(request: Request):
    data = await request.json() if request.method else {}
    force_reload = bool((data or {}).get("force_reload", False))
    provider = preload_image_provider(force_reload=force_reload)
    payload = get_visual_provider_status_payload()
    payload.update(
        {
            "ok": True,
            "provider": str(getattr(provider, "provider_name", "") or ""),
        }
    )
    return _jsonify(payload)


@rpg_presentation_bp.post("/api/rpg/visual/provider/switch")
async def switch_visual_provider_route(request: Request):
    data = await request.json()
    provider_key = str((data or {}).get("provider") or "").strip().lower()
    enabled = bool((data or {}).get("enabled", True))
    force_reload = bool((data or {}).get("force_reload", True))

    settings = load_settings()
    visual = dict(settings.get("rpg_visual") or {})
    visual["enabled"] = enabled
    if provider_key:
        visual["visual_provider"] = provider_key
        visual["provider"] = provider_key
        visual["image_provider"] = provider_key
    settings["rpg_visual"] = visual
    save_settings(settings)

    selected_key, provider = switch_image_provider_runtime(
        provider_key=provider_key,
        enabled=enabled,
        provider_config=visual,
        force_reload=force_reload,
    )
    payload = get_visual_provider_status_payload()
    payload.update(
        {
            "ok": True,
            "enabled": enabled,
            "selected_provider": selected_key,
            "provider": str(getattr(provider, "provider_name", "") or ""),
        }
    )
    return _jsonify(payload)


# ---- Asset Cleanup ----

@rpg_presentation_bp.post("/api/rpg/visual/assets/cleanup")
async def cleanup_visual_assets_route(request: Request):
    payload = await _get_json(request)
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return _jsonify({"ok": False, "error": "session_id_required"}, status_code=400)
    session_data = load_session_from_disk(session_id) or {}
    simulation_state = session_data.get("simulation_state") or {}
    result = cleanup_unused_assets(simulation_state)
    session_data["simulation_state"] = result["simulation_state"]
    save_session_to_disk(session_data)
    return _jsonify({"ok": True, "deleted_asset_ids": result["deleted_asset_ids"], "deleted_files": result["deleted_files"]})


# ---- Visual Inspector ----

@rpg_presentation_bp.post("/api/rpg/visual/inspector")
async def visual_inspector(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    try:
        queue_jobs = list_visual_jobs()
    except Exception:
        queue_jobs = []
    try:
        asset_manifest = get_asset_manifest()
    except Exception:
        asset_manifest = {"assets": {}}
    payload = build_visual_inspector_payload(simulation_state, queue_jobs=queue_jobs, asset_manifest=asset_manifest)
    return _jsonify({"ok": True, "visual_inspector": payload})


# ---- Memory Inspector ----

@rpg_presentation_bp.post("/api/rpg/memory/inspector")
async def memory_inspector(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    payload = build_memory_inspector_payload(simulation_state)
    return _jsonify({"ok": True, "memory_inspector": payload})


# ---- GM Tooling ----

@rpg_presentation_bp.post("/api/rpg/gm/tooling")
async def gm_tooling(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    try:
        queue_jobs = list_visual_jobs()
    except Exception:
        queue_jobs = []
    try:
        asset_manifest = get_asset_manifest()
    except Exception:
        asset_manifest = {"assets": {}}
    payload = build_gm_tooling_payload(simulation_state, queue_jobs=queue_jobs, asset_manifest=asset_manifest)
    return _jsonify({"ok": True, "gm_tooling": payload})


# ---- Memory Reinforce ----

@rpg_presentation_bp.post("/api/rpg/memory/reinforce")
async def reinforce_memory(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    actor_id = _safe_str(data.get("actor_id")).strip()
    text = _safe_str(data.get("text")).strip()
    amount = float(data.get("amount") or 0.2)
    simulation_state = reinforce_actor_memory(simulation_state, actor_id=actor_id, text=text, amount=amount)
    setup_payload["simulation_state"] = simulation_state
    return _jsonify({"ok": True, "setup_payload": setup_payload, "actor_id": actor_id, "text": text})


# ---- Integrity Inspect ----

@rpg_presentation_bp.post("/api/rpg/integrity/inspect")
async def integrity_inspect(request: Request):
    data = await _get_json(request)
    session = _safe_dict(data.get("session"))
    package_payload = _safe_dict(data.get("package"))
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    session_result = validate_session_integrity(session) if session else {"ok": True, "errors": [], "warnings": [], "counts": {}}
    package_result = validate_package_integrity(package_payload) if package_payload else {"ok": True, "errors": [], "warnings": [], "counts": {}}
    simulation_result = validate_simulation_state(simulation_state)
    visual_result = validate_visual_state(simulation_state)
    memory_result = validate_memory_state(simulation_state)
    return _jsonify({"ok": True, "integrity": {"session": session_result, "package": package_result, "simulation": simulation_result, "visual": visual_result, "memory": memory_result}})