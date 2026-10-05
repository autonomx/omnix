"""Phase 8.2 — Encounter Builder.

Builds an encounter state dict from a scene dict and simulation state.
Deterministic participant ordering, encounter type derivation from scene type.

Bounds:
- participants max 12
"""

from __future__ import annotations

from typing import Any, Dict, List


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _participant_from_actor(actor: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Convert an actor dict into a participant dict with deterministic defaults."""
    actor = _safe_dict(actor)
    actor_id = _safe_str(actor.get("id")) or f"actor_{index}"
    faction_position = _safe_dict(actor.get("faction_position"))
    stance = _safe_str(faction_position.get("stance"))

    if actor_id == "player":
        side = "player"
    elif stance == "oppose":
        side = "enemy"
    elif stance == "support":
        side = "ally"
    else:
        side = "neutral"

    # Deterministic initiative: higher index = lower initiative
    initiative = 100 - index
    return {
        "actor_id": actor_id,
        "name": _safe_str(actor.get("name")) or actor_id,
        "side": side,
        "initiative": initiative,
        "hp": 10,
        "max_hp": 10,
        "stress": 0,
        "status_effects": [],
        "can_act": True,
    }


def build_encounter_from_scene(scene: Dict[str, Any], simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build an encounter state from a scene dict.

    Args:
        scene: The scene dict with scene_id, scene_type, actors keys.
        simulation_state: Current simulation state (used for context).

    Returns:
        A new encounter state dict ready for activation.
    """
    scene = _safe_dict(scene)
    simulation_state = _safe_dict(simulation_state)

    scene_id = _safe_str(scene.get("scene_id") or scene.get("id"))
    scene_type = _safe_str(scene.get("scene_type") or scene.get("type"))

    # Derive encounter type from scene type deterministically
    if scene_type in {"conflict", "combat"}:
        encounter_type = "combat"
    elif scene_type in {"political", "negotiation"}:
        encounter_type = "social"
    elif scene_type in {"stealth"}:
        encounter_type = "stealth"
    else:
        encounter_type = "standoff"

    # Build participants from actors (max 12)
    participants = []
    for idx, actor in enumerate(_safe_list(scene.get("actors"))[:12]):
        if isinstance(actor, dict):
            participants.append(_participant_from_actor(actor, idx))
        else:
            participants.append(_participant_from_actor({"id": actor, "name": actor}, idx))

    # Deterministic ordering: sort by (-initiative, actor_id)
    participants.sort(key=lambda p: (-int(p.get("initiative", 0)), _safe_str(p.get("actor_id"))))

    active_actor_id = participants[0]["actor_id"] if participants else ""

    return {
        "active": True,
        "encounter_id": f"enc:{scene_id}",
        "scene_id": scene_id,
        "encounter_type": encounter_type,
        "round": 1,
        "turn_index": 0,
        "active_actor_id": active_actor_id,
        "participants": participants[:12],
        "log": [{
            "round": 1,
            "text": f"Encounter started: {encounter_type}",
            "type": "system",
        }],
        "available_actions": [],
        "status": "active",
    }