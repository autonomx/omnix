"""Phase 10 — Speaker card builders.

Provides deterministic speaker card building for scene and dialogue presentation.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.party import build_companion_presence_summary
from .personality import build_personality_style_tags
from .personality_state import get_actor_personality_profile


_KIND_ORDER = {
    "player": 0,
    "companion": 1,
}


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def build_speaker_cards(simulation_state: Dict[str, Any], scene_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build speaker cards for a scene, including player and present companions.

    Returns a sorted list of cards by kind then speaker_id.
    """
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    scene_state = _safe_dict(scene_state)

    cards: List[Dict[str, Any]] = []

    # Always include the player card
    cards.append({
        "speaker_id": "player",
        "name": "Player",
        "kind": "player",
        "portrait_key": "player",
        "style_tags": ["player"],
        "location_id": _safe_str(scene_state.get("location_id")),
    })

    # Build cards for present companions
    presence = build_companion_presence_summary(player_state)
    for comp in _safe_list(presence.get("present_companions")):
        if not isinstance(comp, dict):
            continue
        profile = get_actor_personality_profile(
            simulation_state,
            _safe_str(comp.get("npc_id")),
            default_name=_safe_str(comp.get("name")),
        )
        style_tags = _safe_list(profile.get("style_tags")) or build_personality_style_tags(comp)
        cards.append({
            "speaker_id": _safe_str(comp.get("npc_id")),
            "name": _safe_str(profile.get("display_name") or comp.get("name")),
            "kind": "companion",
            "portrait_key": _safe_str(comp.get("npc_id")),
            "style_tags": style_tags,
            "location_id": _safe_str(scene_state.get("location_id")),
        })

    return sorted(
        cards,
        key=lambda c: (
            _KIND_ORDER.get(_safe_str(c.get("kind")), 99),
            _safe_str(c.get("speaker_id")),
        ),
    )


def build_party_speaker_cards(simulation_state: Dict[str, Any], companions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build minimal speaker cards for a list of companion dicts.

    Used when you need only companion cards, not the full speaker set.
    """
    simulation_state = _safe_dict(simulation_state)
    cards: List[Dict[str, Any]] = []
    for comp in _safe_list(companions):
        if not isinstance(comp, dict):
            continue
        if _safe_str(comp.get("status")) != "active":
            continue
        profile = get_actor_personality_profile(
            simulation_state,
            _safe_str(comp.get("npc_id")),
            default_name=_safe_str(comp.get("name")),
        )
        style_tags = _safe_list(profile.get("style_tags")) or build_personality_style_tags(comp)
        cards.append({
            "speaker_id": _safe_str(comp.get("npc_id")),
            "name": _safe_str(profile.get("display_name") or comp.get("name")),
            "kind": "companion",
            "portrait_key": _safe_str(comp.get("npc_id")),
            "style_tags": style_tags,
            "location_id": _safe_str(comp.get("location_id")),
        })
    cards = sorted(
        cards,
        key=lambda c: (
            _KIND_ORDER.get(_safe_str(c.get("kind")), 99),
            _safe_str(c.get("speaker_id")),
        ),
    )
    return cards[:6]