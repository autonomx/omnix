"""Phase 12 — Visual state management for character portraits and scene illustrations.

Provides deterministic, bounded, presentation-only visual identity management.
Images are presentation assets, not simulation truth.

Design invariants:
- No LLM calls
- No mutation of simulation truth
- No generated image affects deterministic gameplay logic
- Image metadata persisted in bounded presentation state only after explicit generation
"""
from __future__ import annotations

from typing import Any, Dict, List

_MAX_SCENE_ILLUSTRATIONS = 24
_MAX_IMAGE_REQUESTS = 24


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


def _safe_int(value: Any, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except Exception:
        return default


def _stable_seed_from_text(text: str) -> int:
    """Generate a deterministic seed from text input."""
    text = _safe_str(text)
    total = 0
    for idx, ch in enumerate(text):
        total = (total + ((idx + 1) * ord(ch))) % 2147483647
    return total or 1


def stable_visual_seed_from_text(text: str) -> int:
    """Public deterministic seed helper for portrait/scene visual requests."""
    return _stable_seed_from_text(text)


def _normalize_visual_identity_entry(value: Any) -> Dict[str, Any]:
    """Normalize a character visual identity entry to a consistent shape."""
    data = _safe_dict(value)
    seed = _safe_int(data.get("seed"), None)
    version = _safe_int(data.get("version"), 1)
    if version is None or version < 1:
        version = 1

    return {
        "portrait_url": _safe_str(data.get("portrait_url")).strip(),
        "portrait_asset_id": _safe_str(data.get("portrait_asset_id")).strip(),
        "seed": seed,
        "style": _safe_str(data.get("style")).strip(),
        "base_prompt": _safe_str(data.get("base_prompt")).strip(),
        "model": _safe_str(data.get("model")).strip(),
        "version": version,
        "status": _first_non_empty(data.get("status"), "idle"),
    }


def _normalize_scene_illustration(value: Any) -> Dict[str, Any]:
    """Normalize a scene illustration entry to a consistent shape."""
    data = _safe_dict(value)
    return {
        "scene_id": _safe_str(data.get("scene_id")).strip(),
        "event_id": _safe_str(data.get("event_id")).strip(),
        "title": _safe_str(data.get("title")).strip(),
        "image_url": _safe_str(data.get("image_url")).strip(),
        "asset_id": _safe_str(data.get("asset_id")).strip(),
        "seed": _safe_int(data.get("seed"), None),
        "style": _safe_str(data.get("style")).strip(),
        "prompt": _safe_str(data.get("prompt")).strip(),
        "model": _safe_str(data.get("model")).strip(),
        "status": _first_non_empty(data.get("status"), "idle"),
    }


def _normalize_image_request(value: Any) -> Dict[str, Any]:
    """Normalize an image request entry to a consistent shape."""
    data = _safe_dict(value)
    kind = _first_non_empty(data.get("kind"), "character_portrait")
    if kind not in {"character_portrait", "scene_illustration"}:
        kind = "character_portrait"

    status = _first_non_empty(data.get("status"), "pending")
    if status not in {"pending", "complete", "failed"}:
        status = "pending"

    return {
        "request_id": _safe_str(data.get("request_id")).strip(),
        "kind": kind,
        "target_id": _safe_str(data.get("target_id")).strip(),
        "prompt": _safe_str(data.get("prompt")).strip(),
        "seed": _safe_int(data.get("seed"), None),
        "style": _safe_str(data.get("style")).strip(),
        "model": _safe_str(data.get("model")).strip(),
        "status": status,
    }


def ensure_visual_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure simulation_state has normalized visual state.

    Returns the mutated simulation_state with normalized visual state.
    """
    if not isinstance(simulation_state, dict):
        simulation_state = {}

    presentation_state = simulation_state.setdefault("presentation_state", {})
    if not isinstance(presentation_state, dict):
        presentation_state = {}
        simulation_state["presentation_state"] = presentation_state

    visual_state = presentation_state.setdefault("visual_state", {})
    if not isinstance(visual_state, dict):
        visual_state = {}
        presentation_state["visual_state"] = visual_state

    identities_in = _safe_dict(visual_state.get("character_visual_identities"))
    identities_out: Dict[str, Any] = {}
    for actor_id in sorted(identities_in.keys(), key=lambda v: _safe_str(v)):
        identities_out[_safe_str(actor_id)] = _normalize_visual_identity_entry(identities_in.get(actor_id))
    visual_state["character_visual_identities"] = identities_out

    illustrations_in = _safe_list(visual_state.get("scene_illustrations"))
    illustrations_out = [
        _normalize_scene_illustration(item)
        for item in illustrations_in
        if isinstance(item, dict)
    ]
    illustrations_out = sorted(
        illustrations_out,
        key=lambda item: (
            _safe_str(item.get("scene_id")),
            _safe_str(item.get("event_id")),
            _safe_str(item.get("title")).lower(),
        ),
    )[:_MAX_SCENE_ILLUSTRATIONS]
    visual_state["scene_illustrations"] = illustrations_out

    requests_in = _safe_list(visual_state.get("image_requests"))
    requests_out = [
        _normalize_image_request(item)
        for item in requests_in
        if isinstance(item, dict)
    ]
    requests_out = sorted(
        requests_out,
        key=lambda item: (
            _safe_str(item.get("kind")),
            _safe_str(item.get("target_id")),
            _safe_str(item.get("request_id")),
        ),
    )[:_MAX_IMAGE_REQUESTS]
    visual_state["image_requests"] = requests_out

    defaults = _safe_dict(visual_state.get("defaults"))
    visual_state["defaults"] = {
        "portrait_style": _first_non_empty(defaults.get("portrait_style"), "rpg-portrait"),
        "scene_style": _first_non_empty(defaults.get("scene_style"), "rpg-scene"),
        "model": _first_non_empty(defaults.get("model"), "default"),
    }

    return simulation_state


def build_default_character_visual_identity(
    *,
    actor_id: str,
    name: str,
    role: str,
    description: str,
    personality_summary: str,
    style: str,
    model: str,
) -> Dict[str, Any]:
    """Build a default character visual identity from character data."""
    actor_id = _safe_str(actor_id).strip()
    name = _safe_str(name).strip()
    role = _safe_str(role).strip()
    description = _safe_str(description).strip()
    personality_summary = _safe_str(personality_summary).strip()
    style = _first_non_empty(style, "rpg-portrait")
    model = _first_non_empty(model, "default")

    prompt_parts = [part for part in [name, role, description, personality_summary] if part]
    base_prompt = ", ".join(prompt_parts)
    seed = _stable_seed_from_text(f"{actor_id}|{name}|{role}|{style}|{model}")

    return {
        "portrait_url": "",
        "portrait_asset_id": "",
        "seed": seed,
        "style": style,
        "base_prompt": base_prompt,
        "model": model,
        "version": 1,
        "status": "idle",
    }


def upsert_character_visual_identity(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str,
    identity: Dict[str, Any],
) -> Dict[str, Any]:
    """Upsert a character visual identity into simulation state."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    identities = _safe_dict(visual_state.get("character_visual_identities"))

    identities[_safe_str(actor_id)] = _normalize_visual_identity_entry(identity)
    visual_state["character_visual_identities"] = dict(sorted(identities.items(), key=lambda item: _safe_str(item[0])))

    return simulation_state


def append_scene_illustration(
    simulation_state: Dict[str, Any],
    illustration: Dict[str, Any],
) -> Dict[str, Any]:
    """Append a scene illustration to visual state, maintaining bounds."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    illustrations = _safe_list(visual_state.get("scene_illustrations"))

    illustrations.append(_normalize_scene_illustration(illustration))
    illustrations = sorted(
        [item for item in illustrations if isinstance(item, dict)],
        key=lambda item: (
            _safe_str(item.get("scene_id")),
            _safe_str(item.get("event_id")),
            _safe_str(item.get("title")).lower(),
        ),
    )[-_MAX_SCENE_ILLUSTRATIONS:]

    visual_state["scene_illustrations"] = illustrations
    return simulation_state


def append_image_request(
    simulation_state: Dict[str, Any],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    """Append an image request to visual state, maintaining bounds."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    requests = _safe_list(visual_state.get("image_requests"))

    requests.append(_normalize_image_request(request))
    requests = sorted(
        [item for item in requests if isinstance(item, dict)],
        key=lambda item: (
            _safe_str(item.get("kind")),
            _safe_str(item.get("target_id")),
            _safe_str(item.get("request_id")),
        ),
    )[-_MAX_IMAGE_REQUESTS:]

    visual_state["image_requests"] = requests
    return simulation_state


# NOTE:
# Scene illustrations are presentation artifacts. They may be requested in response
# to important events, but generation itself must remain explicit and external to
# authoritative simulation reducers. Reducers may suggest event IDs/titles, but must
# never depend on image output.