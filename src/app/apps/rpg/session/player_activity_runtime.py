from __future__ import annotations

from app.runtime.clock import utc_now

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _safe_dict as _safe_dict,
    _safe_str as _safe_str,
)
from app.apps.rpg.foundation.safe_values import safe_list as _safe_list
import hashlib as hashlib
import json as json
from app.apps.rpg.rules.economy.menu_catalog import (
    build_available_transaction_menus as build_available_transaction_menus, build_provider_transaction_menus as build_provider_transaction_menus,
)
from app.apps.rpg.rules.economy.provider_catalog import (
    derive_npc_transaction_providers as derive_npc_transaction_providers, derive_world_transaction_providers as derive_world_transaction_providers,
)
from datetime import (
    datetime as datetime, timezone as timezone,
)
from typing import (
    Any as Any, Dict as Dict, List as List,
)


def _seconds_since_iso(iso_str: str, *, now: datetime | None = None) -> int:
    """Return seconds elapsed since an ISO timestamp. Returns 9999 if invalid."""
    iso_str = _safe_str(iso_str).strip()
    if not iso_str:
        return 9999
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (now or utc_now()) - dt
        return max(0, int(delta.total_seconds()))
    except Exception:
        return 9999


def _derive_transaction_context_tags(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[str]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    tags: list[str] = []
    seen = set()

    def _add(value: Any) -> None:
        text = _safe_str(value).strip().lower()
        if text and text not in seen:
            seen.add(text)
            tags.append(text)

    current_scene = _safe_dict(runtime_state.get("current_scene"))
    scene_tags = _safe_list(current_scene.get("tags"))
    for tag in scene_tags:
        _add(tag)

    for npc in _safe_list(runtime_state.get("npcs"))[:24]:
        npc = _safe_dict(npc)
        role = _safe_str(npc.get("role")).lower()
        profession = _safe_str(npc.get("profession")).lower()
        location_type = _safe_str(npc.get("location_type")).lower()
        _add(role)
        _add(profession)
        _add(location_type)

    scene_kind = _safe_str(current_scene.get("scene_type")).lower()
    _add(scene_kind)

    return tags[:16]


def _derive_transaction_providers(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    npcs = _safe_list(runtime_state.get("npcs"))
    world_entities = _safe_list(runtime_state.get("world_entities"))

    npc_providers = derive_npc_transaction_providers(npcs)
    world_providers = derive_world_transaction_providers(world_entities)

    combined: list[dict[str, Any]] = []
    seen = set()

    for provider in npc_providers + world_providers:
        provider = _safe_dict(provider)
        provider_id = _safe_str(provider.get("provider_id"))
        if not provider_id or provider_id in seen:
            continue
        seen.add(provider_id)
        combined.append(provider)

    return combined[:24]


def _build_transaction_menus_for_state(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[dict[str, Any]]:
    providers = _derive_transaction_providers(simulation_state, runtime_state)
    menus = build_provider_transaction_menus(providers)
    if menus:
        return menus

    # Backward-compatible fallback while world/NPC data matures.
    transaction_context_tags = _derive_transaction_context_tags(simulation_state, runtime_state)
    return build_available_transaction_menus(transaction_context_tags)


# ── World consequence state ──────────────────────────────────────────────────


# ── Active NPC activity state ────────────────────────────────────────────────


# ── Living world activity planner ────────────────────────────────────────────


# ── Activity beats ──────────────────────────────────────────────────────────


__all__ = [
    "_build_transaction_menus_for_state",
    "_derive_transaction_context_tags",
    "_derive_transaction_providers",
    "_seconds_since_iso",
]
