"""4C-C — Conversation Scheduler.

Per-scene scheduler that manages conversation lifecycle:
- Scans eligible NPC groups in the same scene
- Starts new threads, continues active threads, pauses/expires stale ones
- Supports three modes: ambient, directed_to_player, group
- Respects beat caps: ambient 2-5, directed 3-6, group 4-8
- Promotes threads from ambient to directed if player is nearby + topic is relevant
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .conversation_beats import (
    MODE_BEAT_CAPS,
    append_beat,
    build_beat_from_conversation_line,
    compute_beat_caps,
    ensure_beats_state,
    should_advance_thread,
    trim_beats_state,
)
from .conversation_engine import (
    advance_active_conversations,
    build_next_conversation_line,
    open_conversation,
    should_close_conversation,
    try_start_ambient_conversations,
)
from .conversation_participants import (
    find_candidate_conversation_groups,
    select_initiator,
    select_next_speaker,
)
from .conversation_settings import resolve_conversation_settings
from .conversation_topics import build_conversation_topic_candidates
from .npc_conversations import (
    append_conversation_line,
    close_conversation,
    ensure_conversation_state,
    get_conversation,
    get_conversation_lines,
    list_active_conversations,
    trim_conversation_state,
    upsert_conversation,
)

# ── Constants ─────────────────────────────────────────────────────────────

_MAX_CONCURRENT_THREADS = 3
_MAX_NEW_THREADS_PER_TICK = 1
_AMBIENT_PRIORITY = 20
_DIRECTED_PRIORITY = 80
_GROUP_PRIORITY = 60
_PIVOT_TURN_EXTENSION = 4   # additional turns granted after mode pivot or thread creation


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v) if not isinstance(v, str) else v


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _player_location(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> str:
    runtime_state = _safe_dict(runtime_state)
    simulation_state = _safe_dict(simulation_state)
    player_state = _safe_dict(simulation_state.get("player_state"))
    return _safe_str(
        runtime_state.get("current_location_id")
        or player_state.get("location_id")
    )


# ── Thread eligibility ────────────────────────────────────────────────────

def _thread_is_expired(conversation: Dict[str, Any], tick: int) -> bool:
    """Check if a conversation thread has expired by tick."""
    expires = _safe_int(conversation.get("expires_at_tick"), 0)
    return expires > 0 and tick > expires


def _thread_is_stale(conversation: Dict[str, Any], tick: int, stale_ticks: int = 6) -> bool:
    """Check if a thread hasn't advanced in too many ticks."""
    updated = _safe_int(conversation.get("updated_tick"), 0)
    return (tick - updated) > stale_ticks


# ── Mode classification ───────────────────────────────────────────────────

