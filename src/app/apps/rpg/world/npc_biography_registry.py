"""A character's biography as the campaign's world has it.

The people are the world's (``foundation/state/people.py``: its world model's, and what the session's own index adds):
the engine has none of its own (roadmap §4.4). Someone the world
does not name has a plain biography that claims nothing.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list, safe_str as _safe_str
from app.apps.rpg.foundation.state.people import world_people as _world_people


def _bio(
    *,
    npc_id: str,
    name: str,
    role: str,
    location_id: str,
    short_bio: str,
    personality_traits: List[str],
    speaking_style: Dict[str, Any],
    values: List[str],
    fears: List[str],
    relationships: Dict[str, str],
    knowledge_boundaries: Dict[str, Any],
    secrets: List[Dict[str, Any]] | None = None,
    source: str,
) -> Dict[str, Any]:
    return {
        "npc_id": npc_id,
        "name": name,
        "role": role,
        "location_id": location_id,
        "short_bio": short_bio,
        "personality_traits": list(personality_traits or [])[:8],
        "speaking_style": dict(speaking_style or {}),
        "values": list(values or [])[:8],
        "fears": list(fears or [])[:8],
        "relationships": dict(relationships or {}),
        "knowledge_boundaries": {
            "knows_about": list(_safe_list(_safe_dict(knowledge_boundaries).get("knows_about")))[:16],
            "does_not_know_about": list(_safe_list(_safe_dict(knowledge_boundaries).get("does_not_know_about")))[:16],
            "must_not_claim": list(_safe_list(_safe_dict(knowledge_boundaries).get("must_not_claim")))[:16],
        },
        "secrets": list(secrets or [])[:8],
        "source": source,
    }


_MUST_NOT_CLAIM = ["quest rewards", "hidden locations", "facts not backed by deterministic state"]


def canonical_npc_id(value: Any, simulation_state: Dict[str, Any] | None = None) -> str:
    """The id of the person ``value`` names: an id as given, else the world's person of that name, else ``npc:value``."""
    text = _safe_str(value).strip()
    if not text:
        return ""
    if text.startswith("npc:") or text in _world_people(simulation_state):
        return text
    folded = text.casefold()
    for npc_id, row in _world_people(simulation_state).items():
        if _safe_str(row.get("name")).casefold() == folded:
            return npc_id
    return f"npc:{text}"


def find_npc_biography(npc_id_or_name: Any, simulation_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """The biography of the world's person ``npc_id_or_name`` names, or ``{}`` when the world has no such person."""
    npc_id = canonical_npc_id(npc_id_or_name, simulation_state)
    row = _world_people(simulation_state).get(npc_id)
    if not row:
        return {}
    speech = _safe_str(row.get("speech_style"))
    return _bio(
        npc_id=npc_id,
        name=_safe_str(row.get("name")) or npc_id.replace("npc:", ""),
        role=_safe_str(row.get("role")),
        location_id=_safe_str(row.get("location_id")),
        short_bio=_safe_str(row.get("description") or row.get("biography")),
        personality_traits=[_safe_str(trait) for trait in _safe_list(row.get("personality")) if _safe_str(trait)],
        speaking_style={"tone": speech} if speech else {},
        values=[_safe_str(goal) for goal in _safe_list(row.get("goals")) if _safe_str(goal)],
        fears=[],
        relationships={_safe_str(key): _safe_str(value) for key, value in _safe_dict(row.get("relationships")).items()},
        knowledge_boundaries={"must_not_claim": list(_MUST_NOT_CLAIM)},
        secrets=[{"summary": _safe_str(secret)} for secret in _safe_list(row.get("secrets")) if _safe_str(secret)],
        source="world_npc",
    )
