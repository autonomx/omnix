"""Phase 7 — GM Tools for controlled intervention.

Provides:
- Controlled GM intervention helpers
- Pure state mutation helpers
- No Flask imports
"""

from __future__ import annotations

from typing import Any, Dict, List


def _clamp_belief(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _ensure_meta(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure debug_meta and gm_overrides structures exist in simulation state."""
    simulation_state.setdefault("debug_meta", {})
    simulation_state.setdefault("gm_overrides", {})
    simulation_state["debug_meta"].setdefault("last_injected_events", [])
    simulation_state["gm_overrides"].setdefault("forced_faction_positions", {})
    simulation_state["gm_overrides"].setdefault("forced_npc_beliefs", {})
    return simulation_state


def inject_event(
    simulation_state: Dict[str, Any],
    event: Dict[str, Any],
    reason: str = "gm_injection",
) -> Dict[str, Any]:
    """Inject an event into the simulation state with debug metadata."""
    simulation_state = _ensure_meta(dict(simulation_state or {}))
    event = dict(event or {})

    simulation_state.setdefault("events", [])
    simulation_state["events"].append(event)

    simulation_state["debug_meta"]["last_step_reason"] = reason
    simulation_state["debug_meta"]["last_step_tick"] = int(simulation_state.get("tick", 0) or 0)
    simulation_state["debug_meta"]["last_injected_events"] = [dict(event)]
    return simulation_state


def seed_rumor(
    simulation_state: Dict[str, Any],
    rumor: Dict[str, Any],
) -> Dict[str, Any]:
    """Seed a new rumor into the social state."""
    simulation_state = _ensure_meta(dict(simulation_state or {}))
    social_state = simulation_state.setdefault("social_state", {})
    social_state.setdefault("rumors", [])
    social_state["rumors"].append(dict(rumor or {}))
    return simulation_state


def force_alliance(
    simulation_state: Dict[str, Any],
    alliance: Dict[str, Any],
) -> Dict[str, Any]:
    """Force an alliance into the social state."""
    simulation_state = _ensure_meta(dict(simulation_state or {}))
    social_state = simulation_state.setdefault("social_state", {})
    social_state.setdefault("alliances", [])
    social_state["alliances"].append(dict(alliance or {}))
    return simulation_state


def force_faction_position(
    simulation_state: Dict[str, Any],
    faction_id: str,
    position: Dict[str, Any],
) -> Dict[str, Any]:
    """Force a faction's group position and record as GM override."""
    simulation_state = _ensure_meta(dict(simulation_state or {}))
    faction_id = _safe_str(faction_id)
    social_state = simulation_state.setdefault("social_state", {})
    social_state.setdefault("group_positions", {})
    social_state["group_positions"][faction_id] = dict(position or {})
    simulation_state["gm_overrides"]["forced_faction_positions"][faction_id] = dict(position or {})
    return simulation_state


def force_npc_belief(
    simulation_state: Dict[str, Any],
    npc_id: str,
    target_id: str,
    belief_patch: Dict[str, Any],
) -> Dict[str, Any]:
    """Force an NPC's belief about another entity.

    Applies the belief patch to the NPC's beliefs dict, attempting
    to convert numeric values to float where possible.
    """
    simulation_state = _ensure_meta(dict(simulation_state or {}))
    npc_id = _safe_str(npc_id)
    target_id = _safe_str(target_id)

    npc_minds = simulation_state.setdefault("npc_minds", {})
    mind = npc_minds.setdefault(npc_id, {})
    beliefs = mind.setdefault("beliefs", {})
    current = beliefs.setdefault(target_id, {})

    for key, value in sorted((belief_patch or {}).items()):
        try:
            current[key] = _clamp_belief(float(value))
        except Exception:
            current[key] = value

    simulation_state["gm_overrides"]["forced_npc_beliefs"].setdefault(npc_id, {})
    simulation_state["gm_overrides"]["forced_npc_beliefs"][npc_id][target_id] = dict(current)
    return simulation_state


def step_ticks(
    setup_payload: Dict[str, Any],
    step_fn,
    count: int = 1,
) -> Dict[str, Any]:
    """Step the simulation forward by the given count.

    Clamps count to [1, 20] for safety.
    """
    setup_payload = dict(setup_payload or {})
    count = max(1, min(20, int(count or 1)))
    current = setup_payload
    for _ in range(count):
        result = step_fn(current)
        current = result.get("next_setup", result)
    return current
