"""Phase 3A — World Simulation Engine Core.

Provides deterministic, stateful simulation state management for the
adventure builder.  All functions accept a raw ``setup_payload`` dict
(the same shape the creator routes already traffic) and return plain
dicts suitable for JSON serialization.

Simulation state lives in ``metadata.simulation_state`` so it stays
compatible with the existing creator flow.

Rules are intentionally simple and fully deterministic with **stateful
pressure evolution**: values step up or down from their previous state
rather than being recomputed from scratch each tick.

* **Threads** — base pressure steps up if connected to multiple factions
  or a hot location; steps down otherwise.  Capped at 0-5.
* **Factions** — pressure steps up if any connected threads are active;
  steps down otherwise.  Capped at 0-5.
* **Locations** — heat steps up if NPCs or threads present; steps down
  otherwise.  Faction pressure >= 3 also pushes heat up.  Capped at 0-5.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .world_events import generate_world_events, generate_consequences
from .world_effects import (
    apply_effects_to_simulation_state,
    build_effects_from_consequences,
    compute_effect_diff,
    decay_active_effects,
    merge_active_effects,
)
from .world_incidents import (
    compute_incident_diff,
    compute_policy_reaction_diff,
    decay_incidents,
    generate_policy_reactions,
    merge_incidents,
    spawn_incidents_from_state_diff,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HISTORY = 20
PRESSURE_CAP = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _cap(value: int, lo: int = 0, hi: int = PRESSURE_CAP) -> int:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))


def _step_up(v: int) -> int:
    """Increment pressure by one level, capped at 5."""
    return _cap(v + 1)


def _step_down(v: int) -> int:
    """Decrement pressure by one level, floored at 0."""
    return _cap(v - 1)


def _thread_status(pressure: int) -> str:
    if pressure <= 1:
        return "low"
    if pressure <= 3:
        return "active"
    return "critical"


def _faction_status(pressure: int) -> str:
    if pressure == 0:
        return "stable"
    if pressure <= 2:
        return "watchful"
    return "strained"


def _location_status(heat: int) -> str:
    if heat <= 1:
        return "quiet"
    if heat <= 3:
        return "active"
    return "hot"


# ---------------------------------------------------------------------------
# Payload introspection helpers
# ---------------------------------------------------------------------------


def _extract_threads(setup: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the regenerated threads from setup metadata."""
    meta = _safe_dict(setup.get("metadata"))
    return _safe_list(meta.get("regenerated_threads"))


def _extract_factions(setup: dict[str, Any]) -> list[dict[str, Any]]:
    return _safe_list(setup.get("factions"))


def _extract_locations(setup: dict[str, Any]) -> list[dict[str, Any]]:
    return _safe_list(setup.get("locations"))


def _extract_npcs(setup: dict[str, Any]) -> list[dict[str, Any]]:
    return _safe_list(setup.get("npc_seeds"))


# ---------------------------------------------------------------------------
# Simulation state builders
# ---------------------------------------------------------------------------


