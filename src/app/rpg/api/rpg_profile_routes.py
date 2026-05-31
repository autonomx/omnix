"""NPC profile and character-card RPG API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rpg.api.rpg_session_payloads import _safe_dict, _safe_str
from app.rpg.profiles.character_cards import (
    approve_character_card_draft,
    draft_character_card,
    generate_character_card_portrait_prompt,
    generate_character_card_profile,
    get_character_card,
    list_character_cards_for_simulation_state,
    reject_character_card_draft,
    update_character_card,
)
from app.rpg.session.runtime import load_runtime_session
from app.rpg.world.npc_biography_registry import list_npc_biographies


async def list_rpg_npc_biographies():
    return JSONResponse({
        "ok": True,
        "biographies": list_npc_biographies(),
        "source": "deterministic_npc_biography_registry",
    })


async def api_get_rpg_npc_profile(npc_id: str):
    return JSONResponse(get_character_card(npc_id))


async def api_update_rpg_npc_profile(npc_id: str, request: Request):
    payload = await request.json()
    return JSONResponse(update_character_card(
        npc_id,
        _safe_dict(payload.get("updates") or payload),
        edited_by=_safe_str(payload.get("edited_by") or "user"),
        tick=int(payload.get("tick") or 0),
    ))


async def api_draft_rpg_npc_profile(npc_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return JSONResponse(draft_character_card(
        npc_id,
        tick=int((payload or {}).get("tick") or 0),
    ))


async def api_approve_rpg_npc_profile_draft(npc_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return JSONResponse(approve_character_card_draft(
        npc_id,
        tick=int((payload or {}).get("tick") or 0),
    ))


async def api_reject_rpg_npc_profile_draft(npc_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return JSONResponse(reject_character_card_draft(
        npc_id,
        tick=int((payload or {}).get("tick") or 0),
    ))


async def api_generate_rpg_npc_profile_portrait_prompt(npc_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return JSONResponse(generate_character_card_portrait_prompt(
        npc_id,
        tick=int((payload or {}).get("tick") or 0),
    ))


async def api_generate_rpg_npc_profile(npc_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload = payload or {}
    return JSONResponse(generate_character_card_profile(
        npc_id=npc_id,
        name=str(payload.get("name") or ""),
        identity_arc=str(payload.get("identity_arc") or ""),
        current_role=str(payload.get("current_role") or ""),
        active_motivations=payload.get("active_motivations") or [],
        location_id=str(payload.get("location_id") or ""),
        source_event=str(payload.get("source_event") or "manual_profile_generation"),
        context_summary=str(payload.get("context_summary") or ""),
        tick=int(payload.get("tick") or 0),
    ))


async def api_get_rpg_session_character_cards(session_id: str = ""):
    session = load_runtime_session(session_id) if session_id else None
    sim = _safe_dict(
        _safe_dict(session).get("simulation_state")
        if session else None
    )
    return JSONResponse(list_character_cards_for_simulation_state(sim))


def register_rpg_profile_routes(router: APIRouter) -> None:
    router.add_api_route("/api/rpg/npc_biographies", list_rpg_npc_biographies, methods=["GET"])
    router.add_api_route("/api/rpg/npc_profiles/{npc_id:path}", api_get_rpg_npc_profile, methods=["GET"])
    router.add_api_route("/api/rpg/npc_profiles/{npc_id:path}/update", api_update_rpg_npc_profile, methods=["POST"])
    router.add_api_route("/api/rpg/npc_profiles/{npc_id:path}/draft", api_draft_rpg_npc_profile, methods=["POST"])
    router.add_api_route(
        "/api/rpg/npc_profiles/{npc_id:path}/approve_draft",
        api_approve_rpg_npc_profile_draft,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/rpg/npc_profiles/{npc_id:path}/reject_draft",
        api_reject_rpg_npc_profile_draft,
        methods=["POST"],
    )
    router.add_api_route(
        "/api/rpg/npc_profiles/{npc_id:path}/portrait_prompt",
        api_generate_rpg_npc_profile_portrait_prompt,
        methods=["POST"],
    )
    router.add_api_route("/api/rpg/npc_profiles/{npc_id:path}/generate", api_generate_rpg_npc_profile, methods=["POST"])
    router.add_api_route("/api/rpg/session/character_cards", api_get_rpg_session_character_cards, methods=["GET"])
