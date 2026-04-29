from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.profiles.dynamic_npc_profiles import (
    ensure_dynamic_npc_profile,
    load_npc_profile,
    update_npc_character_card,
)
from app.rpg.profiles.profile_drafts import (
    approve_profile_draft,
    create_pending_profile_draft,
    profile_draft_summary,
    reject_profile_draft,
)
from app.rpg.profiles.profile_portraits import save_profile_portrait_prompt


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _known_npc_ids_from_simulation_state(simulation_state: Dict[str, Any]) -> List[str]:
    ids = []

    party_state = _safe_dict(_safe_dict(simulation_state.get("player_state")).get("party_state"))
    for companion in _safe_list(party_state.get("companions")):
        npc_id = _safe_str(_safe_dict(companion).get("npc_id"))
        if npc_id:
            ids.append(npc_id)

    present_state = _safe_dict(simulation_state.get("present_npc_state"))
    by_location = _safe_dict(present_state.get("by_location"))
    for location_entry in by_location.values():
        for npc in _safe_list(_safe_dict(location_entry).get("present_npcs")):
            npc_id = _safe_str(_safe_dict(npc).get("npc_id"))
            if npc_id:
                ids.append(npc_id)

    evolution_by_npc = _safe_dict(_safe_dict(simulation_state.get("npc_evolution_state")).get("by_npc"))
    for npc_id in evolution_by_npc.keys():
        if _safe_str(npc_id):
            ids.append(_safe_str(npc_id))

    # Stable order, no duplicates.
    seen = set()
    result = []
    for npc_id in ids:
        if npc_id not in seen:
            seen.add(npc_id)
            result.append(npc_id)

    return result


def build_character_card(profile: Dict[str, Any]) -> Dict[str, Any]:
    profile = _safe_dict(profile)
    npc_id = _safe_str(profile.get("npc_id"))

    return {
        "npc_id": npc_id,
        "name": _safe_str(profile.get("name")),
        "origin": _safe_str(profile.get("origin")),
        "biography": deepcopy(_safe_dict(profile.get("biography"))),
        "history": deepcopy(_safe_dict(profile.get("history"))),
        "personality": deepcopy(_safe_dict(profile.get("personality"))),
        "morality": deepcopy(_safe_dict(profile.get("morality"))),
        "motivations": deepcopy(_safe_list(profile.get("motivations"))),
        "relationships": deepcopy(_safe_dict(profile.get("relationships"))),
        "evolution": deepcopy(_safe_dict(profile.get("evolution"))),
        "portrait": deepcopy(_safe_dict(profile.get("portrait"))),
        "card_edit_state": deepcopy(_safe_dict(profile.get("card_edit_state"))),
        "draft_summary": profile_draft_summary(npc_id),
        "source": "deterministic_character_card_service",
    }


def get_character_card(npc_id: str) -> Dict[str, Any]:
    profile = load_npc_profile(npc_id)
    if not profile:
        return {
            "ok": False,
            "reason": "profile_not_found",
            "npc_id": _safe_str(npc_id),
            "source": "deterministic_character_card_service",
        }

    return {
        "ok": True,
        "card": build_character_card(profile),
        "source": "deterministic_character_card_service",
    }


def list_character_cards_for_simulation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    cards = []
    missing = []

    for npc_id in _known_npc_ids_from_simulation_state(simulation_state):
        profile = load_npc_profile(npc_id)
        if profile:
            cards.append(build_character_card(profile))
        else:
            missing.append(npc_id)

    return {
        "ok": True,
        "cards": cards,
        "missing_profile_npc_ids": missing,
        "count": len(cards),
        "source": "deterministic_character_card_service",
    }


def update_character_card(
    npc_id: str,
    updates: Dict[str, Any],
    *,
    edited_by: str = "user",
    tick: int = 0,
) -> Dict[str, Any]:
    result = update_npc_character_card(
        npc_id,
        updates,
        edited_by=edited_by,
        tick=tick,
    )
    return {
        "ok": bool(result.get("updated")),
        "update_result": result,
        "card": build_character_card(result.get("profile", {})) if result.get("updated") else {},
        "source": "deterministic_character_card_service",
    }


def draft_character_card(npc_id: str, *, tick: int = 0) -> Dict[str, Any]:
    result = create_pending_profile_draft(
        npc_id,
        tick=tick,
        created_by="deterministic_fallback_drafter",
    )
    return {
        "ok": bool(result.get("drafted")),
        "draft_result": result,
        "card": get_character_card(npc_id).get("card", {}),
        "source": "deterministic_character_card_service",
    }


def approve_character_card_draft(npc_id: str, *, tick: int = 0) -> Dict[str, Any]:
    result = approve_profile_draft(
        npc_id,
        tick=tick,
        approved_by="llm_draft_approved",
    )
    return {
        "ok": bool(result.get("approved")),
        "approval_result": result,
        "card": build_character_card(result.get("profile", {})) if result.get("approved") else {},
        "source": "deterministic_character_card_service",
    }


def reject_character_card_draft(npc_id: str, *, tick: int = 0) -> Dict[str, Any]:
    result = reject_profile_draft(npc_id, tick=tick)
    return {
        "ok": bool(result.get("rejected")),
        "rejection_result": result,
        "card": get_character_card(npc_id).get("card", {}),
        "source": "deterministic_character_card_service",
    }


def generate_character_card_portrait_prompt(npc_id: str, *, tick: int = 0) -> Dict[str, Any]:
    result = save_profile_portrait_prompt(npc_id, tick=tick)
    return {
        "ok": bool(result.get("saved")),
        "portrait_prompt_result": result,
        "card": build_character_card(result.get("profile", {})) if result.get("saved") else {},
        "source": "deterministic_character_card_service",
    }


def generate_character_card_profile(
    *,
    npc_id: str,
    name: str = "",
    identity_arc: str = "",
    current_role: str = "",
    active_motivations: List[Dict[str, Any]] | None = None,
    location_id: str = "",
    source_event: str = "manual_profile_generation",
    context_summary: str = "",
    tick: int = 0,
) -> Dict[str, Any]:
    result = ensure_dynamic_npc_profile(
        npc_id=npc_id,
        name=name,
        identity_arc=identity_arc,
        current_role=current_role,
        active_motivations=active_motivations,
        location_id=location_id,
        source_event=source_event,
        context_summary=context_summary,
        tick=tick,
    )
    return {
        "ok": bool(result.get("created") or result.get("profile")),
        "profile_generation_result": result,
        "card": build_character_card(result.get("profile", {})) if result.get("profile") else {},
        "source": "deterministic_character_card_service",
    }
