"""Grouped RPG presentation API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.rpg.api.rpg_presentation_common import (
    _drop_visual_requests_for_target,
    _ensure_character_inspector_state,
    _ensure_character_ui_state,
    _ensure_world_inspector_state,
    _extract_character_ui_state,
    _extract_visual_state,
    _first_non_empty,
    _get_json,
    _get_simulation_state,
    _jsonify,
    _load_visual_request_simulation_state,
    _persist_visual_session,
    _request_nonce,
    _safe_dict,
    _safe_list,
    _safe_str,
    append_appearance_event,
    append_image_request,
    append_scene_illustration,
    append_visual_asset,
    apply_visual_fallback,
    build_default_appearance_profile,
    build_default_character_visual_identity,
    build_grounded_scene_illustration_prompt,
    build_visual_asset_record,
    datetime,
    enqueue_visual_job,
    ensure_personality_state,
    ensure_player_party,
    ensure_player_state,
    ensure_visual_state,
    load_settings,
    normalize_visual_status,
    process_pending_image_requests,
    stable_visual_seed_from_text,
    upsert_appearance_profile,
    upsert_character_visual_identity,
    validate_visual_prompt,
)

router = APIRouter()


@router.post("/api/rpg/character_portrait/request")
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


@router.post("/api/rpg/character_portrait/result")
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

@router.post("/api/rpg/scene_illustration/request")
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


@router.post("/api/rpg/scene_illustration/result")
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

@router.post("/api/rpg/visual_assets")
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

@router.post("/api/rpg/visual/process_requests")
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