def classify_thread_mode(
    conversation: Dict[str, Any],
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> str:
    """Classify what mode a thread should be in based on current state.

    Returns: "ambient" | "directed_to_player" | "group"
    """
    conversation = _safe_dict(conversation)
    participants = _safe_list(conversation.get("participants"))

    # If player is a participant, it's group mode
    if "player" in participants:
        return "group"

    # If 3+ participants (excluding player), it's group mode
    if len(participants) >= 3:
        return "group"

    # Check for player relevance via topic
    topic = _safe_dict(conversation.get("topic"))
    topic_type = _safe_str(topic.get("type"))
    if topic_type in {"plan_reaction", "risk_conflict"}:
        # These topics are often directed at the player
        if conversation.get("player_present"):
            return "directed_to_player"

    # Check existing mode
    current_mode = _safe_str(conversation.get("mode"))
    if current_mode in {"directed_to_player", "group"}:
        return current_mode

    return "ambient"


# ── Scheduling decisions ──────────────────────────────────────────────────

def _should_start_new_thread(
    active_conversations: List[Dict[str, Any]],
    settings: Dict[str, Any],
) -> bool:
    """Decide if a new ambient conversation thread should start.

    Only counts ambient-mode conversations against the concurrent limit,
    since ``max_concurrent_ambient_threads`` specifically caps ambient threads.
    """
    max_concurrent = _safe_int(settings.get("max_concurrent_ambient_threads"), _MAX_CONCURRENT_THREADS)
    ambient_count = sum(
        1 for c in active_conversations
        if _safe_str(_safe_dict(c).get("mode")) in {"ambient", ""}
    )
    return ambient_count < max_concurrent


def _compute_thread_importance(conversation: Dict[str, Any]) -> int:
    """Compute importance score (0-100) for a conversation thread."""
    conversation = _safe_dict(conversation)
    mode = _safe_str(conversation.get("mode"))
    topic = _safe_dict(conversation.get("topic"))
    topic_type = _safe_str(topic.get("type"))
    priority = float(topic.get("priority", 0.5) or 0.5)

    base = {
        "ambient": _AMBIENT_PRIORITY,
        "directed_to_player": _DIRECTED_PRIORITY,
        "group": _GROUP_PRIORITY,
    }.get(mode, _AMBIENT_PRIORITY)

    # Boost by topic priority
    base = int(base + priority * 20)

    # Boost for high-tension topics
    if topic_type in {"faction_tension", "local_incident", "moral_conflict"}:
        base += 10

    return min(100, max(0, base))


def _compute_world_effect_budget(conversation: Dict[str, Any]) -> int:
    """Compute how many world signals this thread is allowed to emit."""
    conversation = _safe_dict(conversation)
    mode = _safe_str(conversation.get("mode"))
    topic = _safe_dict(conversation.get("topic"))
    topic_type = _safe_str(topic.get("type"))

    if mode == "group":
        return 3
    if mode == "directed_to_player":
        return 2
    if topic_type in {"faction_tension", "local_incident", "moral_conflict"}:
        return 2
    return 1


# ── Main scheduler ────────────────────────────────────────────────────────

def run_conversation_scheduler_tick(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    """Run one tick of the conversation scheduler.

    This is the main entry point for the 4C conversation system.
    It handles:
    1. Expiring/closing stale threads
    2. Advancing active threads (producing beats)
    3. Starting new threads if capacity allows
    4. Updating thread metadata (mode, importance, budgets)

    Returns the updated simulation_state.
    """
    ensure_conversation_state(simulation_state)
    ensure_beats_state(simulation_state)
    settings = resolve_conversation_settings(simulation_state, runtime_state)
    player_loc = _player_location(simulation_state, runtime_state)

    # 1. Expire/close stale and expired threads
    simulation_state = _expire_stale_threads(simulation_state, runtime_state, tick)

    # 2. Advance active threads — produce beats
    simulation_state = _advance_threads_with_beats(simulation_state, runtime_state, tick)

    # 3. Start new threads if capacity allows
    active = list_active_conversations(simulation_state, location_id=player_loc)
    if _should_start_new_thread(active, settings):
        simulation_state = _start_new_threads(simulation_state, runtime_state, tick, player_loc, settings)

    # 4. Update thread metadata
    simulation_state = _update_thread_metadata(simulation_state, runtime_state)

    # 5. Trim state to bounded sizes
    trim_conversation_state(simulation_state)
    trim_beats_state(simulation_state)

    return simulation_state


def _expire_stale_threads(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    """Close threads that have expired or gone stale."""
    for conv in list_active_conversations(simulation_state):
        conv = _safe_dict(conv)
        cid = _safe_str(conv.get("conversation_id"))
        if not cid:
            continue

        if _thread_is_expired(conv, tick):
            close_conversation(simulation_state, cid, reason="expired")
            continue

        if _thread_is_stale(conv, tick):
            close_conversation(simulation_state, cid, reason="stale")
            continue

    return simulation_state


def _advance_threads_with_beats(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    """Advance each active thread by one beat, producing authoritative beat records."""
    for conv in list_active_conversations(simulation_state):
        conv = dict(conv)
        cid = _safe_str(conv.get("conversation_id"))

        if not should_advance_thread(conv, tick):
            if should_close_conversation(conv, simulation_state, runtime_state, tick):
                close_conversation(simulation_state, cid, reason="completed")
            continue

        # Check beat cap for this mode
        mode = _safe_str(conv.get("mode")) or "ambient"
        _, max_beats = compute_beat_caps(mode)
        beat_count = _safe_int(conv.get("beat_count"), 0)
        if beat_count >= max_beats:
            close_conversation(simulation_state, cid, reason="beat_cap_reached")
            continue

        # Generate line using existing engine
        line = build_next_conversation_line(conv, simulation_state, runtime_state, tick)
        append_conversation_line(simulation_state, cid, line)

        # Build authoritative beat from the line
        beat = build_beat_from_conversation_line(conv, line, tick)
        append_beat(simulation_state, beat)

        # Update conversation state
        conv["turn_count"] = _safe_int(conv.get("turn_count"), 0) + 1
        conv["beat_count"] = beat_count + 1
        conv["updated_tick"] = int(tick or 0)
        conv["last_speaker_id"] = _safe_str(line.get("speaker"))
        conv["intervention_pending"] = bool(
            conv.get("player_can_intervene") and conv.get("player_present")
        )
        upsert_conversation(simulation_state, conv)

        # Check if now complete
        if should_close_conversation(conv, simulation_state, runtime_state, tick):
            close_conversation(simulation_state, cid, reason="completed")

    return simulation_state


def _start_new_threads(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    tick: int,
    player_loc: str,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """Start new conversation threads if capacity allows."""
    candidate_groups = find_candidate_conversation_groups(
        simulation_state, player_loc, tick,
    )
    started = 0

    for group in candidate_groups:
        if started >= _MAX_NEW_THREADS_PER_TICK:
            break

        topics = build_conversation_topic_candidates(
            simulation_state, runtime_state, player_loc, group, tick,
        )
        if not topics:
            continue

        topic = topics[0]

        # Check if conversation already exists for this group+topic
        existing = list_active_conversations(simulation_state, location_id=player_loc)
        exists = False
        target = sorted([_safe_str(x) for x in group if _safe_str(x)])
        for e in existing:
            if sorted(_safe_list(e.get("participants"))) == target:
                e_topic = _safe_dict(e.get("topic"))
                if _safe_str(e_topic.get("anchor")) == _safe_str(topic.get("anchor")):
                    exists = True
                    break
        if exists:
            continue

        # Determine mode and beat cap
        mode = "ambient"
        topic_type = _safe_str(topic.get("type"))
        if topic_type in {"plan_reaction", "risk_conflict"}:
            mode = "directed_to_player"
        if len(group) >= 3:
            mode = "group"

        _, max_beats = compute_beat_caps(mode)
        avg_turns = _safe_int(settings.get("avg_conversation_turns"), 4)
        effective_max = min(max_beats, max(2, avg_turns))

        conv = open_conversation(
            simulation_state,
            runtime_state,
            kind="ambient_npc_conversation",
            location_id=player_loc,
            participants=group,
            topic=topic,
            tick=tick,
        )

        # Enrich with 4C fields
        conv = _safe_dict(conv)
        conv["mode"] = mode
        conv["importance"] = _compute_thread_importance(conv)
        conv["world_effect_budget"] = _compute_world_effect_budget(conv)
        conv["max_turns"] = effective_max
        conv["expires_at_tick"] = tick + effective_max + _PIVOT_TURN_EXTENSION
        upsert_conversation(simulation_state, conv)

        started += 1

    return simulation_state


def _update_thread_metadata(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Update metadata on active threads (mode reclassification, importance recalc)."""
    for conv in list_active_conversations(simulation_state):
        conv = dict(conv)
        new_mode = classify_thread_mode(conv, simulation_state, runtime_state)
        if new_mode != _safe_str(conv.get("mode")):
            # Record pivot in history
            pivot_history = _safe_list(conv.get("pivot_history"))
            pivot_history.append({
                "from_mode": _safe_str(conv.get("mode")),
                "to_mode": new_mode,
                "at_beat": _safe_int(conv.get("beat_count"), 0),
            })
            conv["pivot_history"] = pivot_history[-8:]  # bound history
            conv["mode"] = new_mode

            # Recalculate max_turns based on new mode
            _, max_beats = compute_beat_caps(new_mode)
            current_beats = _safe_int(conv.get("beat_count"), 0)
            conv["max_turns"] = max(conv.get("max_turns", 0) or 0, min(max_beats, current_beats + _PIVOT_TURN_EXTENSION))

        conv["importance"] = _compute_thread_importance(conv)
        upsert_conversation(simulation_state, conv)

    return simulation_state


# ── Conversation mode summary for UI ──────────────────────────────────────

def get_active_thread_summary(
    simulation_state: Dict[str, Any],
    location_id: str = "",
) -> List[Dict[str, Any]]:
    """Return a compact summary of active threads for the UI inspector."""
    result: List[Dict[str, Any]] = []
    for conv in list_active_conversations(simulation_state, location_id=location_id):
        conv = _safe_dict(conv)
        topic = _safe_dict(conv.get("topic"))
        result.append({
            "conversation_id": _safe_str(conv.get("conversation_id")),
            "mode": _safe_str(conv.get("mode")) or "ambient",
            "participants": _safe_list(conv.get("participants")),
            "topic_type": _safe_str(topic.get("type")),
            "topic_summary": _safe_str(topic.get("summary"))[:100],
            "beat_count": _safe_int(conv.get("beat_count"), 0),
            "max_turns": _safe_int(conv.get("max_turns"), 1),
            "importance": _safe_int(conv.get("importance"), 0),
            "mode_pivots": len(_safe_list(conv.get("pivot_history"))),
            "status": _safe_str(conv.get("status")),
        })
    return result
