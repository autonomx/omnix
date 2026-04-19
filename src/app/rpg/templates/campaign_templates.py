"""Phase 13.3 — Campaign Template / Adventure Bootstrap.

Provides reusable template payloads that can start new adventures.
Templates are not running sessions.
They are "scenario + world + visual + pack reference" presets.
"""
from __future__ import annotations

from typing import Any, Dict, List

_MAX_TEMPLATES = 32


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


def _normalize_template(value: Any) -> Dict[str, Any]:
    data = _safe_dict(value)
    manifest = _safe_dict(data.get("manifest"))
    bootstrap = _safe_dict(data.get("bootstrap"))
    return {
        "manifest": {
            "id": _safe_str(manifest.get("id")).strip(),
            "title": _safe_str(manifest.get("title")).strip(),
            "description": _safe_str(manifest.get("description")).strip(),
            "version": _first_non_empty(manifest.get("version"), "1.0"),
        },
        "bootstrap": bootstrap,
    }


def build_campaign_template(
    *,
    template_id: str,
    title: str,
    description: str,
    bootstrap: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a reusable campaign template from bootstrap payload."""
    return _normalize_template({
        "manifest": {
            "id": template_id,
            "title": title,
            "description": description,
            "version": "1.0",
        },
        "bootstrap": bootstrap,
    })


def build_template_start_payload(template: Dict[str, Any]) -> Dict[str, Any]:
    """Build start-session payload from campaign template."""
    template = _normalize_template(template)
    manifest = _safe_dict(template.get("manifest"))
    bootstrap = _safe_dict(template.get("bootstrap"))

    return {
        "template_manifest": manifest,
        "setup_payload": {
            "simulation_state": {
                "presentation_state": {
                    "visual_state": {
                        "defaults": _safe_dict(bootstrap.get("visual_defaults")),
                    }
                },
                "world_state": {
                    "scenario_title": _safe_str(bootstrap.get("title")).strip(),
                    "scenario_summary": _safe_str(bootstrap.get("summary")).strip(),
                    "world_seed": _safe_dict(bootstrap.get("world_seed")),
                },
            },
            "bootstrap": bootstrap,
        },
    }


def list_campaign_templates(templates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize and list provided campaign templates."""
    normalized = [
        _normalize_template(item)
        for item in _safe_list(templates)
        if isinstance(item, dict)
    ]
    normalized = sorted(
        normalized,
        key=lambda item: (
            _safe_str(_safe_dict(item.get("manifest")).get("title")).lower(),
            _safe_str(_safe_dict(item.get("manifest")).get("id")),
        ),
    )[:_MAX_TEMPLATES]
    return normalized


TAVERN_START_TEMPLATE = build_campaign_template(
    template_id="quick-tavern-adventure",
    title="Quick Start: The Rusty Tankard Tavern",
    description="A classic adventure start. You wake up at a table in a crowded, warm tavern with no memory of how you got here. The bartender eyes you suspiciously. A cloaked stranger in the corner is watching. Something is about to happen.",
    bootstrap={
        "title": "The Rusty Tankard",
        "summary": "You have arrived at the Rusty Tankard Tavern, a roadside establishment on the edge of civilization.",
        "visual_defaults": {
            "lighting": "warm_candlelight",
            "atmosphere": "lively_tavern",
            "time_of_day": "evening",
        },
        "world_seed": {
            "location": {
                "name": "The Rusty Tankard Tavern",
                "type": "tavern",
                "environment": "cozy, crowded, wood interior, smoke curling from hearths",
            },
            "starting_npcs": [
                {
                    "name": "Mara",
                    "role": "bartender",
                    "description": "Middle aged human woman, tough but fair, runs the tavern with an iron fist",
                    "disposition": "neutral_watchful",
                },
                {
                    "name": "The Cloaked Stranger",
                    "role": "mysterious_visitor",
                    "description": "Sits alone in the darkest corner, hood pulled low, hasn't touched their drink",
                    "disposition": "observing",
                }
            ],
            "starting_situation": "You are sitting at a rough wooden table. A half empty mug of ale sits before you. Your head aches. You don't remember arriving here. The tavern is noisy with travellers, merchants and mercenaries. Outside the wind howls.",
            "immediate_hooks": [
                "The bartender is heading your way",
                "The stranger in the corner just gestured to you",
                "A loud argument is breaking out near the door",
                "Someone just dropped a sealed envelope at your feet"
            ]
        },
        "starting_inventory": {
            "gold": 5,
            "items": ["worn cloak", "simple dagger", "empty backpack"]
        },
        "ambient_settings": {
            "background_sounds": ["murmuring voices", "clinking mugs", "fire crackling", "wind outside"],
            "npc_activity_level": "high"
        }
    }
)


DEFAULT_CAMPAIGN_TEMPLATES = [
    TAVERN_START_TEMPLATE,
]
