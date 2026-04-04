"""Phase 8.3 — World Simulation Reducers.

Pure deterministic transformation helpers for background world simulation.
All world-sim logic that mutates simulation state lives here or in
controller helpers — not scattered through the game loop.

Key rules:
- Reducers may derive updates from explicit state and apply deterministic rules.
- Reducers may NOT reach into external controllers, perform side effects,
  or generate random branch choices.
- Every reducer returns ``(updated_state_dict, list_of_effects)``.
"""

from __future__ import annotations

from typing import Any

from .models import (
    SUPPORTED_WORLD_EFFECT_TYPES,
    WorldPressureState,
)


# ------------------------------------------------------------------
# Pressure-level helpers
# ------------------------------------------------------------------

_PRESSURE_ORDER = ("low", "medium", "high", "critical")
_PRESSURE_INDEX = {p: i for i, p in enumerate(_PRESSURE_ORDER)}
_HEAT_ORDER = ("cold", "warm", "hot")
_ACTIVITY_ORDER = ("quiet", "active", "busy")


def _step_up(value: str, order: tuple[str, ...]) -> str:
    """Step a value up one level in an ordered sequence."""
    if value not in order:
        return order[0]
    idx = order.index(value)
    return order[min(idx + 1, len(order) - 1)]


def _step_down(value: str, order: tuple[str, ...]) -> str:
    """Step a value down one level in an ordered sequence."""
    if value not in order:
        return order[0]
    idx = order.index(value)
    return order[max(idx - 1, 0)]


def _escalate_pressure(current: str) -> str:
    """Deterministically raise pressure by one level."""
    idx = _PRESSURE_INDEX.get(current, 0)
    return _PRESSURE_ORDER[min(idx + 1, len(_PRESSURE_ORDER) - 1)]


def _deescalate_pressure(current: str) -> str:
    """Deterministically lower pressure by one level."""
    idx = _PRESSURE_INDEX.get(current, 0)
    return _PRESSURE_ORDER[max(idx - 1, 0)]


# ------------------------------------------------------------------
# Faction drift reducer
# ------------------------------------------------------------------

def reduce_faction_drift(
    current: dict[str, dict],
    seed_context: dict,
) -> tuple[dict[str, dict], list[dict]]:
    """Deterministically update faction drift states.

    Inputs (from seed_context):
    - known_factions: list of faction IDs
    - unresolved_threads: list of thread dicts
    - faction_pressure_map: dict[faction_id, pressure_str]
    - recent_consequences: list of consequence dicts

    Returns: (updated_faction_drift_dict, list_of_effect_dicts)
    """
    updated: dict[str, dict] = {}
    effects: list[dict] = []

    known_factions: list[str] = sorted(seed_context.get("known_factions", []))
    faction_pressure_map: dict[str, str] = seed_context.get("faction_pressure_map", {})
    unresolved_threads: list[dict] = seed_context.get("unresolved_threads", [])
    recent_consequences: list[dict] = seed_context.get("recent_consequences", [])
    tick: int | None = seed_context.get("tick")

    # Count unresolved thread weight per faction  (simple: thread title/id substring match)
    thread_ids = [t.get("thread_id", "") for t in unresolved_threads]
    consequence_count = len(recent_consequences)

    for faction_id in known_factions:
        existing = current.get(faction_id, {})
        momentum = existing.get("momentum", "steady")
        pressure = existing.get("pressure", "low")
        stance_overrides = dict(existing.get("stance_overrides", {}))
        active_goals = list(existing.get("active_goals", []))
        recent_changes = list(existing.get("recent_changes", []))

        # Apply external faction pressure map
        ext_pressure = faction_pressure_map.get(faction_id)
        if ext_pressure and ext_pressure in _PRESSURE_INDEX:
            pressure = ext_pressure

        # Strong unresolved threads → pressure rises
        faction_threads = [t for t in thread_ids if faction_id in t]
        if len(faction_threads) >= 2:
            pressure = _escalate_pressure(pressure)

        # Repeated consequences → defensive momentum
        if consequence_count >= 3:
            if momentum == "assertive":
                momentum = "steady"
            elif momentum == "steady":
                momentum = "defensive"

        # No major threads → de-escalate
        if not faction_threads and not ext_pressure:
            pressure = _deescalate_pressure(pressure)
            if momentum == "defensive":
                momentum = "steady"

        new_state = {
            "faction_id": faction_id,
            "momentum": momentum,
            "pressure": pressure,
            "stance_overrides": stance_overrides,
            "active_goals": active_goals,
            "recent_changes": recent_changes[-10:],
            "metadata": existing.get("metadata", {}),
        }

        # Detect drift
        old_momentum = existing.get("momentum", "steady")
        old_pressure = existing.get("pressure", "low")
        if momentum != old_momentum or pressure != old_pressure:
            effect: dict[str, Any] = {
                "effect_id": f"faction_shift:{faction_id}:{tick}",
                "effect_type": "faction_shift",
                "scope": "faction",
                "target_id": faction_id,
                "payload": {
                    "old_momentum": old_momentum,
                    "new_momentum": momentum,
                    "old_pressure": old_pressure,
                    "new_pressure": pressure,
                },
                "journalable": True,
                "metadata": {},
            }
            effects.append(effect)
            new_state["recent_changes"] = (recent_changes + [effect])[-10:]

        updated[faction_id] = new_state

    return updated, effects


