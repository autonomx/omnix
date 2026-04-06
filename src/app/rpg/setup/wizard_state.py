"""Phase 13.4 — New Adventure Wizard UI state module.

Provides normalized wizard-state management for adventure setup composition.
"""
from __future__ import annotations

from typing import Any, Dict, List


_MAX_WIZARD_CHARACTERS = 16


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _normalize_character_seed(value: Any) -> Dict[str, Any]:
    data = _safe_dict(value)
    canonical_seed = _safe_dict(data.get("canonical_seed"))
    personality_seed = _safe_dict(data.get("personality_seed"))
    appearance_seed = _safe_dict(data.get("appearance_seed"))
    visual_seed = _safe_dict(data.get("visual_seed"))

    return {
        "canonical_seed": canonical_seed,
        "personality_seed": personality_seed,
        "appearance_seed": appearance_seed,
        "visual_seed": visual_seed,
    }


def normalize_wizard_state(value: Any) -> Dict[str, Any]:
    """Normalize wizard input into a deterministic bounded state."""
    data = _safe_dict(value)
    return {
        "step": _first_non_empty(data.get("step"), "mode"),
        "mode": _first_non_empty(data.get("mode"), "blank"),
        "selected_pack": _safe_dict(data.get("selected_pack")),
        "selected_template": _safe_dict(data.get("selected_template")),
        "title": _safe_str(data.get("title")).strip(),
        "summary": _safe_str(data.get("summary")).strip(),
        "opening": _safe_str(data.get("opening")).strip(),
        "world_seed": _safe_dict(data.get("world_seed")),
        "character_seeds": [
            _normalize_character_seed(item)
            for item in _safe_list(data.get("character_seeds"))
            if isinstance(item, dict)
        ][:_MAX_WIZARD_CHARACTERS],
        "visual_defaults": _safe_dict(data.get("visual_defaults")),
    }


def build_wizard_preview_payload(wizard_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build a preview payload from current wizard state."""
    wizard_state = normalize_wizard_state(wizard_state)
    return {
        "title": wizard_state.get("title", ""),
        "summary": wizard_state.get("summary", ""),
        "opening": wizard_state.get("opening", ""),
        "character_count": len(wizard_state.get("character_seeds", [])),
        "world_seed": wizard_state.get("world_seed", {}),
        "visual_defaults": wizard_state.get("visual_defaults", {}),
        "mode": wizard_state.get("mode", "blank"),
    }


def build_wizard_setup_payload(wizard_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build deterministic setup payload from wizard state for simulation bootstrap."""
    wizard_state = normalize_wizard_state(wizard_state)

    simulation_state = {
        "presentation_state": {
            "visual_state": {
                "defaults": _safe_dict(wizard_state.get("visual_defaults")),
            }
        },
        "world_state": {
            "scenario_title": _safe_str(wizard_state.get("title")).strip(),
            "scenario_summary": _safe_str(wizard_state.get("summary")).strip(),
            "opening": _safe_str(wizard_state.get("opening")).strip(),
            "world_seed": _safe_dict(wizard_state.get("world_seed")),
        },
        "setup_state": {
            "character_seeds": _safe_list(wizard_state.get("character_seeds")),
            "selected_pack": _safe_dict(wizard_state.get("selected_pack")),
            "selected_template": _safe_dict(wizard_state.get("selected_template")),
            "mode": _safe_str(wizard_state.get("mode")).strip(),
        },
    }

    return {
        "simulation_state": simulation_state,
        "wizard_state": wizard_state,
    }