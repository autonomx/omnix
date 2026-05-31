"""Grouped RPG presentation API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.rpg.api.rpg_presentation_common import (
    _add_content_pack_data,
    _build_actor_activity_context,
    _build_recent_consequence_context,
    _derive_known_npc_ids,
    _derive_npc_live_state,
    _derive_present_npc_ids,
    _ensure_actor_memory_state,
    _ensure_character_inspector_state,
    _ensure_character_ui_state,
    _ensure_world_inspector_state,
    _extract_character_inspector_state,
    _extract_character_ui_state,
    _extract_visual_state,
    _extract_world_inspector_state,
    _get_json,
    _get_simulation_state,
    _jsonify,
    _maybe_answer_from_activity,
    _resolve_authoritative_runtime_state,
    _safe_dict,
    _safe_list,
    _safe_str,
    apply_dialogue_memory_hooks,
    build_conversation_payload,
    build_dialogue_memory_context,
    build_dialogue_presentation_payload,
    build_dialogue_ux_payload,
    build_intro_scene_payload,
    build_live_provider_presentation_payload,
    build_llm_memory_prompt_block,
    build_narrative_recap_payload,
    build_orchestration_presentation_payload,
    build_player_inspector_overlay_payload,
    build_runtime_presentation_payload,
    build_save_load_ux_payload,
    build_scene_presentation_payload,
    build_setup_flow_payload,
    build_speaker_cards,
    ensure_actor_memory_state,
    ensure_content_pack_state,
    ensure_memory_state,
    ensure_personality_state,
    ensure_player_party,
    ensure_player_state,
    ensure_visual_state,
    ensure_world_memory_state,
)

router = APIRouter()


@router.post("/api/rpg/presentation/scene")
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

@router.post("/api/rpg/presentation/dialogue")
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

@router.post("/api/rpg/presentation/speakers")
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

@router.post("/setup-flow")
async def presentation_setup_flow(request: Request):
    body = await _get_json(request)
    user_input = body.get("user_input") or {}
    payload = build_setup_flow_payload(user_input)
    return _jsonify({"ok": True, "presentation": payload})


@router.post("/session-bootstrap")
async def presentation_session_bootstrap(request: Request):
    body = await _get_json(request)
    user_input = body.get("user_input") or {}
    setup_payload = build_setup_flow_payload(user_input)
    setup_flow = setup_payload.get("setup_flow") or {}
    response_payload = {"session_bootstrap": {"world_seed": dict(setup_flow.get("world_seed") or {}), "rules": dict(setup_flow.get("rules") or {}), "player_role": (setup_flow.get("selected") or {}).get("player_role", "wanderer"), "tone_tags": list(setup_flow.get("tone_tags") or []), "seed_prompt": (setup_flow.get("selected") or {}).get("seed_prompt", "")}}
    return _jsonify({"ok": True, "presentation": response_payload})


@router.post("/intro-scene")
async def presentation_intro_scene(request: Request):
    body = await _get_json(request)
    session_bootstrap = body.get("session_bootstrap") or {}
    payload = build_intro_scene_payload(session_bootstrap)
    return _jsonify({"ok": True, "presentation": payload})


@router.post("/save-load-ux")
async def presentation_save_load_ux(request: Request):
    body = await _get_json(request)
    save_snapshots = body.get("save_snapshots") or []
    current_tick = body.get("current_tick") or 0
    payload = build_save_load_ux_payload(save_snapshots=save_snapshots, current_tick=current_tick)
    return _jsonify({"ok": True, "presentation": payload})


@router.post("/narrative-recap")
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

@router.post("/api/rpg/character_ui")
async def presentation_character_ui(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    character_ui_state = _extract_character_ui_state(simulation_state)
    return _jsonify({"ok": True, "character_ui_state": character_ui_state})


@router.post("/api/rpg/character_inspector")
async def presentation_character_inspector(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = _ensure_character_ui_state(simulation_state)
    simulation_state = _ensure_character_inspector_state(simulation_state)
    return _jsonify({"ok": True, "character_inspector_state": _extract_character_inspector_state(simulation_state)})


@router.post("/api/rpg/character_inspector/detail")
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


@router.post("/api/rpg/world_inspector")
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
