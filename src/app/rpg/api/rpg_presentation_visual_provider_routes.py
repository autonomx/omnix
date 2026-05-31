"""Grouped RPG presentation API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.rpg.api.rpg_presentation_common import (
    _complete_character_portrait,
    _complete_scene_illustration,
    _get_json,
    _jsonify,
    _safe_dict,
    _safe_str,
    append_visual_asset,
    build_gm_tooling_payload,
    build_memory_inspector_payload,
    build_visual_inspector_payload,
    cleanup_unused_assets,
    datetime,
    download_flux_klein_model,
    enqueue_visual_job,
    get_asset_manifest,
    get_flux_local_model_status,
    get_image_settings_payload,
    get_loaded_image_provider_name,
    get_visual_provider_status_payload,
    is_image_provider_loaded,
    list_visual_jobs,
    load_image_provider,
    load_runtime_session,
    load_session_from_disk,
    load_settings,
    mark_image_request_complete,
    normalize_visual_queue,
    preload_image_provider,
    prune_completed_visual_jobs,
    reinforce_actor_memory,
    run_one_queued_job,
    save_runtime_session,
    save_session_to_disk,
    save_settings,
    switch_image_provider_runtime,
    unload_image_provider,
    unload_image_provider_cache,
    update_image_request,
    validate_memory_state,
    validate_package_integrity,
    validate_session_integrity,
    validate_simulation_state,
    validate_visual_runtime,
    validate_visual_state,
)

router = APIRouter()


@router.post("/api/rpg/visual/queue/enqueue")
async def queue_visual_job_route(request: Request):
    payload = await _get_json(request)
    session_id = str(payload.get("session_id") or "").strip()
    request_id = str(payload.get("request_id") or "").strip()
    if not session_id or not request_id:
        return _jsonify({"ok": False, "error": "session_id_and_request_id_required"}, status_code=400)
    job = enqueue_visual_job(session_id=session_id, request_id=request_id)
    return _jsonify({"ok": True, "job": job})


@router.post("/api/rpg/visual/queue/run_once")
async def run_visual_queue_once_route(request: Request):
    payload = await _get_json(request)
    lease_seconds = int(payload.get("lease_seconds") or 300)
    result = run_one_queued_job(lease_seconds=lease_seconds)
    code = 200 if result.get("ok") else 500
    return _jsonify(result, status_code=code)


@router.get("/api/rpg/visual/queue/stats")
async def visual_queue_stats_route():
    return _jsonify({"ok": True, "stats": {"jobs": list_visual_jobs()}, "jobs": list_visual_jobs()})


@router.post("/api/rpg/visual/queue/prune")
async def prune_visual_queue_route(request: Request):
    payload = await _get_json(request)
    keep_last = int(payload.get("keep_last") or 200)
    result = prune_completed_visual_jobs(keep_last=keep_last)
    return _jsonify({"ok": True, "result": result, "jobs": list_visual_jobs()})


@router.post("/api/rpg/visual/queue/normalize")
async def normalize_visual_queue_route(request: Request):
    result = normalize_visual_queue()
    return _jsonify({"ok": True, "total": result.get("total", 0), "jobs": result.get("jobs", [])})


@router.post("/api/rpg/visual/queue/run_one")
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


@router.get("/api/rpg/visual/provider/settings")
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


@router.post("/api/rpg/visual/provider/settings")
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


@router.post("/api/rpg/visual/download_flux_klein")
async def download_flux_klein_route(_request: Request):
    result = download_flux_klein_model()
    code = 200 if result.get("ok") else 500
    return _jsonify(result, status_code=code)


@router.get("/api/rpg/visual/download_flux_klein")
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


@router.post("/api/rpg/visual/provider/download")
async def download_visual_provider_model_route(request: Request):
    payload = await _get_json(request)
    provider = _safe_str(payload.get("provider")).strip().lower() or "flux_klein"
    if provider != "flux_klein":
        return _jsonify({"ok": False, "error": "unsupported_provider"}, status_code=400)
    result = download_flux_klein_model()
    code = 200 if result.get("ok") else 500
    return _jsonify(result, status_code=code)


@router.post("/api/rpg/visual/provider/load")
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


@router.post("/api/rpg/visual/provider/unload")
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


@router.get("/api/rpg/visual/provider/status")
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


@router.post("/api/rpg/visual/provider/preload")
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


@router.post("/api/rpg/visual/provider/switch")
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

@router.post("/api/rpg/visual/assets/cleanup")
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

@router.post("/api/rpg/visual/inspector")
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

@router.post("/api/rpg/memory/inspector")
async def memory_inspector(request: Request):
    data = await _get_json(request)
    setup_payload = _safe_dict(data.get("setup_payload"))
    simulation_state = _safe_dict(setup_payload.get("simulation_state"))
    payload = build_memory_inspector_payload(simulation_state)
    return _jsonify({"ok": True, "memory_inspector": payload})


# ---- GM Tooling ----

@router.post("/api/rpg/gm/tooling")
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

@router.post("/api/rpg/memory/reinforce")
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

@router.post("/api/rpg/integrity/inspect")
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