# ------------------------------------------------------------------
# Rumor propagation reducer
# ------------------------------------------------------------------

def reduce_rumor_propagation(
    current: dict[str, dict],
    seed_context: dict,
) -> tuple[dict[str, dict], list[dict]]:
    """Deterministically propagate rumors.

    Inputs (from seed_context):
    - recent_rumors: list of rumor dicts from social state
    - known_locations: list of location IDs
    - tick

    Returns: (updated_rumor_states_dict, list_of_effect_dicts)
    """
    updated: dict[str, dict] = {}
    effects: list[dict] = []

    recent_rumors: list[dict] = seed_context.get("recent_rumors", [])
    known_locations: list[str] = sorted(seed_context.get("known_locations", []))
    tick: int | None = seed_context.get("tick")

    # Seed new rumors from social state
    for rumor in recent_rumors:
        rumor_id = rumor.get("rumor_id", "")
        if not rumor_id:
            continue
        if rumor_id not in current:
            current[rumor_id] = {
                "rumor_id": rumor_id,
                "source_entity_id": rumor.get("source_npc_id"),
                "subject_entity_id": rumor.get("subject_id"),
                "origin_location": rumor.get("location"),
                "current_locations": [rumor.get("location")] if rumor.get("location") else [],
                "reach": 1,
                "heat": "warm",
                "status": "active",
                "metadata": {},
            }

    for rumor_id in sorted(current.keys()):
        item = current[rumor_id]
        state = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        heat = state.get("heat", "cold")
        status = state.get("status", "dormant")
        current_locs: list[str] = list(state.get("current_locations", []))
        reach: int = int(state.get("reach", 0))

        # Plateau and cooling rules:
        # - a rumor may only increase reach up to 3 per propagation lifecycle
        # - if no new relevant seed pressure appears, it cools instead of rising
        relevant_locations = seed_context.get("locations", [])
        has_new_surface = bool(relevant_locations) and (
            state.get("origin_location") in relevant_locations
            or any(loc not in current_locs for loc in relevant_locations)
        )

        if status == "dormant" or heat == "cold":
            # Cooled/dormant rumors try to revive if there's new surface pressure
            if has_new_surface:
                heat = "warm"
                status = "active"
            else:
                state["status"] = "dormant"
                state["heat"] = "cold"
                updated[rumor_id] = state
                continue

        if has_new_surface:
            heat = _step_up(heat, _HEAT_ORDER)
            if reach < 3:
                reach = reach + 1
                # Find a new location to spread to
                spread_to: str | None = None
                for loc in known_locations:
                    if loc not in current_locs:
                        spread_to = loc
                        break
                if spread_to:
                    current_locs.append(spread_to)
                    effect: dict[str, Any] = {
                        "effect_id": f"rumor_spread:{rumor_id}:{tick}",
                        "effect_type": "rumor_spread",
                        "scope": "rumor",
                        "target_id": rumor_id,
                        "payload": {
                            "spread_to": spread_to,
                            "reach": reach,
                        },
                        "journalable": True,
                        "metadata": {},
                    }
                    effects.append(effect)
        else:
            heat = _step_down(heat, _HEAT_ORDER)
            if heat == "cold" and reach > 0:
                reach = reach - 1

        # Determine status
        if reach <= 0 and heat == "cold":
            status = "cooling"
        elif reach >= 3 and heat == "hot":
            status = "plateaued"
        else:
            status = "active"

        state["current_locations"] = current_locs
        state["reach"] = reach
        state["heat"] = heat
        state["status"] = status

        updated[rumor_id] = state

    return updated, effects