def build_initial_simulation_state(setup_payload: dict[str, Any]) -> dict[str, Any]:
    """Create a fresh tick-0 simulation state from the setup payload.

    Reads threads, factions, locations, and NPCs to compute initial
    pressures and heat values.
    """
    setup = _safe_dict(setup_payload)

    threads = _extract_threads(setup)
    factions = _extract_factions(setup)
    locations = _extract_locations(setup)
    npcs = _extract_npcs(setup)

    # Build lookup structures
    faction_ids = {f.get("faction_id") for f in factions if f.get("faction_id")}
    location_ids = {loc.get("location_id") for loc in locations if loc.get("location_id")}

    # NPC → location map
    npc_location_map: dict[str, list[str]] = {}
    for npc in npcs:
        loc_id = npc.get("location_id")
        if loc_id and loc_id in location_ids:
            npc_location_map.setdefault(loc_id, []).append(npc.get("npc_id", ""))

    # Thread → faction / location maps
    thread_faction_map: dict[str, list[str]] = {}  # thread_id → [faction_ids]
    thread_location_map: dict[str, list[str]] = {}  # thread_id → [location_ids]
    location_thread_count: dict[str, int] = {}  # location_id → thread count

    for thr in threads:
        tid = thr.get("thread_id", "")
        fac_ids = [
            fid for fid in _safe_list(thr.get("faction_ids"))
            if fid and fid in faction_ids
        ]
        loc_ids = [
            lid for lid in _safe_list(thr.get("location_ids"))
            if lid and lid in location_ids
        ]
        thread_faction_map[tid] = fac_ids
        thread_location_map[tid] = loc_ids
        for lid in loc_ids:
            location_thread_count[lid] = location_thread_count.get(lid, 0) + 1

    # --- Compute location heat first (needed by thread pressure) ---
    loc_states: dict[str, dict[str, Any]] = {}
    for loc in locations:
        lid = loc.get("location_id", "")
        if not lid:
            continue
        npc_count = len(npc_location_map.get(lid, []))
        thread_count = location_thread_count.get(lid, 0)
        heat = _cap(npc_count + thread_count)
        loc_states[lid] = {"heat": heat, "status": _location_status(heat)}

    # --- Compute thread pressure ---
    thr_states: dict[str, dict[str, Any]] = {}
    for thr in threads:
        tid = thr.get("thread_id", "")
        if not tid:
            continue
        fac_count = len(thread_faction_map.get(tid, []))
        pressure = 1  # base
        if fac_count > 1:
            pressure += fac_count - 1
        # +1 if connected to any hot location
        for lid in thread_location_map.get(tid, []):
            loc_st = loc_states.get(lid, {})
            if loc_st.get("status") == "hot":
                pressure += 1
                break
        pressure = _cap(pressure)
        thr_states[tid] = {"pressure": pressure, "status": _thread_status(pressure)}

    # --- Compute faction pressure ---
    # Build reverse map: faction_id → list of thread statuses
    faction_thread_statuses: dict[str, list[str]] = {}
    for tid, fac_ids in thread_faction_map.items():
        thr_st = thr_states.get(tid, {})
        for fid in fac_ids:
            faction_thread_statuses.setdefault(fid, []).append(
                thr_st.get("status", "low")
            )

    fac_states: dict[str, dict[str, Any]] = {}
    for fac in factions:
        fid = fac.get("faction_id", "")
        if not fid:
            continue
        active_critical = sum(
            1 for s in faction_thread_statuses.get(fid, [])
            if s in ("active", "critical")
        )
        pressure = _cap(active_critical)
        fac_states[fid] = {"pressure": pressure, "status": _faction_status(pressure)}

    after_state = {
        "tick": 0,
        "threads": thr_states,
        "factions": fac_states,
        "locations": loc_states,
        "history": [],
        "events": [],
        "consequences": [],
        "active_effects": [],
        "incidents": [],
        "policy_reactions": [],
    }
    after_state["step_hash"] = _step_hash({
        "tick": 0,
        "threads": thr_states,
        "factions": fac_states,
        "locations": loc_states,
        "active_effects": [],
        "incidents": [],
    })
    return after_state


