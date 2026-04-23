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
_MAX_VISUAL_ASSETS = 64
_MAX_APPEARANCE_EVENTS = 32


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


def _stable_asset_id(kind: str, target_id: str, version: int, seed: int | None) -> str:
    seed_text = str(seed) if isinstance(seed, int) else "none"
    return f"{_safe_str(kind).strip()}:{_safe_str(target_id).strip()}:{max(1, int(version))}:{seed_text}"


def stable_visual_seed_from_text(text: str) -> int:
    """Public deterministic seed helper for portrait/scene visual requests."""
    return _stable_seed_from_text(text)


def _normalize_scalar(value: Any) -> Any:
    """Normalize a scalar value for appearance features."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return _safe_str(value)


def _normalize_visual_identity_entry(value: Any) -> Dict[str, Any]:
    """Normalize a character visual identity entry to a consistent shape."""
    data = _safe_dict(value)
    seed = _safe_int(data.get("seed"), None)
    version = _safe_int(data.get("version"), 1)
    if version is None or version < 1:
        version = 1

    return {
        "portrait_url": _safe_str(data.get("portrait_url")).strip(),
        "portrait_local_path": _safe_str(data.get("portrait_local_path")).strip(),
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
        "local_path": _safe_str(data.get("local_path")).strip(),
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
    if status not in {"pending", "complete", "failed", "blocked"}:
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
        "attempts": max(0, _safe_int(data.get("attempts"), 0) or 0),
        "max_attempts": max(1, _safe_int(data.get("max_attempts"), 3) or 3),
        "error": _safe_str(data.get("error")).strip(),
        "created_at": _safe_str(data.get("created_at")).strip(),
        "updated_at": _safe_str(data.get("updated_at")).strip(),
        "completed_at": _safe_str(data.get("completed_at")).strip(),
    }


def _normalize_visual_asset(value: Any) -> Dict[str, Any]:
    """Normalize a visual asset entry to a consistent shape."""
    data = _safe_dict(value)
    version = _safe_int(data.get("version"), 1)
    if version is None or version < 1:
        version = 1

    kind = _first_non_empty(data.get("kind"), "character_portrait")
    if kind not in {"character_portrait", "scene_illustration"}:
        kind = "character_portrait"

    status = _first_non_empty(data.get("status"), "complete")
    if status not in {"pending", "complete", "failed", "blocked"}:
        status = "complete"

    moderation = _safe_dict(data.get("moderation"))
    moderation_status = _first_non_empty(moderation.get("status"), "unchecked")
    if moderation_status not in {"unchecked", "approved", "blocked", "flagged"}:
        moderation_status = "unchecked"

    return {
        "asset_id": _safe_str(data.get("asset_id")).strip(),
        "kind": kind,
        "target_id": _safe_str(data.get("target_id")).strip(),
        "url": _safe_str(data.get("url")).strip(),
        "local_path": _safe_str(data.get("local_path")).strip(),
        "cache_key": _safe_str(data.get("cache_key")).strip(),
        "seed": _safe_int(data.get("seed"), None),
        "style": _safe_str(data.get("style")).strip(),
        "model": _safe_str(data.get("model")).strip(),
        "prompt": _safe_str(data.get("prompt")).strip(),
        "version": version,
        "status": status,
        "created_from_request_id": _safe_str(data.get("created_from_request_id")).strip(),
        "moderation": {
            "status": moderation_status,
            "reason": _safe_str(moderation.get("reason")).strip(),
        },
    }


def _normalize_appearance_profile(value: Any) -> Dict[str, Any]:
    """Normalize an appearance profile entry to a consistent shape."""
    data = _safe_dict(value)

    features = _safe_dict(data.get("features"))
    normalized_features = {}
    for key in sorted(features.keys(), key=lambda v: _safe_str(v)):
        if not _safe_str(key).strip():
            continue
        normalized_features[_safe_str(key)] = _normalize_scalar(features.get(key))

    return {
        "base_description": _safe_str(data.get("base_description")).strip(),
        "current_summary": _safe_str(data.get("current_summary")).strip(),
        "features": normalized_features,
        "last_reason": _safe_str(data.get("last_reason")).strip(),
        "version": max(1, _safe_int(data.get("version"), 1) or 1),
    }


def _normalize_appearance_event(value: Any) -> Dict[str, Any]:
    """Normalize an appearance event entry to a consistent shape."""
    data = _safe_dict(value)
    reason = _first_non_empty(data.get("reason"), "update")
    if reason not in {
        "initial",
        "injury",
        "promotion",
        "faction_change",
        "equipment_change",
        "corruption",
        "disguise",
        "aging",
        "manual_refresh",
        "update",
    }:
        reason = "update"

    return {
        "event_id": _safe_str(data.get("event_id")).strip(),
        "reason": reason,
        "summary": _safe_str(data.get("summary")).strip(),
        "tick": max(0, _safe_int(data.get("tick"), 0) or 0),
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

    # Phase 12.3 — visual assets
    assets_in = _safe_list(visual_state.get("visual_assets"))
    assets_out = [
        _normalize_visual_asset(item)
        for item in assets_in
        if isinstance(item, dict)
    ]
    assets_out = sorted(
        assets_out,
        key=lambda item: (
            _safe_str(item.get("kind")),
            _safe_str(item.get("target_id")),
            _safe_str(item.get("asset_id")),
        ),
    )[-_MAX_VISUAL_ASSETS:]
    visual_state["visual_assets"] = assets_out

    # Phase 12.4 — appearance profiles
    profiles_in = _safe_dict(visual_state.get("appearance_profiles"))
    profiles_out: Dict[str, Any] = {}
    for actor_id in sorted(profiles_in.keys(), key=lambda v: _safe_str(v)):
        profiles_out[_safe_str(actor_id)] = _normalize_appearance_profile(profiles_in.get(actor_id))
    visual_state["appearance_profiles"] = profiles_out

    # Phase 12.4 — appearance events
    events_in = _safe_dict(visual_state.get("appearance_events"))
    events_out: Dict[str, Any] = {}
    for actor_id in sorted(events_in.keys(), key=lambda v: _safe_str(v)):
        raw_events = _safe_list(events_in.get(actor_id))
        normalized_events = [
            _normalize_appearance_event(item)
            for item in raw_events
            if isinstance(item, dict)
        ]
        normalized_events = sorted(
            normalized_events,
            key=lambda item: (
                item.get("tick", 0),
                _safe_str(item.get("reason")),
                _safe_str(item.get("event_id")),
            ),
        )[-_MAX_APPEARANCE_EVENTS:]
        events_out[_safe_str(actor_id)] = normalized_events
    visual_state["appearance_events"] = events_out

    defaults = _safe_dict(visual_state.get("defaults"))
    visual_state["defaults"] = {
        "portrait_style": _first_non_empty(defaults.get("portrait_style"), "rpg-portrait"),
        "scene_style": _first_non_empty(defaults.get("scene_style"), "rpg-scene"),
        "model": _first_non_empty(defaults.get("model"), "default"),
        "fallback_portrait_url": _safe_str(defaults.get("fallback_portrait_url")).strip(),
        "fallback_scene_url": _safe_str(defaults.get("fallback_scene_url")).strip(),
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

    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


def append_scene_illustration(
    simulation_state: Dict[str, Any],
    illustration: Dict[str, Any],
) -> Dict[str, Any]:
    """Append a scene illustration to visual state, maintaining bounds."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    illustrations = [
        _normalize_scene_illustration(item)
        for item in _safe_list(visual_state.get("scene_illustrations"))
        if isinstance(item, dict)
    ]

    normalized = _normalize_scene_illustration(illustration)
    normalized_scene_id = _safe_str(normalized.get("scene_id")).strip()
    normalized_event_id = _safe_str(normalized.get("event_id")).strip()
    normalized_asset_id = _safe_str(normalized.get("asset_id")).strip()

    deduped = []
    for item in illustrations:
        same_event = (
            normalized_event_id
            and _safe_str(item.get("event_id")).strip() == normalized_event_id
        )
        same_asset = (
            normalized_asset_id
            and _safe_str(item.get("asset_id")).strip() == normalized_asset_id
        )
        same_scene_latest = (
            normalized_scene_id
            and not normalized_event_id
            and _safe_str(item.get("scene_id")).strip() == normalized_scene_id
        )
        if same_event or same_asset or same_scene_latest:
            continue
        deduped.append(item)

    deduped.append(normalized)
    illustrations = sorted(
        deduped,
        key=lambda item: (
            _safe_str(item.get("scene_id")),
            _safe_str(item.get("event_id")),
            _safe_str(item.get("title")).lower(),
        ),
    )[-_MAX_SCENE_ILLUSTRATIONS:]

    visual_state["scene_illustrations"] = illustrations
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
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
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


