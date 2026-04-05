"""Phase 3A — World Simulation Engine Core.

Provides deterministic, read-only simulation state management for the
adventure builder.  All functions accept a raw ``setup_payload`` dict
(the same shape the creator routes already traffic) and return plain
dicts suitable for JSON serialization.

Simulation state lives in ``metadata.simulation_state`` so it stays
compatible with the existing creator flow.

Rules are intentionally simple and fully deterministic:

* **Threads** — base pressure 1, +1 per connected faction beyond 1,
  +1 if connected to a hot location.  Capped at 5.
* **Factions** — pressure = count of connected active/critical threads.
  Capped at 5.
* **Locations** — heat = NPCs there + threads connected there.
  Capped at 5.
"""

from __future__ import annotations

import copy
from typing import Any


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

    return {
        "tick": 0,
        "threads": thr_states,
        "factions": fac_states,
        "locations": loc_states,
        "history": [],
    }


def step_simulation_state(setup_payload: dict[str, Any]) -> dict[str, Any]:
    """Advance the simulation by one tick.

    Returns ``{"next_setup": ..., "before_state": ..., "after_state": ...}``.

    If ``metadata.simulation_state`` is missing the initial state is
    computed first.  The updated simulation state is written into a
    *copy* of the setup so the original is never mutated.
    """
    setup = copy.deepcopy(_safe_dict(setup_payload))
    meta = setup.setdefault("metadata", {})

    # Ensure we have a current simulation state
    current = _safe_dict(meta.get("simulation_state"))
    if not current or "tick" not in current:
        current = build_initial_simulation_state(setup)

    before_state = copy.deepcopy(current)
    next_tick = current.get("tick", 0) + 1

    # Recompute pressures/heat for the new tick using current setup data
    fresh = build_initial_simulation_state(setup)

    # The "next" state is the fresh computation with the incremented tick
    after_state: dict[str, Any] = {
        "tick": next_tick,
        "threads": fresh["threads"],
        "factions": fresh["factions"],
        "locations": fresh["locations"],
        "history": list(current.get("history", [])),
    }

    # Build diff + summary and append to history
    diff = compute_simulation_diff(before_state, after_state)
    summary = summarize_simulation_step(diff)
    after_state["history"].append({"tick": next_tick, "summary": summary})
    if len(after_state["history"]) > MAX_HISTORY:
        after_state["history"] = after_state["history"][-MAX_HISTORY:]

    # Write back into setup copy
    meta["simulation_state"] = after_state
    setup["metadata"] = meta

    return {
        "next_setup": setup,
        "before_state": before_state,
        "after_state": after_state,
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


def summarize_simulation_step(diff: dict[str, Any]) -> list[str]:
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

    return lines