def step_simulation_state(setup_payload: dict[str, Any]) -> dict[str, Any]:
    """Advance the simulation by one tick.

    Returns ``{"next_setup": ..., "before_state": ..., "after_state": ...}``.

    If ``metadata.simulation_state`` is missing the initial state is
    computed first.  The updated simulation state is written into a
    *copy* of the setup so the original is never mutated.

    Uses **stateful pressure evolution**: each entity's pressure/heat
    steps up or down from its previous value based on current conditions,
    rather than being recomputed from scratch.
    """
    setup = copy.deepcopy(_safe_dict(setup_payload))
    meta = setup.setdefault("metadata", {})

    # Ensure we have a current simulation state
    current = _safe_dict(meta.get("simulation_state"))
    if not current or "tick" not in current:
        current = build_initial_simulation_state(setup)

    before_state = copy.deepcopy(current)
    before_effects = _safe_list(current.get("active_effects"))
    before_incidents = _safe_list(current.get("incidents"))
    before_reactions = _safe_list(current.get("policy_reactions"))
    next_tick = current.get("tick", 0) + 1

    # Extract current setup data for condition evaluation
    threads = _extract_threads(setup)
    factions = _extract_factions(setup)
    locations = _extract_locations(setup)
    npcs = _extract_npcs(setup)

    # Build lookup structures
    faction_ids = {f.get("faction_id") for f in factions if f.get("faction_id")}
    location_ids = {loc.get("location_id") for loc in locations if loc.get("location_id")}

    # NPC → location map
    npc_location_map: dict[str, list[str]] = {}
    for npc in npcs:
        loc_id = npc.get("location_id")
        if loc_id and loc_id in location_ids:
            npc_location_map.setdefault(loc_id, []).append(npc.get("npc_id", ""))

    # Thread → faction / location maps
    thread_faction_map: dict[str, list[str]] = {}
    thread_location_map: dict[str, list[str]] = {}
    location_thread_count: dict[str, int] = {}

    for thr in threads:
        tid = thr.get("thread_id", "")
        fac_ids = [
            fid for fid in _safe_list(thr.get("faction_ids"))
            if fid and fid in faction_ids
        ]
        loc_ids = [
            lid for lid in _safe_list(thr.get("location_ids"))
            if lid and lid in location_ids
        ]
        thread_faction_map[tid] = fac_ids
        thread_location_map[tid] = loc_ids
        for lid in loc_ids:
            location_thread_count[lid] = location_thread_count.get(lid, 0) + 1

    # Build reverse map: faction_id → list of connected thread_ids
    faction_thread_map: dict[str, list[str]] = {}
    for tid, fac_ids in thread_faction_map.items():
        for fid in fac_ids:
            faction_thread_map.setdefault(fid, []).append(tid)

    # Get previous states for stateful evolution
    prev_threads = _safe_dict(current.get("threads"))
    prev_factions = _safe_dict(current.get("factions"))
    prev_locations = _safe_dict(current.get("locations"))

    # --- Step 1: Compute location heat with stateful evolution ---
    loc_states: dict[str, dict[str, Any]] = {}
    for loc in locations:
        lid = loc.get("location_id", "")
        if not lid:
            continue
        npc_count = len(npc_location_map.get(lid, []))
        thread_count = location_thread_count.get(lid, 0)
        prev_heat = prev_locations.get(lid, {}).get("heat", 0)

        if npc_count + thread_count > 0:
            heat = _step_up(prev_heat)
        else:
            heat = _step_down(prev_heat)

        loc_states[lid] = {"heat": heat, "status": _location_status(heat)}

    # --- Step 2: Compute thread pressure with stateful evolution ---
    thr_states: dict[str, dict[str, Any]] = {}
    for thr in threads:
        tid = thr.get("thread_id", "")
        if not tid:
            continue
        fac_count = len(thread_faction_map.get(tid, []))
        prev_pressure = prev_threads.get(tid, {}).get("pressure", 1)

        # Determine escalation conditions
        delta = 0
        if fac_count > 1:
            delta += 1
        # +1 if connected to any hot location
        location_is_hot = False
        for lid in thread_location_map.get(tid, []):
            loc_st = loc_states.get(lid, {})
            if loc_st.get("status") == "hot":
                location_is_hot = True
                delta += 1
                break

        if delta > 0:
            pressure = _step_up(prev_pressure)
        else:
            pressure = _step_down(prev_pressure)

        thr_states[tid] = {"pressure": pressure, "status": _thread_status(pressure)}

    # --- Step 3: Compute faction pressure with stateful evolution ---
    fac_states: dict[str, dict[str, Any]] = {}
    for fac in factions:
        fid = fac.get("faction_id", "")
        if not fid:
            continue
        active_thread_ids = faction_thread_map.get(fid, [])
        active_threads_count = len(active_thread_ids)
        prev_pressure = prev_factions.get(fid, {}).get("pressure", 0)

        if active_threads_count > 0:
            pressure = _step_up(prev_pressure)
        else:
            pressure = _step_down(prev_pressure)

        fac_states[fid] = {"pressure": pressure, "status": _faction_status(pressure)}

    # --- Step 4: Faction → location feedback loop ---
    # If faction_pressure >= 3, push heat up on connected locations
    for fid, fstate in fac_states.items():
        faction_pressure = fstate.get("pressure", 0)
        if faction_pressure >= 3:
            # Find locations connected to this faction's threads
            for tid in faction_thread_map.get(fid, []):
                for lid in thread_location_map.get(tid, []):
                    if lid in loc_states:
                        loc_states[lid]["heat"] = _step_up(loc_states[lid]["heat"])
                        loc_states[lid]["status"] = _location_status(loc_states[lid]["heat"])

    # Build after_state
    after_state: dict[str, Any] = {
        "tick": next_tick,
        "threads": thr_states,
        "factions": fac_states,
        "locations": loc_states,
        "history": list(current.get("history", [])),
    }

    # 1. Compute BASE diff (natural changes only, no effects)
    base_diff = compute_simulation_diff(before_state, after_state)
    events = generate_world_events(base_diff)
    consequences = generate_consequences(events)

    # 2. Build/merge/decay active effects.
    new_effects = build_effects_from_consequences(consequences)
    merged_effects = merge_active_effects(before_effects, new_effects)
    after_effects = decay_active_effects(merged_effects)
    after_state["active_effects"] = after_effects

    # 3. Apply effects separately (clean layering)
    after_state_with_effects = apply_effects_to_simulation_state(copy.deepcopy(after_state))

    effect_applied_diff = compute_simulation_diff(after_state, after_state_with_effects)
    final_diff = compute_simulation_diff(before_state, after_state_with_effects)
    effect_diff = compute_effect_diff(before_effects, after_effects)

    # 4. Spawn incidents and policy reactions from the updated state diff.
    new_incidents = spawn_incidents_from_state_diff(final_diff)
    merged_incidents = merge_incidents(before_incidents, new_incidents)
    after_incidents = decay_incidents(merged_incidents)
    after_state_with_effects["incidents"] = after_incidents

    after_reactions = generate_policy_reactions(final_diff)
    after_state_with_effects["policy_reactions"] = after_reactions

    incident_diff = compute_incident_diff(before_incidents, after_incidents)
    reaction_diff = compute_policy_reaction_diff(before_reactions, after_reactions)

    summary = summarize_simulation_step(
        final_diff,
        events=events,
        consequences=consequences,
        effect_diff=effect_diff,
        incident_diff=incident_diff,
        reaction_diff=reaction_diff,
    )

    # Use base_after state for history, but record final_diff for change counts
    history_state = after_state_with_effects
    history_state["history"] = list(current.get("history", []))
    history_state["history"].append({
        "tick": next_tick,
        "summary": summary,
        "changes": {
            "threads": len(final_diff.get("threads_changed", [])),
            "factions": len(final_diff.get("factions_changed", [])),
            "locations": len(final_diff.get("locations_changed", [])),
            "events": len(events),
            "consequences": len(consequences),
            "effects": len(_safe_list(effect_diff.get("added"))),
            "incidents": len(_safe_list(incident_diff.get("added"))),
            "reactions": len(_safe_list(reaction_diff.get("added"))),
        },
    })
    if len(history_state["history"]) > MAX_HISTORY:
        history_state["history"] = history_state["history"][-MAX_HISTORY:]

    # Add step hash for traceability (on final state with effects)
    history_state["step_hash"] = _step_hash({
        "tick": history_state["tick"],
        "threads": history_state["threads"],
        "factions": history_state["factions"],
        "locations": history_state["locations"],
        "active_effects": history_state.get("active_effects", []),
        "incidents": history_state.get("incidents", []),
    })
    history_state["events"] = events
    history_state["consequences"] = consequences

    # Write back into setup copy (final state with effects applied)
    meta["simulation_state"] = history_state
    setup["metadata"] = meta

    return {
        "next_setup": setup,
        "before_state": before_state,
        "after_state": history_state,
        "after_state_base": after_state,
        "simulation_diff": final_diff,
        "base_diff": base_diff,
        "effect_applied_diff": effect_applied_diff,
        "summary": summary,
        "events": events,
        "consequences": consequences,
        "effect_diff": effect_diff,
        "incident_diff": incident_diff,
        "reaction_diff": reaction_diff,
    }