# ---- Phase 12.10 — Request update helpers for worker ----


def update_image_request(
    simulation_state: Dict[str, Any],
    *,
    request_id: str,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    """Update an existing image request by ID with the given patch fields."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    requests = _safe_list(visual_state.get("image_requests"))

    updated = []
    for item in requests:
        item_dict = _safe_dict(item)
        if _safe_str(item_dict.get("request_id")).strip() == _safe_str(request_id).strip():
            merged = dict(item_dict)
            merged.update(_safe_dict(patch))
            updated.append(_normalize_image_request(merged))
        else:
            updated.append(_normalize_image_request(item_dict))

    visual_state["image_requests"] = updated[-_MAX_IMAGE_REQUESTS:]
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


def get_pending_image_requests(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a list of pending image requests."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    requests = _safe_list(visual_state.get("image_requests"))
    out = []
    for item in requests:
        item_dict = _safe_dict(item)
        if _first_non_empty(item_dict.get("status"), "pending") == "pending":
            out.append(_normalize_image_request(item_dict))
    return out


# ---- Phase 12.3 — Asset registry + continuity mutators ----


def append_visual_asset(
    simulation_state: Dict[str, Any],
    asset: Dict[str, Any],
) -> Dict[str, Any]:
    """Append a visual asset to visual state, maintaining bounds."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    assets = [
        _normalize_visual_asset(item)
        for item in _safe_list(visual_state.get("visual_assets"))
        if isinstance(item, dict)
    ]

    normalized = _normalize_visual_asset(asset)
    normalized_asset_id = _safe_str(normalized.get("asset_id")).strip()
    normalized_kind = _safe_str(normalized.get("kind")).strip()
    normalized_target_id = _safe_str(normalized.get("target_id")).strip()
    normalized_version = _safe_int(normalized.get("version"), 1)

    deduped = []
    for item in assets:
        same_asset = (
            normalized_asset_id
            and _safe_str(item.get("asset_id")).strip() == normalized_asset_id
        )
        same_slot = (
            _safe_str(item.get("kind")).strip() == normalized_kind
            and _safe_str(item.get("target_id")).strip() == normalized_target_id
            and _safe_int(item.get("version"), 1) == normalized_version
        )
        if same_asset or same_slot:
            continue
        deduped.append(item)

    deduped.append(normalized)
    assets = sorted(
        deduped,
        key=lambda item: (
            _safe_str(item.get("kind")),
            _safe_str(item.get("target_id")),
            _safe_str(item.get("asset_id")),
        ),
    )[-_MAX_VISUAL_ASSETS:]
    visual_state["visual_assets"] = assets
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