# ------------------------------------------------------------------
# Location condition reducer
# ------------------------------------------------------------------

def reduce_location_conditions(
    current: dict[str, dict],
    seed_context: dict,
) -> tuple[dict[str, dict], list[dict]]:
    """Deterministically update location condition overlays.

    Inputs (from seed_context):
    - known_locations: list of location IDs
    - faction_pressure_map: dict[faction_id, pressure]
    - unresolved_threads: list of thread dicts
    - recent_consequences: list of consequence dicts
    - encounter_aftermath: dict with recent encounter info
    - tick

    Returns: (updated_location_conditions_dict, list_of_effect_dicts)
    """
    updated: dict[str, dict] = {}
    effects: list[dict] = []

    known_locations: list[str] = sorted(seed_context.get("known_locations", []))
    recent_consequences: list[dict] = seed_context.get("recent_consequences", [])
    encounter_aftermath: dict = seed_context.get("encounter_aftermath", {})
    faction_pressure_map: dict[str, str] = seed_context.get("faction_pressure_map", {})
    tick: int | None = seed_context.get("tick")

    # Compute per-location signals
    consequence_count = len(recent_consequences)
    has_encounter = bool(encounter_aftermath.get("mode"))

    for location_id in known_locations:
        existing = current.get(location_id, {})
        conditions: list[str] = list(existing.get("conditions", []))
        pressure = existing.get("pressure", "low")
        activity_level = existing.get("activity_level", "normal")

        old_conditions = list(conditions)
        old_pressure = pressure

        # Conflict-heavy → tense
        if consequence_count >= 2 and "tense" not in conditions:
            conditions.append("tense")

        # Encounter aftermath at active location → guarded
        active_location = seed_context.get("active_scene_location")
        if has_encounter and location_id == active_location and "guarded" not in conditions:
            conditions.append("guarded")

        # High faction pressure → pressure rises
        high_pressure_factions = [
            f for f, p in faction_pressure_map.items()
            if _PRESSURE_INDEX.get(p, 0) >= 2
        ]
        if high_pressure_factions:
            pressure = _escalate_pressure(pressure)

        # No recent activity → calm
        if consequence_count == 0 and not has_encounter:
            pressure = _deescalate_pressure(pressure)
            if "tense" in conditions:
                conditions.remove("tense")
            if "calm" not in conditions and not conditions:
                conditions.append("calm")

        # Trim conditions to bounded set
        conditions = conditions[:5]

        new_state = {
            "location_id": location_id,
            "conditions": conditions,
            "pressure": pressure,
            "activity_level": activity_level,
            "active_flags": list(existing.get("active_flags", [])),
            "metadata": existing.get("metadata", {}),
        }

        if conditions != old_conditions or pressure != old_pressure:
            effects.append({
                "effect_id": f"location_condition_changed:{location_id}:{tick}",
                "effect_type": "location_condition_changed",
                "scope": "location",
                "target_id": location_id,
                "payload": {
                    "old_conditions": old_conditions,
                    "new_conditions": conditions,
                    "old_pressure": old_pressure,
                    "new_pressure": pressure,
                },
                "journalable": True,
                "metadata": {},
            })

        updated[location_id] = new_state

    return updated, effects


