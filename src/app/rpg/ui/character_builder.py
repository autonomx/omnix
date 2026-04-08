"""Phase A — Canonical character UI state builder.

Provides deterministic, read-only, presentation-derived character UI state
for frontend character panels.

Design invariants:
- No LLM calls
- No mutation of simulation truth
- No new persistent character state
- Backward-compatible with missing presentation_state, personality_state,
  social_state, ai_state
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

_MAX_RECENT_ACTIONS = 5
_MAX_TRAITS = 8
_MAX_RELATIONSHIPS = 8
_MAX_INVENTORY_ITEMS = 12
_MAX_ACTIVE_QUESTS = 8
_MAX_GOALS = 5
_MAX_BELIEFS = 8
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


def _sorted_dict_items(value: Dict[str, Any]) -> List[Tuple[str, Any]]:
    return sorted(value.items(), key=lambda item: _safe_str(item[0]))


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _derive_character_id(entry: Dict[str, Any], fallback_index: int) -> str:
    return _first_non_empty(
        entry.get("entity_id"),
        entry.get("speaker_id"),
        entry.get("actor_id"),
        entry.get("id"),
        f"character:{fallback_index}",
    )


def _derive_display_name(entry: Dict[str, Any]) -> str:
    return _first_non_empty(
        entry.get("display_name"),
        entry.get("speaker_name"),
        entry.get("name"),
        entry.get("label"),
        "Unknown",
    )


def _derive_role(entry: Dict[str, Any]) -> str:
    return _first_non_empty(
        entry.get("role"),
        entry.get("entity_type"),
        entry.get("speaker_role"),
        "character",
    )


def _normalize_profile(personality_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    profiles = _safe_dict(personality_state.get("profiles"))
    profile = _safe_dict(profiles.get(actor_id))

    style_tags: List[str] = []
    for raw in _safe_list(profile.get("style_tags")):
        value = _safe_str(raw).strip()
        if value:
            style_tags.append(value)

    return {
        "tone": _safe_str(profile.get("tone")).strip(),
        "archetype": _safe_str(profile.get("archetype")).strip(),
        "style_tags": style_tags[:_MAX_TRAITS],
        "summary": _safe_str(profile.get("summary")).strip(),
    }


def _normalize_traits(profile: Dict[str, Any], entry: Dict[str, Any]) -> List[str]:
    raw_traits: List[str] = []

    for key in ("traits", "style_tags", "tags"):
        value = profile.get(key)
        if isinstance(value, list):
            for item in value:
                text = _safe_str(item).strip()
                if text:
                    raw_traits.append(text)

    for key in ("traits", "tags"):
        value = entry.get(key)
        if isinstance(value, list):
            for item in value:
                text = _safe_str(item).strip()
                if text:
                    raw_traits.append(text)

    seen = set()
    deduped: List[str] = []
    for item in raw_traits:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(item)

    return sorted(deduped, key=lambda v: v.lower())[:_MAX_TRAITS]


def _normalize_recent_actions(entry: Dict[str, Any]) -> List[str]:
    recent_actions: List[str] = []
    for raw in _safe_list(entry.get("recent_actions")):
        value = _safe_str(raw).strip()
        if value:
            recent_actions.append(value)
    return recent_actions[:_MAX_RECENT_ACTIONS]


def _normalize_relationships(simulation_state: Dict[str, Any], actor_id: str) -> List[Dict[str, Any]]:
    social_state = _safe_dict(simulation_state.get("social_state"))
    relationships = _safe_dict(social_state.get("relationships"))
    actor_links = _safe_dict(relationships.get(actor_id))

    normalized: List[Dict[str, Any]] = []
    for target_id, payload in _sorted_dict_items(actor_links):
        payload_dict = _safe_dict(payload)
        score = payload_dict.get("score")
        normalized.append(
            {
                "target_id": _safe_str(target_id),
                "kind": _first_non_empty(
                    payload_dict.get("kind"),
                    payload_dict.get("type"),
                    "neutral",
                ),
                "score": score if isinstance(score, (int, float)) else None,
            }
        )

    return normalized[:_MAX_RELATIONSHIPS]


def _normalize_current_intent(
    simulation_state: Dict[str, Any],
    actor_id: str,
    entry: Dict[str, Any],
) -> str:
    direct_intent = _safe_str(entry.get("current_intent")).strip()
    if direct_intent:
        return direct_intent

    ai_state = _safe_dict(simulation_state.get("ai_state"))
    npc_minds = _safe_dict(ai_state.get("npc_minds"))
    actor_mind = _safe_dict(npc_minds.get(actor_id))

    return _first_non_empty(
        actor_mind.get("current_intent"),
        actor_mind.get("goal"),
        actor_mind.get("top_goal"),
    )


def _normalize_card_meta(entry: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "subtitle": _first_non_empty(
            entry.get("title"),
            entry.get("role"),
            profile.get("archetype"),
        ),
        "summary": _first_non_empty(
            entry.get("description"),
            profile.get("summary"),
        ),
        "badge": _first_non_empty(
            entry.get("faction"),
            entry.get("group"),
        ),
    }


def _normalize_actor_memory_block(
    simulation_state: Dict[str, Any],
    actor_id: str,
) -> Dict[str, Any]:
    """Extract actor-specific memory for character UI/inspector."""
    from app.rpg.memory.actor_memory_state import get_actor_memory

    memory = get_actor_memory(simulation_state, actor_id)
    return {
        "short_term": memory.get("short_term", []),
        "long_term": memory.get("long_term", []),
    }


def _normalize_appearance(
    simulation_state: Dict[str, Any],
    actor_id: str,
    entry: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract appearance profile and recent appearance events for a character."""
    from app.rpg.presentation.visual_state import (
        build_default_appearance_profile,
        ensure_visual_state,
    )

    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    profiles = _safe_dict(visual_state.get("appearance_profiles"))
    events = _safe_dict(visual_state.get("appearance_events"))

    profile = _safe_dict(profiles.get(actor_id))
    if not profile:
        profile = build_default_appearance_profile(
            actor_id=actor_id,
            name=_derive_display_name(entry),
            role=_derive_role(entry),
            description=_safe_str(entry.get("description")).strip(),
        )

    appearance_events = _safe_list(events.get(actor_id))
    appearance_events = [item for item in appearance_events if isinstance(item, dict)][-_MAX_APPEARANCE_EVENTS:]

    return {
        "profile": profile,
        "recent_events": appearance_events,
    }


