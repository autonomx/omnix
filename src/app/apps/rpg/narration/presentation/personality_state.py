"""Phase 10 — Deterministic personality state helpers.

Provides helpers to ensure and query personality state
within simulation state.
"""
from __future__ import annotations

from typing import Any, Dict, cast

from app.apps.rpg.narration.presentation.visual_state import ensure_visual_state
from app.apps.rpg.foundation.safe_values import dict_copy as _safe_dict, list_copy as _safe_list, safe_str as _safe_str

_MAX_TRAITS = 8
_MAX_STYLE_TAGS = 8


def _normalize_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a personality profile to a consistent shape."""
    profile = _safe_dict(profile)
    return {
        "actor_id": _safe_str(profile.get("actor_id")),
        "display_name": _safe_str(profile.get("display_name")),
        "tone": _safe_str(profile.get("tone") or "neutral"),
        "voice_style": _safe_str(profile.get("voice_style") or "plain"),
        "traits": [
            _safe_str(v)
            for v in _safe_list(profile.get("traits"))[:_MAX_TRAITS]
            if _safe_str(v)
        ],
        "style_tags": [
            _safe_str(v)
            for v in _safe_list(profile.get("style_tags"))[:_MAX_STYLE_TAGS]
            if _safe_str(v)
        ],
        "temperature_hint": _safe_str(profile.get("temperature_hint") or "low"),
    }


def ensure_personality_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure simulation_state has normalized personality state.

    Returns the mutated simulation_state with normalized profiles.
    """
    if not isinstance(simulation_state, dict):
        simulation_state = {}
    presentation_state = simulation_state.setdefault("presentation_state", {})
    if not isinstance(presentation_state, dict):
        presentation_state = simulation_state["presentation_state"] = {}
    personality_state = presentation_state.setdefault("personality_state", {})
    if not isinstance(personality_state, dict):
        personality_state = presentation_state["personality_state"] = {}
    profiles_in = personality_state.get("profiles", {})
    if not isinstance(profiles_in, dict):
        profiles_in = {}

    profiles_out: Dict[str, Dict[str, Any]] = {}
    for actor_id in sorted(profiles_in.keys()):
        normalized = _normalize_profile(cast(Any, profiles_in.get(actor_id)))
        normalized["actor_id"] = _safe_str(actor_id or normalized.get("actor_id"))
        profiles_out[str(actor_id)] = normalized

    personality_state["profiles"] = profiles_out

    simulation_state = ensure_visual_state(simulation_state)
    return simulation_state
