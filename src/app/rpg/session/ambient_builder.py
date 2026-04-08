"""Living-world ambient update builder.

Converts raw simulation state changes into player-facing ambient updates.
All logic is deterministic and bounded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

# ── Hard caps (Phase 0.3) ──────────────────────────────────────────────────
_MAX_AMBIENT_QUEUE = 32
_MAX_RECENT_AMBIENT_IDS = 64
_MAX_AMBIENT_COOLDOWNS = 64
_MAX_IDLE_TICKS_PER_REQUEST = 6
_MAX_RESUME_CATCHUP_TICKS = 12
_MAX_AMBIENT_BATCH_PER_DELIVERY = 8

# ── Helpers ────────────────────────────────────────────────────────────────

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

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Ambient update contract (Phase 0.4) ───────────────────────────────────

def _blank_ambient_update() -> Dict[str, Any]:
    """Return an empty ambient update with all required fields."""
    return {
        "ambient_id": "",
        "seq": 0,
        "tick": 0,
        "kind": "world_event",
        "priority": 0.0,
        "interrupt": False,
        "speaker_id": "",
        "speaker_name": "",
        "target_id": "",
        "target_name": "",
        "scene_id": "",
        "location_id": "",
        "text": "",
        "structured": {},
        "source_event_ids": [],
        "source": "simulation",
        "created_at": "",
    }


def make_ambient_update(**kwargs: Any) -> Dict[str, Any]:
    """Build an ambient update, filling missing fields with defaults."""
    update = _blank_ambient_update()
    for key, value in kwargs.items():
        if key in update:
            update[key] = value
    update["created_at"] = update["created_at"] or _utc_now_iso()
    return update


# ── Runtime state defaults (Phase 0.2) ────────────────────────────────────

def ensure_ambient_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all ambient fields exist with safe defaults."""
    runtime_state = dict(runtime_state) if isinstance(runtime_state, dict) else {}
    runtime_state.setdefault("ambient_queue", [])
    runtime_state.setdefault("ambient_seq", 0)
    runtime_state.setdefault("last_idle_tick_at", "")
    runtime_state.setdefault("last_player_turn_at", "")
    runtime_state.setdefault("idle_streak", 0)
    runtime_state.setdefault("ambient_cooldowns", {})
    runtime_state.setdefault("recent_ambient_ids", [])
    runtime_state.setdefault("pending_interrupt", None)
    runtime_state.setdefault("subscription_state", {"last_polled_seq": 0})
    runtime_state.setdefault("ambient_metrics", {
        "emitted": 0,
        "suppressed": 0,
        "coalesced": 0,
    })
    return runtime_state


def normalize_ambient_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    """Trim/bound all ambient state fields to hard caps."""
    runtime_state = ensure_ambient_runtime_state(runtime_state)
    # Trim queue
    queue = _safe_list(runtime_state.get("ambient_queue"))
    if len(queue) > _MAX_AMBIENT_QUEUE:
        runtime_state["ambient_queue"] = queue[-_MAX_AMBIENT_QUEUE:]
    # Trim recent IDs
    recent = _safe_list(runtime_state.get("recent_ambient_ids"))
    if len(recent) > _MAX_RECENT_AMBIENT_IDS:
        runtime_state["recent_ambient_ids"] = recent[-_MAX_RECENT_AMBIENT_IDS:]
    # Trim cooldowns
    cooldowns = _safe_dict(runtime_state.get("ambient_cooldowns"))
    if len(cooldowns) > _MAX_AMBIENT_COOLDOWNS:
        # Keep most recent entries by sorted key
        keys = sorted(cooldowns.keys())[-_MAX_AMBIENT_COOLDOWNS:]
        runtime_state["ambient_cooldowns"] = {k: cooldowns[k] for k in keys}
    return runtime_state


# ── Phase 2: Ambient extraction ───────────────────────────────────────────

def _get_player_location(simulation_state: Dict[str, Any]) -> str:
    """Get the player's current location_id."""
    player = _safe_dict(simulation_state.get("player_state"))
    return _safe_str(player.get("location_id")).strip()


def _nearby_npc_ids(simulation_state: Dict[str, Any]) -> List[str]:
    """Get IDs of NPCs near the player."""
    player = _safe_dict(simulation_state.get("player_state"))
    return [_safe_str(nid) for nid in _safe_list(player.get("nearby_npc_ids")) if _safe_str(nid)]