def _normalize_visual_identity(
    simulation_state: Dict[str, Any],
    actor_id: str,
    entry: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    from app.rpg.presentation.visual_state import (
        build_default_character_visual_identity,
        ensure_visual_state,
    )

    simulation_state = ensure_visual_state(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    identities = _safe_dict(visual_state.get("character_visual_identities"))

    actor_identity = _safe_dict(identities.get(actor_id))
    entry_visual = _safe_dict(entry.get("visual_identity"))

    defaults = _safe_dict(visual_state.get("defaults"))
    merged = {
        **build_default_character_visual_identity(
            actor_id=actor_id,
            name=_derive_display_name(entry),
            role=_derive_role(entry),
            description=_safe_str(entry.get("description")).strip(),
            personality_summary=_safe_str(profile.get("summary")).strip(),
            style=_safe_str(defaults.get("portrait_style")).strip(),
            model=_safe_str(defaults.get("model")).strip(),
        ),
        **actor_identity,
        **entry_visual,
    }

    seed = merged.get("seed")
    version = merged.get("version")

    return {
        "portrait_url": _safe_str(merged.get("portrait_url")).strip(),
        "portrait_asset_id": _safe_str(merged.get("portrait_asset_id")).strip(),
        "seed": seed if isinstance(seed, int) else None,
        "style": _safe_str(merged.get("style")).strip(),
        "base_prompt": _safe_str(merged.get("base_prompt")).strip(),
        "model": _safe_str(merged.get("model")).strip(),
        "version": version if isinstance(version, int) and version > 0 else 1,
        "status": _first_non_empty(merged.get("status"), "idle"),
    }


def build_character_ui_entry(
    simulation_state: Dict[str, Any],
    presentation_entry: Dict[str, Any],
    fallback_index: int = 0,
) -> Dict[str, Any]:
    """Build a single canonical character UI entry.

    This is a read-only, deterministic projection from simulation state
    and presentation entry data. No mutation occurs.
    """
    from app.rpg.memory.actor_memory_state import ensure_actor_memory_state

    simulation_state = _safe_dict(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    presentation_entry = _safe_dict(presentation_entry)

    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    personality_state = _safe_dict(presentation_state.get("personality_state"))

    actor_id = _derive_character_id(presentation_entry, fallback_index)
    profile = _normalize_profile(personality_state, actor_id)
    traits = _normalize_traits(profile, presentation_entry)

    speaker_order = presentation_entry.get("speaker_order")
    if not isinstance(speaker_order, int):
        speaker_order = fallback_index

    card_meta = _normalize_card_meta(presentation_entry, profile)
    appearance = _normalize_appearance(simulation_state, actor_id, presentation_entry)

    return {
        "id": actor_id,
        "name": _derive_display_name(presentation_entry),
        "role": _derive_role(presentation_entry),
        "kind": "character",
        "description": _safe_str(presentation_entry.get("description")).strip(),
        "traits": traits,
        "current_intent": _normalize_current_intent(simulation_state, actor_id, presentation_entry),
        "recent_actions": _normalize_recent_actions(presentation_entry),
        "relationships": _normalize_relationships(simulation_state, actor_id),
        "personality": profile,
        "visual_identity": _normalize_visual_identity(simulation_state, actor_id, presentation_entry, profile),
        "appearance": appearance,
        "actor_memory": _normalize_actor_memory_block(simulation_state, actor_id),
        "card": card_meta,
        "meta": {
            "present": bool(presentation_entry.get("present", True)),
            "speaker_order": speaker_order,
            "source": _first_non_empty(
                presentation_entry.get("source"),
                "presentation_state",
            ),
        },
    }


def build_character_ui_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build complete canonical character UI state from simulation state.

    Extracts speaker cards from presentation_state and converts them to
    a deterministic, sorted character list.
    """
    simulation_state = _safe_dict(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    speaker_cards = _safe_list(presentation_state.get("speaker_cards"))

    characters: List[Dict[str, Any]] = []
    for idx, raw_entry in enumerate(speaker_cards):
        entry = _safe_dict(raw_entry)
        if not entry:
            continue
        characters.append(build_character_ui_entry(simulation_state, entry, idx))

    characters = sorted(
        characters,
        key=lambda item: (
            int(_safe_dict(item.get("meta")).get("speaker_order", 0)),
            _safe_str(item.get("name")).lower(),
            _safe_str(item.get("id")),
        ),
    )

    return {
        "characters": characters,
        "count": len(characters),
    }


# ---- Phase 11.2 — Inspector helpers ----


def _normalize_inventory(simulation_state: Dict[str, Any], actor_id: str) -> List[Dict[str, Any]]:
    """Normalize inventory items for a given actor into a stable, bounded list."""
    inventory_state = _safe_dict(simulation_state.get("inventory_state"))
    if isinstance(inventory_state.get("entries"), list):
        items = [e for e in inventory_state["entries"] if _safe_dict(e).get("actor_id") == actor_id]
    else:
        actor_inventory = inventory_state.get(actor_id)
        items = actor_inventory if isinstance(actor_inventory, list) else []

    normalized: List[Dict[str, Any]] = []
    for raw in items:
        item = _safe_dict(raw)
        item_id = _first_non_empty(
            item.get("id"),
            item.get("item_id"),
            item.get("key"),
        )
        if not item_id:
            continue
        normalized.append(
            {
                "id": item_id,
                "name": _first_non_empty(
                    item.get("name"),
                    item.get("label"),
                    item_id,
                ),
                "kind": _first_non_empty(
                    item.get("kind"),
                    item.get("type"),
                    "item",
                ),
                "quantity": item.get("quantity") if isinstance(item.get("quantity"), int) else 1,
            }
        )

    normalized = sorted(
        normalized,
        key=lambda it: (
            _safe_str(it.get("name")).lower(),
            _safe_str(it.get("id")),
        ),
    )
    return normalized[:_MAX_INVENTORY_ITEMS]


def _normalize_goals(simulation_state: Dict[str, Any], actor_id: str) -> List[str]:
    """Extract goals from ai_state.npc_minds for a given actor."""
    ai_state = _safe_dict(simulation_state.get("ai_state"))
    npc_minds = _safe_dict(ai_state.get("npc_minds"))
    actor_mind = _safe_dict(npc_minds.get(actor_id))

    goals: List[str] = []
    for key in ("goals",):
        value = actor_mind.get(key)
        if isinstance(value, list):
            for raw in value:
                text = _safe_str(raw).strip()
                if text:
                    goals.append(text)

    for key in ("top_goal", "goal", "current_intent"):
        text = _safe_str(actor_mind.get(key)).strip()
        if text:
            goals.append(text)

    deduped: List[str] = []
    seen = set()
    for item in goals:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(item)

    return deduped[:_MAX_GOALS]


def _normalize_beliefs(simulation_state: Dict[str, Any], actor_id: str) -> List[Dict[str, Any]]:
    """Extract belief summaries from npc_minds for a given actor."""
    ai_state = _safe_dict(simulation_state.get("ai_state"))
    npc_minds = _safe_dict(ai_state.get("npc_minds"))
    actor_mind = _safe_dict(npc_minds.get(actor_id))

    beliefs = actor_mind.get("beliefs")
    if not isinstance(beliefs, dict):
        return []

    normalized: List[Dict[str, Any]] = []
    for target_id, payload in _sorted_dict_items(beliefs):
        payload_dict = _safe_dict(payload)
        summary_parts: List[str] = []

        for key, value in _sorted_dict_items(payload_dict):
            if isinstance(value, (str, int, float, bool)) and _safe_str(value).strip():
                summary_parts.append(f"{key}={_safe_str(value).strip()}")

        normalized.append(
            {
                "target_id": _safe_str(target_id),
                "summary": ", ".join(summary_parts[:4]),
            }
        )

    return normalized[:_MAX_BELIEFS]


def _normalize_active_quests(simulation_state: Dict[str, Any], actor_id: str) -> List[Dict[str, Any]]:
    """Normalize active quests that involve the given actor."""
    quest_state = _safe_dict(simulation_state.get("quest_state"))
    quests = _safe_list(quest_state.get("quests"))

    normalized: List[Dict[str, Any]] = []
    for raw in quests:
        quest = _safe_dict(raw)
        participants = _safe_list(quest.get("participants"))
        owners = _safe_list(quest.get("owners"))
        assigned_to = _safe_list(quest.get("assigned_to"))

        actor_refs = {_safe_str(v) for v in participants + owners + assigned_to}
        if actor_id not in actor_refs:
            continue

        normalized.append(
            {
                "id": _first_non_empty(
                    quest.get("id"),
                    quest.get("quest_id"),
                ),
                "title": _first_non_empty(
                    quest.get("title"),
                    quest.get("name"),
                    "Untitled Quest",
                ),
                "status": _first_non_empty(
                    quest.get("status"),
                    "active",
                ),
            }
        )

    normalized = sorted(
        normalized,
        key=lambda it: (
            _safe_str(it.get("title")).lower(),
            _safe_str(it.get("id")),
        ),
    )
    return normalized[:_MAX_ACTIVE_QUESTS]


def _normalize_relationship_summary(relationships: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregate relationships into positive/negative/neutral counts."""
    summary = {
        "positive": 0,
        "negative": 0,
        "neutral": 0,
    }

    for item in relationships:
        score = item.get("score")
        if isinstance(score, (int, float)):
            if score > 0:
                summary["positive"] += 1
            elif score < 0:
                summary["negative"] += 1
            else:
                summary["neutral"] += 1
            continue

        kind = _safe_str(item.get("kind")).lower()
        if kind in {"ally", "friendly", "trusted", "positive"}:
            summary["positive"] += 1
        elif kind in {"hostile", "enemy", "negative", "suspicious"}:
            summary["negative"] += 1
        else:
            summary["neutral"] += 1

    return summary


def build_character_inspector_entry(
    simulation_state: Dict[str, Any],
    presentation_entry: Dict[str, Any],
    fallback_index: int = 0,
) -> Dict[str, Any]:
    """Build a canonical character UI entry with inspector details appended."""
    from app.rpg.memory.actor_memory_state import ensure_actor_memory_state

    simulation_state = _safe_dict(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    base = build_character_ui_entry(simulation_state, presentation_entry, fallback_index)
    actor_id = _safe_str(base.get("id"))

    inventory = _normalize_inventory(simulation_state, actor_id)
    goals = _normalize_goals(simulation_state, actor_id)
    beliefs = _normalize_beliefs(simulation_state, actor_id)
    active_quests = _normalize_active_quests(simulation_state, actor_id)
    relationships = _safe_list(base.get("relationships"))

    return {
        **base,
        "inspector": {
            "inventory": inventory,
            "goals": goals,
            "beliefs": beliefs,
            "active_quests": active_quests,
            "relationship_summary": _normalize_relationship_summary(relationships),
            "memory": _normalize_actor_memory_block(simulation_state, actor_id),
        },
    }


def build_character_inspector_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build complete canonical character inspector state from simulation state."""
    simulation_state = _safe_dict(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    speaker_cards = _safe_list(presentation_state.get("speaker_cards"))

    characters: List[Dict[str, Any]] = []
    for idx, raw_entry in enumerate(speaker_cards):
        entry = _safe_dict(raw_entry)
        if not entry:
            continue
        characters.append(build_character_inspector_entry(simulation_state, entry, idx))

    characters = sorted(
        characters,
        key=lambda item: (
            int(_safe_dict(item.get("meta")).get("speaker_order", 0)),
            _safe_str(item.get("name")).lower(),
            _safe_str(item.get("id")),
        ),
    )

    return {
        "characters": characters,
        "count": len(characters),
    }