# ---------------------------------------------------------------------------
# Diff & summary
# ---------------------------------------------------------------------------


def compute_simulation_diff(
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> dict[str, Any]:
    """Return a structured diff between two simulation states."""
    before = _safe_dict(before_state)
    after = _safe_dict(after_state)

    def _entity_changes(
        before_map: dict[str, Any],
        after_map: dict[str, Any],
        key_field: str,
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        all_ids = sorted(set(list(before_map.keys()) + list(after_map.keys())))
        for eid in all_ids:
            b = _safe_dict(before_map.get(eid))
            a = _safe_dict(after_map.get(eid))
            if b.get(key_field) != a.get(key_field):
                changes.append({
                    "id": eid,
                    "before": {key_field: b.get(key_field, 0)},
                    "after": {key_field: a.get(key_field, 0)},
                })
        return changes

    return {
        "tick_before": before.get("tick", 0),
        "tick_after": after.get("tick", 0),
        "threads_changed": _entity_changes(
            _safe_dict(before.get("threads")),
            _safe_dict(after.get("threads")),
            "pressure",
        ),
        "factions_changed": _entity_changes(
            _safe_dict(before.get("factions")),
            _safe_dict(after.get("factions")),
            "pressure",
        ),
        "locations_changed": _entity_changes(
            _safe_dict(before.get("locations")),
            _safe_dict(after.get("locations")),
            "heat",
        ),
    }


def _step_hash(state: dict[str, Any]) -> str:
    """Compute a stable hash of the simulation state for traceability."""
    # Exclude history and step_hash itself to keep hash stable
    stable = {
        "tick": state.get("tick"),
        "threads": state.get("threads", {}),
        "factions": state.get("factions", {}),
        "locations": state.get("locations", {}),
    }
    try:
        s = json.dumps(stable, sort_keys=True)
        return hashlib.sha1(s.encode()).hexdigest()[:8]
    except Exception:
        return "00000000"


def summarize_simulation_step(
    diff: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
    consequences: list[dict[str, Any]] | None = None,
    effect_diff: dict[str, Any] | None = None,
    incident_diff: dict[str, Any] | None = None,
    reaction_diff: dict[str, Any] | None = None,
) -> list[str]:
    """Return human-readable summary lines for the diff."""
    diff = _safe_dict(diff)
    lines: list[str] = []

    # Threads
    thr_changes = _safe_list(diff.get("threads_changed"))
    if thr_changes:
        escalated = sum(
            1 for c in thr_changes
            if c.get("after", {}).get("pressure", 0) > c.get("before", {}).get("pressure", 0)
        )
        deescalated = sum(
            1 for c in thr_changes
            if c.get("after", {}).get("pressure", 0) < c.get("before", {}).get("pressure", 0)
        )
        if escalated:
            lines.append(f"{escalated} thread{'s' if escalated != 1 else ''} escalated")
        if deescalated:
            lines.append(f"{deescalated} thread{'s' if deescalated != 1 else ''} de-escalated")

    # Factions — group by resulting status
    fac_changes = _safe_list(diff.get("factions_changed"))
    if fac_changes:
        fac_by_status: dict[str, int] = {}
        for c in fac_changes:
            after_p = c.get("after", {}).get("pressure", 0)
            status = _faction_status(after_p)
            fac_by_status[status] = fac_by_status.get(status, 0) + 1
        for status, count in sorted(fac_by_status.items()):
            lines.append(f"{count} faction{'s' if count != 1 else ''} became {status}")

    # Locations — group by resulting status
    loc_changes = _safe_list(diff.get("locations_changed"))
    if loc_changes:
        loc_by_status: dict[str, int] = {}
        for c in loc_changes:
            after_h = c.get("after", {}).get("heat", 0)
            status = _location_status(after_h)
            loc_by_status[status] = loc_by_status.get(status, 0) + 1
        for status, count in sorted(loc_by_status.items()):
            lines.append(f"{count} location{'s' if count != 1 else ''} became {status}")

    evt_count = len(_safe_list(events))
    if evt_count:
        lines.append(f"{evt_count} world event{'s' if evt_count != 1 else ''} generated")

    cnsq_count = len(_safe_list(consequences))
    if cnsq_count:
        lines.append(f"{cnsq_count} consequence{'s' if cnsq_count != 1 else ''} generated")

    eff_added = len(_safe_list(_safe_dict(effect_diff).get("added")))
    eff_removed = len(_safe_list(_safe_dict(effect_diff).get("removed")))
    if eff_added:
        lines.append(f"{eff_added} active effect{'s' if eff_added != 1 else ''} added")
    if eff_removed:
        lines.append(f"{eff_removed} active effect{'s' if eff_removed != 1 else ''} expired")

    inc_added = len(_safe_list(_safe_dict(incident_diff).get("added")))
    inc_removed = len(_safe_list(_safe_dict(incident_diff).get("removed")))
    if inc_added:
        lines.append(f"{inc_added} incident{'s' if inc_added != 1 else ''} spawned")
    if inc_removed:
        lines.append(f"{inc_removed} incident{'s' if inc_removed != 1 else ''} resolved")

    rxn_added = len(_safe_list(_safe_dict(reaction_diff).get("added")))
    if rxn_added:
        lines.append(f"{rxn_added} policy reaction{'s' if rxn_added != 1 else ''} triggered")
    return lines
