"""Grouped RPG presentation API routes."""
from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Request

from app.rpg.api.rpg_presentation_common import (
    _ensure_character_inspector_state,
    _ensure_character_ui_state,
    _ensure_world_inspector_state,
    _extract_character_inspector_state,
    _extract_character_ui_state,
    _extract_visual_state,
    _get_json,
    _get_simulation_state,
    _jsonify,
    _safe_dict,
    _safe_list,
    _safe_str,
    append_long_term_memory,
    append_short_term_memory,
    append_world_memory,
    apply_content_pack,
    archive_session,
    build_campaign_template,
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
    build_pack_application_preview,
    build_pack_bootstrap_payload,
    build_pack_draft_export,
    build_pack_draft_preview,
    build_template_start_payload,
    build_wizard_preview_payload,
    build_wizard_setup_payload,
    decay_memory_state,
    ensure_actor_memory_state,
    ensure_content_pack_state,
    ensure_memory_state,
    ensure_personality_state,
    ensure_player_party,
    ensure_player_state,
    ensure_session_registry,
    ensure_visual_state,
    ensure_world_memory_state,
    export_canonical_character_card,
    export_session_as_package,
    export_session_package,
    get_session,
    import_external_character_card,
    import_session_from_package,
    import_session_package,
    list_campaign_templates,
    list_content_packs,
    list_sessions,
    list_sessions_from_disk,
    load_session_from_disk,
    migrate_session_payload,
    normalize_wizard_state,
    save_session,
    save_session_to_disk,
    validate_pack_draft,
)

router = APIRouter()



@router.post("/api/rpg/character/import")
async def import_character_card(request: Request):
    data = await _get_json(request)
    card = _safe_dict(data.get("card"))
    imported = import_external_character_card(card)
    return _jsonify({"ok": True, "imported": imported})


@router.post("/api/rpg/character/export")
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

@router.post("/api/rpg/gm_trace")
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

@router.post("/api/rpg/package/export")
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


@router.post("/api/rpg/package/import")
async def import_rpg_package(request: Request):
    data = await _get_json(request)
    package_data = _safe_dict(data.get("package"))
    imported = import_session_package(package_data)
    return _jsonify({"ok": True, "imported": imported})


# ---- Content Packs ----

@router.post("/api/rpg/packs/list")
async def list_rpg_packs(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_content_pack_state(simulation_state)
    return _jsonify({"ok": True, "packs": list_content_packs(simulation_state)})


@router.post("/api/rpg/packs/preview")
async def preview_rpg_pack(request: Request):
    data = await _get_json(request)
    pack = _safe_dict(data.get("pack"))
    preview = build_pack_application_preview(pack)
    return _jsonify({"ok": True, "preview": preview})


@router.post("/api/rpg/packs/apply")
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


@router.post("/api/rpg/packs/bootstrap")
async def bootstrap_rpg_pack(request: Request):
    data = await _get_json(request)
    pack = _safe_dict(data.get("pack"))
    bootstrap = build_pack_bootstrap_payload(pack)
    return _jsonify({"ok": True, "bootstrap": bootstrap})


@router.post("/api/rpg/packs/start")
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

@router.post("/api/rpg/creator/pack/validate")
async def validate_rpg_pack_draft(request: Request):
    data = await _get_json(request)
    draft = _safe_dict(data.get("draft"))
    validation = validate_pack_draft(draft)
    return _jsonify({"ok": True, "validation": validation})


@router.post("/api/rpg/creator/pack/preview")
async def preview_rpg_pack_draft(request: Request):
    data = await _get_json(request)
    draft = _safe_dict(data.get("draft"))
    preview = build_pack_draft_preview(draft)
    return _jsonify({"ok": True, "preview": preview})


@router.post("/api/rpg/creator/pack/export")
async def export_rpg_pack_draft(request: Request):
    data = await _get_json(request)
    draft = _safe_dict(data.get("draft"))
    exported = build_pack_draft_export(draft)
    return _jsonify({"ok": True, "pack": exported})


# ---- Campaign Templates ----

@router.post("/api/rpg/templates/build")
async def build_rpg_template(request: Request):
    data = await _get_json(request)
    template_id = _safe_str(data.get("template_id")).strip() or "template:default"
    title = _safe_str(data.get("title")).strip() or "Campaign Template"
    description = _safe_str(data.get("description")).strip()
    bootstrap = _safe_dict(data.get("bootstrap"))
    template = build_campaign_template(template_id=template_id, title=title, description=description, bootstrap=bootstrap)
    return _jsonify({"ok": True, "template": template})


@router.post("/api/rpg/templates/start")
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


@router.post("/api/rpg/templates/list")
async def list_rpg_templates(request: Request):
    data = await _get_json(request)
    templates = _safe_list(data.get("templates"))
    return _jsonify({"ok": True, "templates": list_campaign_templates(templates)})


# ---- Wizard ----

@router.post("/api/rpg/wizard/preview")
async def preview_rpg_wizard(request: Request):
    data = await _get_json(request)
    wizard_state = normalize_wizard_state(data.get("wizard_state"))
    return _jsonify({"ok": True, "preview": build_wizard_preview_payload(wizard_state)})


@router.post("/api/rpg/wizard/build")
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


@router.post("/api/rpg/session/save")
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


@router.post("/api/rpg/session/list")
async def list_rpg_sessions(request: Request):
    global _RPG_SESSION_ROOT_STATE
    _RPG_SESSION_ROOT_STATE = ensure_session_registry(_RPG_SESSION_ROOT_STATE)
    disk_sessions = list_sessions_from_disk()
    migrated_sessions = [migrate_session_payload(s) for s in disk_sessions] if disk_sessions else []
    return _jsonify({"ok": True, "sessions": migrated_sessions or list_sessions(_RPG_SESSION_ROOT_STATE)})


@router.post("/api/rpg/session/load")
async def load_rpg_session(request: Request):
    global _RPG_SESSION_ROOT_STATE
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    session = migrate_session_payload(load_session_from_disk(session_id)) or get_session(_RPG_SESSION_ROOT_STATE, session_id)
    if not session:
        return _jsonify({"ok": False, "error": "session_not_found"}, status_code=404)
    return _jsonify({"ok": True, "session": session})


@router.post("/api/rpg/session/archive")
async def archive_rpg_session(request: Request):
    global _RPG_SESSION_ROOT_STATE
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    _RPG_SESSION_ROOT_STATE = archive_session(_RPG_SESSION_ROOT_STATE, session_id)
    return _jsonify({"ok": True, "sessions": list_sessions(_RPG_SESSION_ROOT_STATE)})


# ---- Memory ----

@router.post("/api/rpg/memory/get")
async def get_rpg_memory(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    return _jsonify({"ok": True, "memory_state": _safe_dict(simulation_state.get("memory_state"))})


@router.post("/api/rpg/memory/add")
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

@router.post("/api/rpg/memory/dialogue_context")
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

@router.post("/api/rpg/memory/decay")
async def memory_decay(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    simulation_state = decay_memory_state(simulation_state)
    setup_payload["simulation_state"] = simulation_state
    return _jsonify({"ok": True, "setup_payload": setup_payload})


# ---- Session Package ----

@router.post("/api/rpg/session/export_package")
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


@router.post("/api/rpg/session/import_package")
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