# ------------------------------------------------------------------
# NPC activity reducer
# ------------------------------------------------------------------

def reduce_npc_activities(
    current: dict[str, dict],
    seed_context: dict,
) -> tuple[dict[str, dict], list[dict]]:
    """Deterministically update NPC background activity overlays.

    Inputs (from seed_context):
    - scene_entities: list of entity IDs
    - known_locations: list of location IDs
    - faction_pressure_map: dict
    - location_pressure: dict[location_id, pressure]
    - tick

    Returns: (updated_npc_activities_dict, list_of_effect_dicts)
    """
    updated: dict[str, dict] = {}
    effects: list[dict] = []

    scene_entities: list[str] = sorted(seed_context.get("scene_entities", []))
    location_pressure: dict[str, str] = seed_context.get("location_pressure", {})
    active_location: str | None = seed_context.get("active_scene_location")
    tick: int | None = seed_context.get("tick")

    # Deterministic activity mapping based on pressure
    _PRESSURE_ACTIVITY = {
        "critical": "patrolling",
        "high": "searching",
        "medium": "watchful",
        "low": "idle",
    }

    for entity_id in scene_entities:
        if entity_id == "player":
            continue

        existing = current.get(entity_id, {})
        old_activity = existing.get("activity", "idle")
        location = existing.get("current_location") or active_location

        # Derive activity from location pressure
        loc_pressure = location_pressure.get(location, "low") if location else "low"
        new_activity = _PRESSURE_ACTIVITY.get(loc_pressure, "idle")

        new_state = {
            "entity_id": entity_id,
            "current_location": location,
            "activity": new_activity,
            "visibility": existing.get("visibility", "unknown"),
            "status": existing.get("status", "normal"),
            "last_update_tick": tick,
            "metadata": existing.get("metadata", {}),
        }

        if new_activity != old_activity:
            effects.append({
                "effect_id": f"npc_activity_changed:{entity_id}:{tick}",
                "effect_type": "npc_activity_changed",
                "scope": "npc",
                "target_id": entity_id,
                "payload": {
                    "old_activity": old_activity,
                    "new_activity": new_activity,
                    "location": location,
                },
                "journalable": False,
                "metadata": {},
            })

        updated[entity_id] = new_state

    return updated, effects


# ------------------------------------------------------------------
# World pressure reducer
# ------------------------------------------------------------------

