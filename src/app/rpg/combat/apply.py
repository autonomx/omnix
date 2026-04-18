from __future__ import annotations

from typing import Any, Dict

from app.rpg.combat.state import normalize_combat_state


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_attack_resolution(
    simulation_state: Dict[str, Any],
    combat_state: Dict[str, Any],
    resolution: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    combat_state = normalize_combat_state(combat_state)
    target_id = str(resolution.get("target_id") or "")
    hp_after = int(resolution.get("target_hp_after", 0) or 0)

    for collection_key in ("actor_states", "npc_states"):
        collection = simulation_state.get(collection_key) or []
        for actor in collection:
            if str(actor.get("id") or "") != target_id:
                continue
            resources = _safe_dict(actor.get("resources"))
            resources["hp"] = hp_after
            actor["resources"] = resources
            if hp_after <= 0:
                statuses = actor.get("status_effects") or []
                if "downed" not in statuses:
                    statuses.append("downed")
                actor["status_effects"] = statuses

    combat_state["active"] = True
    combat_state["phase"] = "active"
    combat_state["last_resolution"] = dict(resolution)
    recent = list(combat_state.get("recent_events") or [])
    recent.append({
        "type": "attack_resolution",
        "actor_id": resolution.get("actor_id"),
        "target_id": resolution.get("target_id"),
        "hit": bool(resolution.get("hit")),
        "damage_total": int(resolution.get("damage_total", 0) or 0),
        "target_downed": bool(resolution.get("target_downed")),
    })
    combat_state["recent_events"] = recent[-24:]

    if bool(resolution.get("target_downed")):
        combat_state["current_target_id"] = ""

    return simulation_state, combat_state