def mark_image_request_complete(
    simulation_state: Dict[str, Any],
    *,
    request_id: str,
    asset_id: str,
    image_url: str,
    local_path: str,
) -> Dict[str, Any]:
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    requests = _safe_list(visual_state.get("image_requests"))

    updated = []
    for item in requests:
        data = _safe_dict(item)
        if _safe_str(data.get("request_id")).strip() == _safe_str(request_id).strip():
            data["status"] = "complete"
            data["asset_id"] = asset_id
            data["image_url"] = image_url
            data["local_path"] = local_path
        updated.append(data)

    visual_state["image_requests"] = updated
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


def upsert_appearance_profile(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Upsert an appearance profile for an actor."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    profiles = _safe_dict(visual_state.get("appearance_profiles"))

    profiles[_safe_str(actor_id)] = _normalize_appearance_profile(profile)
    visual_state["appearance_profiles"] = dict(sorted(profiles.items(), key=lambda item: _safe_str(item[0])))
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


def append_appearance_event(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str,
    event: Dict[str, Any],
) -> Dict[str, Any]:
    """Append an appearance event for an actor."""
    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    events = _safe_dict(visual_state.get("appearance_events"))

    actor_events = _safe_list(events.get(actor_id))
    actor_events.append(_normalize_appearance_event(event))
    actor_events = sorted(
        [item for item in actor_events if isinstance(item, dict)],
        key=lambda item: (
            item.get("tick", 0),
            _safe_str(item.get("reason")),
            _safe_str(item.get("event_id")),
        ),
    )[-_MAX_APPEARANCE_EVENTS:]

    events[_safe_str(actor_id)] = actor_events
    visual_state["appearance_events"] = dict(sorted(events.items(), key=lambda item: _safe_str(item[0])))
    presentation_state["visual_state"] = visual_state
    simulation_state["presentation_state"] = presentation_state
    return simulation_state


def build_default_appearance_profile(
    *,
    actor_id: str,
    name: str,
    role: str,
    description: str,
) -> Dict[str, Any]:
    """Build a default appearance profile for an actor."""
    base_description = ", ".join([part for part in [_safe_str(name).strip(), _safe_str(role).strip(), _safe_str(description).strip()] if part])
    return {
        "base_description": base_description,
        "current_summary": base_description,
        "features": {},
        "last_reason": "initial",
        "version": 1,
    }


def build_visual_asset_record(
    *,
    kind: str,
    target_id: str,
    version: int,
    seed: int | None,
    style: str,
    model: str,
    prompt: str,
    url: str,
    local_path: str,
    status: str,
    created_from_request_id: str,
    moderation_status: str = "unchecked",
    moderation_reason: str = "",
) -> Dict[str, Any]:
    """Build a visual asset record with stable asset ID and cache key."""
    asset_id = _stable_asset_id(kind, target_id, version, seed)
    cache_key = f"{kind}|{target_id}|{version}|{seed if isinstance(seed, int) else 'none'}|{style}|{model}"
    return {
        "asset_id": asset_id,
        "kind": kind,
        "target_id": target_id,
        "url": _safe_str(url).strip(),
        "local_path": _safe_str(local_path).strip(),
        "cache_key": cache_key,
        "seed": seed,
        "style": _safe_str(style).strip(),
        "model": _safe_str(model).strip(),
        "prompt": _safe_str(prompt).strip(),
        "version": max(1, int(version)),
        "status": _first_non_empty(status, "complete"),
        "created_from_request_id": _safe_str(created_from_request_id).strip(),
        "moderation": {
            "status": _first_non_empty(moderation_status, "unchecked"),
            "reason": _safe_str(moderation_reason).strip(),
        },
    }


# ---- Phase 12.5 — Request validation / moderation / fallback helpers ----


def validate_visual_prompt(prompt: str) -> Dict[str, Any]:
    """Validate a visual prompt for content and length."""
    prompt = _safe_str(prompt).strip()
    if not prompt:
        return {"ok": False, "status": "blocked", "reason": "empty_prompt"}
    if len(prompt) > 2000:
        return {"ok": False, "status": "blocked", "reason": "prompt_too_long"}
    return {"ok": True, "status": "approved", "reason": ""}


def normalize_visual_status(value: Any, *, default: str = "pending") -> str:
    """Normalize a visual status value to a known set of values."""
    status = _first_non_empty(value, default)
    if status not in {"idle", "pending", "complete", "failed", "blocked"}:
        status = default
    return status


def apply_visual_fallback(identity_or_illustration: Dict[str, Any], fallback_url: str) -> Dict[str, Any]:
    """Apply fallback URL when portrait/image_url is empty."""
    payload = dict(_safe_dict(identity_or_illustration))
    if not _safe_str(payload.get("portrait_url")).strip() and not _safe_str(payload.get("image_url")).strip():
        if "portrait_url" in payload:
            payload["portrait_url"] = _safe_str(fallback_url).strip()
        if "image_url" in payload:
            payload["image_url"] = _safe_str(fallback_url).strip()
    return payload


# NOTE:
# Scene illustrations are presentation artifacts. They may be requested in response
# to important events, but generation itself must remain explicit and external to
# authoritative simulation reducers. Reducers may suggest event IDs/titles, but must
# never depend on image output.