def build_ambient_updates(
    before_state: Dict[str, Any],
    after_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Extract ambient updates from simulation state changes.

    Inspects new events, NPC decisions, arrivals/departures, incident changes,
    faction pressure changes, and encounter state changes.
    """
    before_state = _safe_dict(before_state)
    after_state = _safe_dict(after_state)
    runtime_state = _safe_dict(runtime_state)

    updates: List[Dict[str, Any]] = []
    tick = int(after_state.get("tick", 0) or 0)
    player_loc = _get_player_location(after_state)
    nearby = set(_nearby_npc_ids(after_state))

    # ── New world events ──
    before_events = _safe_list(before_state.get("events"))
    after_events = _safe_list(after_state.get("events"))
    before_event_ids = {_safe_str(e.get("event_id")) for e in before_events if _safe_str(e.get("event_id"))}

    for event in after_events:
        event = _safe_dict(event)
        eid = _safe_str(event.get("event_id"))
        if not eid or eid in before_event_ids:
            continue
        loc = _safe_str(event.get("location_id"))
        updates.append(make_ambient_update(
            tick=tick,
            kind="world_event",
            priority=0.5 if loc == player_loc else 0.2,
            location_id=loc,
            text=_safe_str(event.get("description") or event.get("summary") or f"Something happens at {loc}"),
            source_event_ids=[eid],
            source="simulation",
        ))

    # ── NPC decisions (arrivals, departures, actions) ──
    before_decisions = _safe_dict(before_state.get("npc_decisions"))
    after_decisions = _safe_dict(after_state.get("npc_decisions"))
    npc_index = _safe_dict(after_state.get("npc_index"))

    for npc_id, decision in sorted(after_decisions.items()):
        decision = _safe_dict(decision)
        if npc_id in before_decisions and before_decisions[npc_id] == decision:
            continue

        action = _safe_str(decision.get("action") or decision.get("action_type")).lower()
        npc_info = _safe_dict(npc_index.get(npc_id))
        npc_name = _safe_str(npc_info.get("name") or npc_id)
        npc_loc = _safe_str(decision.get("location_id") or npc_info.get("location_id"))

        if action in ("move", "travel", "depart", "leave"):
            target_loc = _safe_str(decision.get("target_location") or decision.get("destination"))
            if npc_loc == player_loc or target_loc == player_loc:
                if target_loc == player_loc:
                    kind = "arrival"
                    text = f"{npc_name} arrives."
                else:
                    kind = "departure"
                    text = f"{npc_name} departs."
                updates.append(make_ambient_update(
                    tick=tick,
                    kind=kind,
                    priority=0.6 if npc_id in nearby else 0.3,
                    speaker_id=npc_id,
                    speaker_name=npc_name,
                    location_id=player_loc,
                    text=text,
                    source="simulation",
                ))
        elif action in ("speak", "talk", "address"):
            target_id = _safe_str(decision.get("target_id"))
            target_name = _safe_str(decision.get("target_name"))
            if target_id == "player" or npc_id in nearby:
                is_to_player = target_id == "player"
                updates.append(make_ambient_update(
                    tick=tick,
                    kind="npc_to_player" if is_to_player else "npc_to_npc",
                    priority=0.8 if is_to_player else 0.5,
                    interrupt=is_to_player,
                    speaker_id=npc_id,
                    speaker_name=npc_name,
                    target_id=target_id,
                    target_name=(target_name or "you") if is_to_player else target_name,
                    location_id=npc_loc,
                    text=_safe_str(decision.get("dialogue") or decision.get("text") or f"{npc_name} speaks."),
                    source="simulation",
                ))
        elif action in ("attack", "threaten", "warn"):
            target_id = _safe_str(decision.get("target_id"))
            if target_id == "player" or npc_id in nearby:
                kind = "combat_start" if action == "attack" else "warning"
                updates.append(make_ambient_update(
                    tick=tick,
                    kind=kind,
                    priority=0.9,
                    interrupt=True,
                    speaker_id=npc_id,
                    speaker_name=npc_name,
                    target_id=target_id,
                    location_id=npc_loc,
                    text=_safe_str(decision.get("text") or f"{npc_name} {'attacks' if action == 'attack' else 'warns'} you!"),
                    source="simulation",
                ))

    # ── Faction pressure changes ──
    before_factions = _safe_dict(before_state.get("factions"))
    after_factions = _safe_dict(after_state.get("factions"))
    for fid, after_fac in sorted(after_factions.items()):
        after_fac = _safe_dict(after_fac)
        before_fac = _safe_dict(before_factions.get(fid))
        bp = int(before_fac.get("pressure", 0) or 0)
        ap = int(after_fac.get("pressure", 0) or 0)
        if ap != bp and ap >= 3:
            fname = _safe_str(after_fac.get("name") or fid)
            updates.append(make_ambient_update(
                tick=tick,
                kind="world_event",
                priority=0.4,
                text=f"Tension rises among the {fname}." if ap > bp else f"Tensions ease among the {fname}.",
                source="simulation",
            ))

    # ── Incident changes ──
    before_incidents = _safe_list(before_state.get("incidents"))
    after_incidents = _safe_list(after_state.get("incidents"))
    before_inc_ids = {_safe_str(i.get("incident_id")) for i in before_incidents if _safe_str(i.get("incident_id"))}
    for inc in after_incidents:
        inc = _safe_dict(inc)
        iid = _safe_str(inc.get("incident_id"))
        if iid and iid not in before_inc_ids:
            loc = _safe_str(inc.get("location_id"))
            if loc == player_loc or not loc:
                updates.append(make_ambient_update(
                    tick=tick,
                    kind="world_event",
                    priority=0.45,
                    location_id=loc,
                    text=_safe_str(inc.get("description") or inc.get("summary") or "An incident unfolds nearby."),
                    source_event_ids=[iid],
                    source="simulation",
                ))

    return updates


# ── Phase 2.2: Salience scoring ───────────────────────────────────────────

def score_ambient_salience(update: Dict[str, Any], context: Dict[str, Any]) -> float:
    """Deterministic salience scoring for an ambient update.

    Score based on: same location, targets player, urgency, known NPC,
    active thread ties, scene transitions, repetition penalty.
    """
    update = _safe_dict(update)
    context = _safe_dict(context)

    score = float(update.get("priority", 0.0) or 0.0)
    player_loc = _safe_str(context.get("player_location"))
    update_loc = _safe_str(update.get("location_id"))
    nearby = set(_safe_list(context.get("nearby_npc_ids")))
    recent_ids = set(_safe_list(context.get("recent_ambient_ids")))

    # Same location bonus
    if update_loc and update_loc == player_loc:
        score += 0.3

    # Targets player
    if _safe_str(update.get("target_id")) == "player":
        score += 0.4

    # Known nearby NPC
    speaker = _safe_str(update.get("speaker_id"))
    if speaker and speaker in nearby:
        score += 0.2

    # Urgent/hostile kinds
    kind = _safe_str(update.get("kind"))
    if kind in ("combat_start", "warning"):
        score += 0.5
    elif kind in ("arrival", "departure"):
        score += 0.1

    # Interrupt flag
    if update.get("interrupt"):
        score += 0.3

    # Repetition penalty — reduce score for repeat source events
    source_ids = _safe_list(update.get("source_event_ids"))
    for sid in source_ids:
        if _safe_str(sid) in recent_ids:
            score -= 0.3
            break

    return max(0.0, min(score, 3.0))


# ── Phase 2.3: Visibility filter ──────────────────────────────────────────

def is_player_visible_update(update: Dict[str, Any], session: Dict[str, Any]) -> bool:
    """Check if an ambient update is visible/relevant to the player.

    Filters out internal bookkeeping, distant events, and omniscient leaks.
    """
    update = _safe_dict(update)
    session = _safe_dict(session)
    sim = _safe_dict(session.get("simulation_state"))
    runtime = _safe_dict(session.get("runtime_state"))

    kind = _safe_str(update.get("kind"))
    player_loc = _get_player_location(sim) or _safe_str(_safe_dict(runtime.get("current_scene")).get("location_id"))
    update_loc = _safe_str(update.get("location_id"))

    # System summaries are always visible
    if kind == "system_summary":
        return True

    # Combat/warning is always visible if it targets the player
    if kind in ("combat_start", "warning") and _safe_str(update.get("target_id")) == "player":
        return True

    # NPC-to-player is always visible
    if kind == "npc_to_player":
        return True

    # Must be at same location or location-independent
    if update_loc and player_loc and update_loc != player_loc:
        return False

    # Filter out very low priority internal events
    if float(update.get("priority", 0) or 0) < 0.1:
        return False

    return True


# ── Phase 2.4: Coalescing ─────────────────────────────────────────────────

def coalesce_ambient_updates(updates: List[Dict[str, Any]], runtime_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Merge repetitive updates in same tick.

    - Several low-priority world shifts → one summary
    - Multiple NPC chatter candidates → cap to two
    """
    if not updates:
        return []

    runtime_state = _safe_dict(runtime_state)
    metrics = _safe_dict(runtime_state.get("ambient_metrics"))

    # Separate by kind priority
    high_priority: List[Dict[str, Any]] = []
    npc_chatter: List[Dict[str, Any]] = []
    low_world: List[Dict[str, Any]] = []

    for u in updates:
        u = _safe_dict(u)
        kind = _safe_str(u.get("kind"))
        pri = float(u.get("priority", 0) or 0)

        if kind in ("combat_start", "warning", "npc_to_player"):
            high_priority.append(u)
        elif kind in ("npc_to_npc", "npc_reaction", "companion_comment"):
            npc_chatter.append(u)
        else:
            if pri >= 0.4:
                high_priority.append(u)
            else:
                low_world.append(u)

    result: List[Dict[str, Any]] = list(high_priority)

    # Cap NPC chatter to 2 per tick
    npc_chatter.sort(key=lambda u: float(u.get("priority", 0) or 0), reverse=True)
    result.extend(npc_chatter[:2])
    coalesced_chatter = max(0, len(npc_chatter) - 2)

    # Coalesce low-priority world events into one summary if >2
    coalesced_world = 0
    if len(low_world) <= 2:
        result.extend(low_world)
    else:
        texts = [_safe_str(u.get("text")) for u in low_world if _safe_str(u.get("text"))]
        summary_text = "; ".join(texts[:4])
        if len(texts) > 4:
            summary_text += f" and {len(texts) - 4} more changes"
        tick = int(low_world[0].get("tick", 0) or 0) if low_world else 0
        result.append(make_ambient_update(
            tick=tick,
            kind="system_summary",
            priority=0.3,
            text=summary_text,
            source="simulation",
        ))
        coalesced_world = len(low_world) - 1

    total_coalesced = coalesced_chatter + coalesced_world
    metrics["coalesced"] = int(metrics.get("coalesced", 0) or 0) + total_coalesced
    runtime_state["ambient_metrics"] = metrics

    # Sort by priority descending, then by kind for determinism
    result.sort(key=lambda u: (-float(u.get("priority", 0) or 0), _safe_str(u.get("kind")), _safe_str(u.get("speaker_id"))))

    return result


# ── Phase 3: Queue + delivery ─────────────────────────────────────────────

def enqueue_ambient_updates(runtime_state: Dict[str, Any], updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Append updates to the ambient queue with seq numbers and IDs.

    Trims queue to _MAX_AMBIENT_QUEUE, updates metrics and recent_ambient_ids.
    """
    runtime_state = ensure_ambient_runtime_state(runtime_state)
    queue = _safe_list(runtime_state.get("ambient_queue"))
    seq = int(runtime_state.get("ambient_seq", 0) or 0)
    recent = _safe_list(runtime_state.get("recent_ambient_ids"))
    metrics = _safe_dict(runtime_state.get("ambient_metrics"))

    for update in updates:
        update = _safe_dict(update)
        seq += 1
        update["seq"] = seq
        update["ambient_id"] = f"ambient:{seq}"
        queue.append(update)
        recent.append(update["ambient_id"])
        metrics["emitted"] = int(metrics.get("emitted", 0) or 0) + 1

    # Trim to bounds
    if len(queue) > _MAX_AMBIENT_QUEUE:
        queue = queue[-_MAX_AMBIENT_QUEUE:]
    if len(recent) > _MAX_RECENT_AMBIENT_IDS:
        recent = recent[-_MAX_RECENT_AMBIENT_IDS:]

    runtime_state["ambient_queue"] = queue
    runtime_state["ambient_seq"] = seq
    runtime_state["recent_ambient_ids"] = recent
    runtime_state["ambient_metrics"] = metrics
    return runtime_state


def get_pending_ambient_updates(session: Dict[str, Any], after_seq: int = 0, limit: int = 8) -> List[Dict[str, Any]]:
    """Return pending queue items after a given sequence number."""
    session = _safe_dict(session)
    runtime = _safe_dict(session.get("runtime_state"))
    queue = _safe_list(runtime.get("ambient_queue"))
    limit = min(max(1, limit), _MAX_AMBIENT_BATCH_PER_DELIVERY)

    result = []
    for item in queue:
        item = _safe_dict(item)
        item_seq = int(item.get("seq", 0) or 0)
        if item_seq > after_seq:
            result.append(item)
            if len(result) >= limit:
                break
    return result


def acknowledge_ambient_updates(session: Dict[str, Any], up_to_seq: int) -> Dict[str, Any]:
    """Acknowledge ambient updates up to a given seq, updating subscription state."""
    session = _safe_dict(session)
    runtime = ensure_ambient_runtime_state(_safe_dict(session.get("runtime_state")))
    sub = _safe_dict(runtime.get("subscription_state"))
    sub["last_polled_seq"] = max(int(sub.get("last_polled_seq", 0) or 0), int(up_to_seq))
    runtime["subscription_state"] = sub
    session["runtime_state"] = runtime
    return session
