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

# ruff: noqa: F401

from datetime import datetime
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

from app.image.downloads import download_flux_klein_model, get_flux_local_model_status
from app.image.lifecycle import load_image_provider, unload_image_provider
from app.image.settings_api import get_image_settings_payload
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
    apply_visual_fallback,
    build_visual_asset_record,
    build_default_appearance_profile,
    build_default_character_visual_identity,
    ensure_visual_state,
    mark_image_request_complete,
    normalize_visual_status,
    stable_visual_seed_from_text,
    update_image_request,
    upsert_appearance_profile,
    upsert_character_visual_identity,
    validate_visual_prompt,
)

# Phase 15.0 — Durable persistence
from app.rpg.session.durable_store import (
    list_sessions_from_disk,
    load_session_from_disk,
    save_session_to_disk,
)
from app.rpg.session.migrations import migrate_session_payload
from app.rpg.session.runtime import (
    load_runtime_session,
    save_runtime_session,
)

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
    unload_image_provider_cache,
)
from app.rpg.visual.queue_runner import run_one_queued_job
from app.rpg.visual.runtime_status import validate_visual_runtime

# Phase 12.10 — Visual worker executor
from app.rpg.visual.worker import (
    _complete_character_portrait,
    _complete_scene_illustration,
    process_pending_image_requests,
)
from app.shared import load_settings, save_settings


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
