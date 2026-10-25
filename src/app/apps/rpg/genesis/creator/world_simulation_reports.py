"""Diff, summary, and expansion helpers for world simulation."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list


def _faction_status(pressure: int) -> str:
    if pressure >= 4:
        return "volatile"
    if pressure >= 2:
        return "tense"
    return "stable"


def _location_status(heat: int) -> str:
    if heat >= 4:
        return "dangerous"
    if heat >= 2:
        return "active"
    return "quiet"


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
