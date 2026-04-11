"""World Events view builder.

Constructs a structured view of local, global, and director-pressure events
for the frontend World Events panel.

Simulation truth stays in simulation_state.  This module produces
**presentation data only** — never written back as simulation authority.

Deterministic ordering everywhere: (scope_order, -priority, tick, event_id).
Hard-capped per section.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

_MAX_LOCAL = 12
_MAX_GLOBAL = 12
_MAX_DIRECTOR = 12
_MAX_RECENT = 12
_MAX_PLAYER_WORLD_VIEW_ROWS = 8

_SCOPE_ORDER = {"local": 0, "global": 1, "director": 2}


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v) if not isinstance(v, str) else v


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _normalize_world_consequence(record: Dict[str, Any]) -> Dict[str, Any]:
    record = _safe_dict(record)
    return {
        "consequence_id": _safe_str(record.get("consequence_id")),
        "kind": _safe_str(record.get("kind")),
        "scope": _safe_str(record.get("scope")) or "local",
        "location_id": _safe_str(record.get("location_id")),
        "summary": _safe_str(record.get("summary")),
        "source_actor_id": _safe_str(record.get("source_actor_id")),
        "source_activity_id": _safe_str(record.get("source_activity_id")),
        "tick": _safe_int(record.get("tick"), 0),
        "priority": max(1, _safe_int(record.get("priority"), 1)),
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _lookup_location_label(location_id: str, simulation_state: Dict[str, Any]) -> str:
    simulation_state = _safe_dict(simulation_state)
    location_id = _safe_str(location_id)
    if not location_id:
        return ""

    locations = _safe_dict(simulation_state.get("location_index"))
    loc = _safe_dict(locations.get(location_id))
    if loc:
        return _safe_str(loc.get("name") or loc.get("title") or "")

    for loc in _safe_list(simulation_state.get("locations")):
        loc = _safe_dict(loc)
        if _safe_str(loc.get("id")) == location_id:
            return _safe_str(loc.get("name") or loc.get("title") or "")

    if location_id.startswith("loc_"):
        return location_id.replace("loc_", "").replace("_", " ").title()
    return ""


# ── World View normalization helpers ─────────────────────────────────────────

def _normalize_world_view_text(text: str) -> str:
    """Create a deterministic normalized text for duplicate detection."""
    text = _safe_str(text)
    text = text.lower()
    text = " ".join(text.split())  # collapse repeated spaces
    text = text.rstrip(".,!?;:")  # remove trailing punctuation
    return text


def _world_view_actor_label(row: Dict[str, Any], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> str:
    """Return the best human-readable actor label."""
    row = _safe_dict(row)
    actors = _safe_list(row.get("actors", []))
    if actors:
        for actor_id in actors:
            name = _lookup_actor_name(_safe_str(actor_id), simulation_state, runtime_state)
            if name:
                return name
    actor_id = _safe_str(row.get("actor_id"))
    if actor_id:
        name = _lookup_actor_name(actor_id, simulation_state, runtime_state)
        if name:
            return name
    return ""


def _lookup_actor_name(actor_id: str, simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> str:
    """Lookup human-readable name for actor_id from simulation state."""
    if not actor_id:
        return ""

    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    def _name_from_entity(entity: Dict[str, Any]) -> str:
        entity = _safe_dict(entity)
        return _safe_str(entity.get("name") or entity.get("display_name") or entity.get("label") or "")

    # Check npc_index first if present
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    entity = _safe_dict(npc_index.get(actor_id))
    if entity:
        name = _name_from_entity(entity)
        if name:
            return name

    # Check npcs when stored as dict
    npcs_dict = _safe_dict(simulation_state.get("npcs"))
    entity = _safe_dict(npcs_dict.get(actor_id))
    if entity:
        name = _name_from_entity(entity)
        if name:
            return name
    for npc_id, npc in npcs_dict.items():
        npc = _safe_dict(npc)
        if npc_id == actor_id or _safe_str(npc.get("id")) == actor_id:
            name = _name_from_entity(npc)
            if name:
                return name

    # Check npcs when stored as list
    for npc in _safe_list(simulation_state.get("npcs")):
        npc = _safe_dict(npc)
        if _safe_str(npc.get("id")) == actor_id:
            name = _name_from_entity(npc)
            if name:
                return name

    # Check actor_states when present
    for actor in _safe_list(runtime_state.get("actor_states")):
        actor = _safe_dict(actor)
        if _safe_str(actor.get("id")) == actor_id:
            name = _name_from_entity(actor)
            if name:
                return name
    # Check player if applicable
    player_state = _safe_dict(simulation_state.get("player_state"))
    if _safe_str(player_state.get("actor_id")) == actor_id:
        return _safe_str(player_state.get("name") or "Player")
    # Fallback to cleaned actor_id if it looks like a readable name, otherwise empty
    if actor_id.startswith("npc_"):
        return actor_id.replace("npc_", "").replace("_", " ").title()
    return ""


def _world_view_group_key(row: Dict[str, Any], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> str:
    """Group rows that represent the same underlying beat."""
    row = _safe_dict(row)
    tick = _safe_int(row.get("tick"), 0)
    location_id = _safe_str(row.get("location_id"))
    normalized_summary = _normalize_world_view_text(_safe_str(row.get("summary")))
    actor_label = _world_view_actor_label(row, simulation_state, runtime_state)
    kind = _safe_str(row.get("kind"))
    # Only merge state_change and state_change_beat
    merge_kind = "merged" if kind in ("state_change", "state_change_beat") else kind
    # Stable key
    key_parts = [str(tick), location_id, normalized_summary, actor_label, merge_kind]
    return "|".join(key_parts)


def _merge_world_view_rows(rows: List[Dict[str, Any]], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collapse paired duplicate rows into one player-facing row."""
    if not rows:
        return []
    rows = [_safe_dict(r) for r in rows]
    if len(rows) == 1:
        row = rows[0]
        return [_make_merged_row([row], simulation_state, runtime_state)]
    # Group by key
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = _world_view_group_key(row, simulation_state, runtime_state)
        if key not in groups:
            groups[key] = []
        groups[key].append(row)
    # Merge groups
    merged = []
    for group_rows in groups.values():
        merged.append(_make_merged_row(group_rows, simulation_state, runtime_state))
    return merged