def reduce_world_pressure(
    current: WorldPressureState,
    seed_context: dict,
) -> tuple[WorldPressureState, list[dict]]:
    """Deterministically update aggregate world pressure.

    Inputs (from seed_context):
    - unresolved_threads: list of thread dicts
    - faction_drift: dict of faction drift states
    - location_conditions: dict of location condition states
    - recent_consequences: list
    - encounter_aftermath: dict
    - tick

    Returns: (updated_WorldPressureState, list_of_effect_dicts)
    """
    effects: list[dict] = []

    unresolved_threads: list[dict] = seed_context.get("unresolved_threads", [])
    faction_drift: dict[str, dict] = seed_context.get("faction_drift_current", {})
    location_conditions: dict[str, dict] = seed_context.get("location_conditions_current", {})
    recent_consequences: list[dict] = seed_context.get("recent_consequences", [])
    encounter_aftermath: dict = seed_context.get("encounter_aftermath", {})
    tick: int | None = seed_context.get("tick")

    # Thread pressure: unresolved → rises, not present → cools
    active_thread_ids: set[str] = set()
    for thread in unresolved_threads:
        tid = thread.get("thread_id", "")
        if tid:
            active_thread_ids.add(tid)

    old_thread_pressure = dict(current.pressure_by_thread)
    new_thread_pressure: dict[str, str] = {}

    # Escalate active threads
    for tid in sorted(active_thread_ids):
        old_p = old_thread_pressure.get(tid, "low")
        new_thread_pressure[tid] = _escalate_pressure(old_p)

    # Cool unreinforced threads
    for tid in sorted(old_thread_pressure.keys()):
        if tid not in active_thread_ids:
            new_thread_pressure[tid] = _deescalate_pressure(old_thread_pressure[tid])

    # Encounter aftermath can spike local pressure
    if encounter_aftermath.get("mode"):
        enc_location = encounter_aftermath.get("location")
        if enc_location:
            loc_p = new_thread_pressure.get(enc_location, "low")
            new_thread_pressure[enc_location] = _escalate_pressure(loc_p)

    # Faction pressure: active → keep, unreinforced → cool
    active_faction_ids: set[str] = set(faction_drift.keys())
    old_faction_pressure = dict(current.pressure_by_faction)
    new_faction_pressure: dict[str, str] = {}
    for fid in sorted(active_faction_ids):
        fstate = faction_drift.get(fid, {})
        new_faction_pressure[fid] = fstate.get("pressure", "low")
    for fid in sorted(old_faction_pressure.keys()):
        if fid not in active_faction_ids:
            new_faction_pressure[fid] = _deescalate_pressure(old_faction_pressure[fid])

    # Location pressure: active → keep, unreinforced → cool
    active_location_ids: set[str] = set(location_conditions.keys())
    old_location_pressure = dict(current.pressure_by_location)
    new_location_pressure: dict[str, str] = {}
    for lid in sorted(active_location_ids):
        lstate = location_conditions.get(lid, {})
        new_location_pressure[lid] = lstate.get("pressure", "low")
    for lid in sorted(old_location_pressure.keys()):
        if lid not in active_location_ids:
            new_location_pressure[lid] = _deescalate_pressure(old_location_pressure[lid])

    # Detect overall change
    if (
        new_thread_pressure != old_thread_pressure
        or new_faction_pressure != dict(current.pressure_by_faction)
        or new_location_pressure != dict(current.pressure_by_location)
    ):
        effects.append({
            "effect_id": f"thread_pressure_changed:{tick}",
            "effect_type": "thread_pressure_changed",
            "scope": "world",
            "target_id": None,
            "payload": {
                "thread_count": len(active_thread_ids),
                "consequence_count": len(recent_consequences),
            },
            "journalable": False,
            "metadata": {},
        })

    updated = WorldPressureState(
        active_threads=list(active_thread_ids),
        pressure_by_thread=new_thread_pressure,
        pressure_by_location=new_location_pressure,
        pressure_by_faction=new_faction_pressure,
        metadata=dict(current.metadata),
    )

    return updated, effects


# ------------------------------------------------------------------
# Trace builder
# ------------------------------------------------------------------

def build_world_sim_trace(
    seed_context: dict,
    faction_effects: list[dict],
    rumor_effects: list[dict],
    location_effects: list[dict],
    npc_effects: list[dict],
    pressure_effects: list[dict],
    tick: int | None = None,
) -> dict:
    """Build a debug-friendly trace of the simulation step."""
    return {
        "tick": tick,
        "seed_keys": sorted(seed_context.keys()),
        "faction_effect_count": len(faction_effects),
        "rumor_effect_count": len(rumor_effects),
        "location_effect_count": len(location_effects),
        "npc_effect_count": len(npc_effects),
        "pressure_effect_count": len(pressure_effects),
        "total_effects": (
            len(faction_effects)
            + len(rumor_effects)
            + len(location_effects)
            + len(npc_effects)
            + len(pressure_effects)
        ),
    }
