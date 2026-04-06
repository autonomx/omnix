from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.compat.character_cards import export_canonical_character_card, import_external_character_card
from app.rpg.presentation.personality_state import ensure_personality_state
from app.rpg.presentation.visual_state import ensure_visual_state
from app.rpg.ui.character_builder import build_character_ui_state
from app.rpg.ui.world_builder import build_world_inspector_state


_PACKAGE_VERSION = "1.0"
_MAX_PACKAGE_CHARACTERS = 64
_MAX_PACKAGE_CARDS = 64
_MAX_PACKAGE_VISUAL_ASSETS = 128
_MAX_PACKAGE_SCENE_ILLUSTRATIONS = 64


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


def _normalize_manifest(value: Any) -> Dict[str, Any]:
    data = _safe_dict(value)
    return {
        "package_version": _first_non_empty(data.get("package_version"), _PACKAGE_VERSION),
        "title": _safe_str(data.get("title")).strip(),
        "description": _safe_str(data.get("description")).strip(),
        "created_by": _safe_str(data.get("created_by")).strip(),
        "source": _safe_str(data.get("source")).strip(),
    }


def _normalize_package(value: Any) -> Dict[str, Any]:
    data = _safe_dict(value)
    return {
        "manifest": _normalize_manifest(data.get("manifest")),
        "simulation_state": _safe_dict(data.get("simulation_state")),
        "presentation_state": _safe_dict(data.get("presentation_state")),
        "character_cards": [
            _safe_dict(item) for item in _safe_list(data.get("character_cards")) if isinstance(item, dict)
        ][:_MAX_PACKAGE_CARDS],
        "world_summary": _safe_dict(data.get("world_summary")),
        "visual_registry": _safe_dict(data.get("visual_registry")),
        "content_packs": [
            _safe_dict(item) for item in _safe_list(data.get("content_packs")) if isinstance(item, dict)
        ],
    }


def build_package_manifest(
    *,
    title: str,
    description: str,
    created_by: str,
    source: str = "rpg-engine",
) -> Dict[str, Any]:
    return {
        "package_version": _PACKAGE_VERSION,
        "title": _safe_str(title).strip(),
        "description": _safe_str(description).strip(),
        "created_by": _safe_str(created_by).strip(),
        "source": _safe_str(source).strip(),
    }


def export_session_package(
    simulation_state: Dict[str, Any],
    *,
    title: str,
    description: str,
    created_by: str,
) -> Dict[str, Any]:
    simulation_state = ensure_personality_state(_safe_dict(simulation_state))
    simulation_state = ensure_visual_state(simulation_state)

    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))

    character_ui_state = build_character_ui_state(simulation_state)
    world_inspector_state = build_world_inspector_state(simulation_state)

    characters = character_ui_state.get("characters") if isinstance(character_ui_state, dict) else []
    if not isinstance(characters, list):
        characters = []

    character_cards = [
        export_canonical_character_card(character)
        for character in characters[:_MAX_PACKAGE_CHARACTERS]
        if isinstance(character, dict)
    ]

    visual_registry = {
        "visual_assets": [
            _safe_dict(item)
            for item in _safe_list(visual_state.get("visual_assets"))
            if isinstance(item, dict)
        ][:_MAX_PACKAGE_VISUAL_ASSETS],
        "scene_illustrations": [
            _safe_dict(item)
            for item in _safe_list(visual_state.get("scene_illustrations"))
            if isinstance(item, dict)
        ][:_MAX_PACKAGE_SCENE_ILLUSTRATIONS],
        "image_requests": [
            _safe_dict(item)
            for item in _safe_list(visual_state.get("image_requests"))
            if isinstance(item, dict)
        ][:_MAX_PACKAGE_VISUAL_ASSETS],
        "defaults": _safe_dict(visual_state.get("defaults")),
    }

    return {
        "manifest": build_package_manifest(
            title=title,
            description=description,
            created_by=created_by,
        ),
        "simulation_state": simulation_state,
        "presentation_state": presentation_state,
        "character_cards": character_cards,
        "world_summary": world_inspector_state,
        "visual_registry": visual_registry,
        "content_packs": [],
    }


def import_session_package(package_data: Dict[str, Any]) -> Dict[str, Any]:
    package_data = _normalize_package(package_data)

    simulation_state = _safe_dict(package_data.get("simulation_state"))
    presentation_state = _safe_dict(package_data.get("presentation_state"))

    if presentation_state:
        simulation_state["presentation_state"] = presentation_state

    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)

    imported_cards = [
        import_external_character_card(card)
        for card in _safe_list(package_data.get("character_cards"))
        if isinstance(card, dict)
    ][: _MAX_PACKAGE_CARDS]

    return {
        "manifest": _safe_dict(package_data.get("manifest")),
        "simulation_state": simulation_state,
        "imported_cards": imported_cards,
        "world_summary": _safe_dict(package_data.get("world_summary")),
        "visual_registry": _safe_dict(package_data.get("visual_registry")),
        "content_packs": _safe_list(package_data.get("content_packs")),
    }