def _make_merged_row(group_rows: List[Dict[str, Any]], simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    """Create a single merged row from a group of similar rows."""
    if not group_rows:
        return {}
    # Sort by kind priority: prefer state_change over state_change_beat
    group_rows.sort(key=lambda r: 0 if _safe_str(r.get("kind")) == "state_change" else 1)
    primary_row = group_rows[0]
    # Collect all event_ids for deterministic merged ID
    event_ids = sorted([_safe_str(r.get("event_id")) for r in group_rows if _safe_str(r.get("event_id"))])
    merged_id = f"world_view_merged_{hashlib.sha1('|'.join(event_ids).encode('utf-8')).hexdigest()[:16]}"
    # Determine merged properties
    actor_label = _world_view_actor_label(primary_row, simulation_state, runtime_state)
    # Preferred summary: state_change summary first
    summary = ""
    for row in group_rows:
        if _safe_str(row.get("kind")) == "state_change" and _safe_str(row.get("summary")):
            summary = _safe_str(row.get("summary"))
            break
    if not summary:
        for row in group_rows:
            if _safe_str(row.get("summary")):
                summary = _safe_str(row.get("summary"))
                break
    # Source
    sources = set(_safe_str(r.get("source")) for r in group_rows)
    source = "world_view_merged" if len(sources) > 1 else next(iter(sources), "simulation")
    # Kind
    kinds = set(_safe_str(r.get("kind")) for r in group_rows)
    if kinds == {"state_change", "state_change_beat"} or "activity_beat" in kinds:
        kind = "world_view_activity"
    elif "security_pressure" in kinds or "market_shift" in kinds or "location_condition" in kinds or "rumor" in kinds:
        kind = "world_view_consequence"
    else:
        kind = next(iter(kinds), "world_event")
    # Title
    if kind == "world_view_activity":
        title = actor_label or "Local Activity"
    elif kind == "world_view_consequence":
        title = _safe_str(primary_row.get("title")) or "World Consequence"
    else:
        title = actor_label or _safe_str(primary_row.get("title")) or "World Update"
    return _make_event_row(
        event_id=merged_id,
        scope=_safe_str(primary_row.get("scope")),
        kind=kind,
        title=title,
        summary=summary,
        tick=_safe_int(primary_row.get("tick"), 0),
        actors=_safe_list(primary_row.get("actors")),
        actor_label=actor_label,
        location_id=_safe_str(primary_row.get("location_id")),
        priority=_safe_float(primary_row.get("priority") or 0.5),
        status=_safe_str(primary_row.get("status")) or "active",
        source=source,
        location_label=_lookup_location_label(_safe_str(primary_row.get("location_id")), simulation_state),
    )


def _suppress_repetitive_world_view_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reduce spam from nearly identical consecutive patrol/watch beats."""
    if not rows:
        return rows
    # Group by suppression key
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = _world_view_suppression_key(row)
        if key not in groups:
            groups[key] = []
        groups[key].append(row)
    # For each group, sort newest first, keep only the newest, suppress others within 4 ticks
    suppressed = []
    for group in groups.values():
        if not group:
            continue
        # Sort newest first
        group.sort(key=lambda r: (-_safe_int(r.get("tick"), 0), _safe_str(r.get("event_id"))))
        # Keep the newest
        suppressed.append(group[0])
        # Suppress others if within 4 ticks of the newest
        newest_tick = _safe_int(group[0].get("tick"), 0)
        for row in group[1:]:
            tick = _safe_int(row.get("tick"), 0)
            if newest_tick - tick > 4:
                suppressed.append(row)
    return suppressed


def _world_view_suppression_key(row: Dict[str, Any]) -> str:
    """Generate suppression key for near-identical detection."""
    row = _safe_dict(row)
    actor_label = _safe_str(row.get("actor_label"))
    location_id = _safe_str(row.get("location_id"))
    normalized_summary = _normalize_world_view_text(_safe_str(row.get("summary")))
    kind_bucket = "world_view_activity" if _safe_str(row.get("kind")) == "world_view_activity" else _safe_str(row.get("kind"))
    return f"{actor_label}|{location_id}|{normalized_summary}|{kind_bucket}"


def build_player_local_world_view_rows(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    rows = [r for r in _safe_list(runtime_state.get("recent_world_event_rows")) if _safe_str(_safe_dict(r).get("scope")) == "local"]
    merged_rows = _merge_world_view_rows(rows, simulation_state, runtime_state)
    suppressed_rows = _suppress_repetitive_world_view_rows(merged_rows)
    suppressed_rows.sort(key=lambda r: (-_safe_int(r.get("tick"), 0), _safe_str(r.get("event_id"))))
    return suppressed_rows[:_MAX_PLAYER_WORLD_VIEW_ROWS]


def build_player_global_world_view_rows(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    rows = []
    rows.extend([_safe_dict(r) for r in _safe_list(runtime_state.get("global_world_beats"))])
    rows.extend([r for r in _safe_list(runtime_state.get("recent_world_event_rows")) if _safe_str(_safe_dict(r).get("scope")) == "global"])

    # Also include recent global consequences directly
    for consequence in _safe_list(runtime_state.get("world_consequences"))[-16:]:
        consequence = _normalize_world_consequence(consequence)
        if _safe_str(consequence.get("scope")) != "global":
            continue
        rows.append({
            "event_id": _safe_str(consequence.get("consequence_id")),
            "scope": "global",
            "kind": _safe_str(consequence.get("kind")) or "world_consequence",
            "title": "World Consequence",
            "summary": _safe_str(consequence.get("summary")),
            "tick": _safe_int(consequence.get("tick"), 0),
            "actors": [_safe_str(consequence.get("source_actor_id"))] if _safe_str(consequence.get("source_actor_id")) else [],
            "actor_id": _safe_str(consequence.get("source_actor_id")),
            "location_id": _safe_str(consequence.get("location_id")),
            "priority": min(1.0, 0.4 + (0.1 * _safe_int(consequence.get("priority"), 1))),
            "status": "active",
            "source": "consequence_runtime",
        })

    merged_rows = _merge_world_view_rows(rows, simulation_state, runtime_state)
    suppressed_rows = _suppress_repetitive_world_view_rows(merged_rows)
    suppressed_rows.sort(key=lambda r: (-_safe_int(r.get("tick"), 0), _safe_str(r.get("event_id"))))
    return suppressed_rows[:_MAX_PLAYER_WORLD_VIEW_ROWS]


def build_player_world_view_rows(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    local_rows = build_player_local_world_view_rows(simulation_state, runtime_state)
    global_rows = build_player_global_world_view_rows(simulation_state, runtime_state)
    rows = list(local_rows) + list(global_rows)
    rows.sort(key=lambda r: (-_safe_int(r.get("tick"), 0), _safe_str(r.get("event_id"))))
    return rows[:_MAX_PLAYER_WORLD_VIEW_ROWS]


def _row_sort_key(row: Dict[str, Any]) -> tuple:
    scope = _safe_str(row.get("scope"))
    return (
        _SCOPE_ORDER.get(scope, 9),
        -float(row.get("priority", 0) or 0),
        _safe_int(row.get("tick"), 0),
        _safe_str(row.get("event_id")),
    )


def _make_event_row(
    *,
    event_id: str,
    scope: str,
    kind: str,
    title: str,
    summary: str,
    tick: int = 0,
    actors: List[str] | None = None,
    actor_label: str = "",
    location_id: str = "",
    priority: float = 0.0,
    status: str = "active",
    source: str = "simulation",
    location_label: str = "",
) -> Dict[str, Any]:
    return {
        "event_id": event_id,
        "scope": scope,
        "kind": kind,
        "title": title,
        "summary": summary,
        "tick": tick,
        "actors": actors or [],
        "actor_label": actor_label,
        "location_id": location_id,
        "priority": max(0.0, min(priority, 1.0)),
        "status": status,
        "source": source,
        "location_label": location_label,
    }


# ── Local events ─────────────────────────────────────────────────────────

def _build_local_events(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build local event rows from ambient updates, incidents, and conversations."""
    rows: List[Dict[str, Any]] = []
    player_state = _safe_dict(simulation_state.get("player_state"))
    player_loc = _safe_str(player_state.get("location_id"))
    tick = _safe_int(simulation_state.get("tick"), 0)

    # From recent events at player location
    for event in _safe_list(simulation_state.get("events"))[-24:]:
        event = _safe_dict(event)
        loc = _safe_str(event.get("location_id"))
        if loc and loc != player_loc:
            continue
        eid = _safe_str(event.get("event_id"))
        rows.append(_make_event_row(
            event_id=eid or f"evt:{tick}:{len(rows)}",
            scope="local",
            kind=_safe_str(event.get("type") or "world_event"),
            title=_safe_str(event.get("type") or "Event"),
            summary=_safe_str(event.get("description") or event.get("summary") or "Something happens."),
            tick=_safe_int(event.get("tick"), tick),
            location_id=loc,
            priority=0.5,
            source="simulation",
        ))

    # From recent incidents at player location
    for inc in _safe_list(simulation_state.get("incidents"))[-8:]:
        inc = _safe_dict(inc)
        loc = _safe_str(inc.get("location_id"))
        if loc and loc != player_loc:
            continue
        iid = _safe_str(inc.get("incident_id"))
        rows.append(_make_event_row(
            event_id=iid or f"inc:{tick}:{len(rows)}",
            scope="local",
            kind="incident",
            title="Incident",
            summary=_safe_str(inc.get("description") or inc.get("summary") or "An incident unfolds."),
            tick=_safe_int(inc.get("tick"), tick),
            location_id=loc,
            priority=0.55,
            source="simulation",
        ))

    # From queued ambient updates (reaction beats)
    for update in _safe_list(runtime_state.get("ambient_queue"))[-12:]:
        update = _safe_dict(update)
        kind = _safe_str(update.get("kind"))
        if kind in ("follow_reaction", "caution_reaction", "assist_reaction", "warning", "npc_to_player"):
            rows.append(_make_event_row(
                event_id=_safe_str(update.get("ambient_id")) or f"amb:{tick}:{len(rows)}",
                scope="local",
                kind=kind,
                title=kind.replace("_", " ").title(),
                summary=_safe_str(update.get("text") or ""),
                tick=_safe_int(update.get("tick"), tick),
                actors=[_safe_str(update.get("speaker_id"))],
                location_id=_safe_str(update.get("location_id")),
                priority=float(update.get("priority", 0.4) or 0.4),
                source="ambient_runtime",
            ))

    rows.sort(key=_row_sort_key)
    return rows[:_MAX_LOCAL]


# ── Global events ────────────────────────────────────────────────────────

def _build_global_events(
    simulation_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build global event rows from world consequences, faction shifts, threads."""
    rows: List[Dict[str, Any]] = []
    tick = _safe_int(simulation_state.get("tick"), 0)

    sandbox_state = _safe_dict(simulation_state.get("sandbox_state"))
    for wc in _safe_list(sandbox_state.get("world_consequences"))[-12:]:
        wc = _safe_dict(wc)
        rows.append(_make_event_row(
            event_id=_safe_str(wc.get("consequence_id")) or f"wc:{tick}:{len(rows)}",
            scope="global",
            kind="world_consequence",
            title=_safe_str(wc.get("type") or "World Change"),
            summary=_safe_str(wc.get("description") or wc.get("summary") or "The world shifts."),
            tick=_safe_int(wc.get("tick"), tick),
            priority=0.5,
            source="sandbox",
        ))

    # Faction pressure shifts
    faction_pressure = _safe_dict(simulation_state.get("faction_pressure"))
    for fid, fp in sorted(faction_pressure.items()):
        fp = _safe_dict(fp)
        level = float(fp.get("level", 0) or 0)
        if level > 0.4:
            fname = _safe_str(fp.get("name") or fid)
            rows.append(_make_event_row(
                event_id=f"fp:{fid}:{tick}",
                scope="global",
                kind="faction_pressure",
                title=f"{fname} Pressure",
                summary=f"Faction pressure at {level:.1f}",
                tick=tick,
                priority=min(level, 1.0),
                source="simulation",
            ))

    # Threads / hotspots
    for thread in _safe_list(simulation_state.get("threads"))[-6:]:
        thread = _safe_dict(thread)
        tid = _safe_str(thread.get("thread_id"))
        rows.append(_make_event_row(
            event_id=tid or f"thr:{tick}:{len(rows)}",
            scope="global",
            kind="thread",
            title=_safe_str(thread.get("name") or "Active Thread"),
            summary=_safe_str(thread.get("summary") or "An ongoing development."),
            tick=_safe_int(thread.get("tick"), tick),
            priority=0.45,
            source="simulation",
        ))

    rows.sort(key=_row_sort_key)
    return rows[:_MAX_GLOBAL]


# ── Director pressure ────────────────────────────────────────────────────

def _build_director_pressure(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build director pressure rows from narrative control structures.

    Always labeled scope="director" and source="director_bias".
    Never mixed into local/global.
    """
    rows: List[Dict[str, Any]] = []
    tick = _safe_int(simulation_state.get("tick"), 0)

    # Arc control structures
    arc_control = _safe_dict(simulation_state.get("arc_control"))
    if arc_control:
        current_arc = _safe_str(arc_control.get("current_arc"))
        if current_arc:
            rows.append(_make_event_row(
                event_id=f"arc:{current_arc}:{tick}",
                scope="director",
                kind="arc_control",
                title="Current Arc",
                summary=current_arc,
                tick=tick,
                priority=0.6,
                source="director_bias",
            ))

    # Narrative pressure
    narrative_pressure = _safe_dict(simulation_state.get("narrative_pressure"))
    if narrative_pressure:
        level = float(narrative_pressure.get("level", 0) or 0)
        if level > 0.2:
            rows.append(_make_event_row(
                event_id=f"np:{tick}",
                scope="director",
                kind="narrative_pressure",
                title="Narrative Pressure",
                summary=f"Pressure level: {level:.1f}",
                tick=tick,
                priority=min(level, 1.0),
                source="director_bias",
            ))

    # Director hints / biases from runtime
    opening_runtime = _safe_dict(runtime_state.get("opening_runtime"))
    if opening_runtime.get("active"):
        hook = _safe_str(opening_runtime.get("hook_id") or opening_runtime.get("starter_conflict"))
        if hook:
            rows.append(_make_event_row(
                event_id=f"opening:{hook}:{tick}",
                scope="director",
                kind="opening_hook",
                title="Opening Hook",
                summary=f"Active opening: {hook}",
                tick=tick,
                priority=0.55,
                source="director_bias",
            ))

    rows.sort(key=_row_sort_key)
    return rows[:_MAX_DIRECTOR]


# ── Public API ───────────────────────────────────────────────────────────

def build_world_events_view(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    *,
    limit: int = 48,
) -> Dict[str, Any]:
    """Build the full World Events view for the frontend panel.

    Returns presentation-only data with strict scope separation.
    Director rows are always labeled as bias/setup, never as world fact.
    """
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    local_events = _build_local_events(simulation_state, runtime_state)
    global_events = _build_global_events(simulation_state)
    director_pressure = _build_director_pressure(simulation_state, runtime_state)

    # Recent changes: merge and sort all
    all_rows = local_events + global_events + director_pressure
    all_rows.sort(key=_row_sort_key)
    recent_changes = all_rows[:_MAX_RECENT]

    return {
        "current_tick": _safe_int(simulation_state.get("tick"), 0),
        "local_events": local_events,
        "global_events": global_events,
        "director_pressure": director_pressure,
        "recent_changes": recent_changes,
    }


def build_incremental_world_event_rows(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    debug_trace: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Build incremental event rows for appending to recent_world_event_rows.

    Returns a small bounded list of new rows from the current tick.
    """
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    tick = _safe_int(simulation_state.get("tick"), 0)

    print(
        "DEBUG WORLD EVENTS BUILD START =",
        {
            "tick": tick,
            "ambient_queue_count": len(_safe_list(runtime_state.get("ambient_queue"))),
            "accepted_state_change_events_count": len(_safe_list(runtime_state.get("accepted_state_change_events"))),
            "recent_scene_beats_count": len(_safe_list(runtime_state.get("recent_scene_beats"))),
        },
    )

    rows: List[Dict[str, Any]] = []
    seen_event_ids: set[str] = set()

    def _append_row(row: Dict[str, Any]) -> None:
        row = _safe_dict(row)
        event_id = _safe_str(row.get("event_id")).strip()
        if not event_id or event_id in seen_event_ids:
            return
        seen_event_ids.add(event_id)
        rows.append(row)

    # Pull from ambient queue — only recent items at current tick
    for update in _safe_list(runtime_state.get("ambient_queue"))[-8:]:
        update = _safe_dict(update)
        utick = _safe_int(update.get("tick"), 0)
        if utick < tick - 1:
            continue
        kind = _safe_str(update.get("kind"))
        if kind in ("system_summary",):
            continue
        scope = "local"
        if kind in ("world_event",) and not _safe_str(update.get("location_id")):
            scope = "global"
        _append_row(_make_event_row(
            event_id=_safe_str(update.get("ambient_id")) or f"inc_row:{tick}:{len(rows)}",
            scope=scope,
            kind=kind,
            title=kind.replace("_", " ").title(),
            summary=_safe_str(update.get("text") or "")[:200],
            tick=utick,
            actors=[_safe_str(update.get("speaker_id"))] if _safe_str(update.get("speaker_id")) else [],
            location_id=_safe_str(update.get("location_id")),
            priority=float(update.get("priority", 0.3) or 0.3),
            source="ambient_runtime",
        ))

    # Pull from accepted semantic state-change events — these are canonical
    # post-LLM events already accepted by the runtime and should surface in
    # the incremental world events feed.
    for event in _safe_list(runtime_state.get("accepted_state_change_events"))[-8:]:
        event = _safe_dict(event)
        etick = _safe_int(event.get("tick"), 0)

        print(
            "DEBUG WORLD EVENTS CHECK accepted_state_change_event =",
            {
                "event_id": _safe_str(event.get("event_id")),
                "event_tick": etick,
                "current_tick": tick,
                "summary": _safe_str(event.get("summary")),
            },
        )

        if etick < tick - 1:
            print(
                "DEBUG WORLD EVENTS SKIP accepted_state_change_event old_tick =",
                {
                    "event_id": _safe_str(event.get("event_id")),
                    "event_tick": etick,
                    "current_tick": tick,
                },
            )
            continue
        beat = _safe_dict(event.get("beat"))
        summary = (
            _safe_str(event.get("summary")).strip()
            or _safe_str(beat.get("summary")).strip()
            or "A character changes behavior."
        )
        location_id = _safe_str(event.get("location_id"))

        print(
            "DEBUG WORLD EVENTS APPEND accepted_state_change_event =",
            {
                "event_id": _safe_str(event.get("event_id")),
                "event_tick": etick,
                "summary": summary,
            },
        )

        _append_row(_make_event_row(
            event_id=_safe_str(event.get("event_id")) or f"state_change:{etick}:{len(rows)}",
            scope="local" if location_id else "global",
            kind="state_change",
            title="NPC Activity",
            summary=summary[:200],
            tick=etick,
            actors=[_safe_str(event.get("actor_id"))] if _safe_str(event.get("actor_id")) else [],
            location_id=location_id,
            priority=float(beat.get("priority", 0.65) or 0.65),
            status="active",
            source="semantic_runtime",
        ))

    # Pull from recent scene beats — especially state_change_beat entries
    # emitted during idle/world advancement. These are presentation-facing
    # beats and should appear in the recent feed.
    for beat in _safe_list(runtime_state.get("recent_scene_beats"))[-8:]:
        beat = _safe_dict(beat)
        btick = _safe_int(beat.get("tick"), 0)

        print(
            "DEBUG WORLD EVENTS CHECK scene_beat =",
            {
                "event_id": _safe_str(beat.get("beat_id")) or f"scene_beat:{btick}",
                "beat_tick": btick,
                "current_tick": tick,
                "kind": _safe_str(beat.get("kind")),
                "summary": _safe_str(beat.get("summary")),
            },
        )

        if btick < tick - 1:
            print(
                "DEBUG WORLD EVENTS SKIP scene_beat old_tick =",
                {
                    "event_id": _safe_str(beat.get("beat_id")) or f"scene_beat:{btick}",
                    "beat_tick": btick,
                    "current_tick": tick,
                },
            )
            continue
        kind = _safe_str(beat.get("kind"))
        if not kind:
            continue
        if kind not in ("state_change_beat", "world_event", "director_pressure", "incident", "consequence"):
            print(
                "DEBUG WORLD EVENTS SKIP scene_beat disallowed_kind =",
                {
                    "event_id": _safe_str(beat.get("beat_id")) or f"scene_beat:{btick}",
                    "kind": kind,
                },
            )
            continue
        summary = _safe_str(beat.get("summary")).strip()
        if not summary:
            continue
        location_id = _safe_str(beat.get("location_id"))

        print(
            "DEBUG WORLD EVENTS APPEND scene_beat =",
            {
                "event_id": _safe_str(beat.get("beat_id")) or f"scene_beat:{btick}",
                "beat_tick": btick,
                "summary": summary,
            },
        )

        _append_row(_make_event_row(
            event_id=_safe_str(beat.get("beat_id")) or f"scene_beat:{btick}:{len(rows)}",
            scope="local" if location_id else "global",
            kind=kind,
            title="Scene Development",
            summary=summary[:200],
            tick=btick,
            actors=[_safe_str(beat.get("actor_id"))] if _safe_str(beat.get("actor_id")) else [],
            location_id=location_id,
            priority=float(beat.get("priority", 0.55) or 0.55),
            status="active",
            source="scene_beats",
        ))

    rows.sort(key=_row_sort_key)
    print(
        "DEBUG WORLD EVENTS BUILD END =",
        {
            "tick": tick,
            "row_count": len(rows),
            "row_event_ids": [_safe_str(r.get("event_id")) for r in rows],
        },
    )
    return rows[:8]
