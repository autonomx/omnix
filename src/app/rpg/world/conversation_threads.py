from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.world.location_registry import (
    current_location_id,
    get_location,
    present_npcs_for_current_location,
)
from app.rpg.world.world_event_log import add_world_event
from app.rpg.session.ambient_intent import is_ambient_wait_or_listen_intent


MAX_CONVERSATION_THREADS = 32
MAX_BEATS_PER_THREAD = 8
MAX_WORLD_SIGNALS = 64


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def ensure_conversation_thread_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    state = simulation_state.get("conversation_thread_state")
    if not isinstance(state, dict):
        state = {}
        simulation_state["conversation_thread_state"] = state

    if not isinstance(state.get("threads"), list):
        state["threads"] = []
    if not isinstance(state.get("active_thread_ids"), list):
        state["active_thread_ids"] = []
    if not isinstance(state.get("world_signals"), list):
        state["world_signals"] = []
    if not isinstance(state.get("debug"), dict):
        state["debug"] = {}
    return state


def get_conversation_thread_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(ensure_conversation_thread_state(simulation_state))





def _participant_key(npc: Dict[str, Any]) -> str:
    return _safe_str(npc.get("id") or npc.get("npc_id") or npc.get("name"))


def _normalize_present_npc(npc: Dict[str, Any]) -> Dict[str, Any]:
    npc = _safe_dict(npc)
    npc_id = _safe_str(npc.get("id") or npc.get("npc_id"))
    name = _safe_str(npc.get("name"))
    if not npc_id and name:
        npc_id = f"npc:{name}"
    return {
        "id": npc_id,
        "name": name or npc_id.replace("npc:", ""),
        "role": _safe_str(npc.get("role")),
    }


def select_conversation_participants(
    simulation_state: Dict[str, Any],
    *,
    limit: int = 2,
) -> List[Dict[str, Any]]:
    """Select participants only from NPCs present at current location."""
    present = [
        _normalize_present_npc(npc)
        for npc in present_npcs_for_current_location(simulation_state)
    ]
    present = [npc for npc in present if _participant_key(npc)]
    present.sort(key=lambda npc: (_safe_str(npc.get("id")), _safe_str(npc.get("name"))))
    return deepcopy(present[:limit])


def _topic_for_location(location_id: str) -> Dict[str, str]:
    if location_id == "loc_tavern":
        return {
            "topic_id": "tavern_evening_rumors",
            "topic": "the mood in the tavern",
            "signal_kind": "rumor_interest",
            "summary": "The tavern staff trade quiet observations about travelers and local rumors.",
        }
    if location_id == "loc_market":
        return {
            "topic_id": "market_trade_pressure",
            "topic": "market traffic",
            "signal_kind": "market_pressure",
            "summary": "Market workers comment on stock, traffic, and the day's trade.",
        }
    return {
        "topic_id": "local_activity",
        "topic": "local activity",
        "signal_kind": "ambient_interest",
        "summary": "Nearby NPCs exchange quiet comments about the area.",
    }


def _line_for_participant(
    participant: Dict[str, Any],
    *,
    location_id: str,
    beat_index: int,
) -> str:
    if location_id == "loc_tavern":
        if beat_index % 2 == 1:
            return "The room has been busier than usual tonight."
        return "Travelers always bring more stories than coin."
    if location_id == "loc_market":
        if beat_index % 2 == 1:
            return "The market crowd is moving quickly today."
        return "Busy stalls mean both opportunity and trouble."
    if beat_index % 2 == 1:
        return "The mood nearby is shifting."
    return "Best keep the exchange grounded in what is happening here."


def _thread_id_for(
    *,
    location_id: str,
    participants: List[Dict[str, Any]],
) -> str:
    participant_ids = [
        _safe_str(participant.get("id") or participant.get("name"))
        for participant in participants
    ]
    participant_part = ":".join(participant_ids)
    return f"conversation:{location_id}:{participant_part}"


def _find_thread(state: Dict[str, Any], thread_id: str) -> Dict[str, Any]:
    for thread in _safe_list(state.get("threads")):
        thread = _safe_dict(thread)
        if _safe_str(thread.get("thread_id")) == thread_id:
            return thread
    return {}


def _append_world_signal(
    state: Dict[str, Any],
    signal: Dict[str, Any],
) -> Dict[str, Any]:
    signals = _safe_list(state.get("world_signals"))
    signal_id = _safe_str(signal.get("signal_id"))
    if not signal_id:
        return {}
    for existing in signals:
        if _safe_str(_safe_dict(existing).get("signal_id")) == signal_id:
            return deepcopy(_safe_dict(existing))
    signals.append(deepcopy(signal))
    if len(signals) > MAX_WORLD_SIGNALS:
        del signals[:-MAX_WORLD_SIGNALS]
    state["world_signals"] = signals
    return deepcopy(signal)


def _make_beat(
    *,
    thread_id: str,
    participants: List[Dict[str, Any]],
    location_id: str,
    tick: int,
    beat_index: int,
    topic_payload: Dict[str, str],
) -> Dict[str, Any]:
    speaker = participants[(beat_index - 1) % len(participants)]
    listener = participants[beat_index % len(participants)]
    return {
        "beat_id": f"conversation:beat:{tick}:{thread_id}:{beat_index}",
        "thread_id": thread_id,
        "beat_index": beat_index,
        "speaker_id": _safe_str(speaker.get("id")),
        "speaker_name": _safe_str(speaker.get("name")),
        "listener_id": _safe_str(listener.get("id")),
        "listener_name": _safe_str(listener.get("name")),
        "line": _line_for_participant(
            speaker,
            location_id=location_id,
            beat_index=beat_index,
        ),
        "topic_id": _safe_str(topic_payload.get("topic_id")),
        "topic": _safe_str(topic_payload.get("topic")),
        "tick": int(tick or 0),
        "source": "deterministic_conversation_thread_runtime",
    }


def maybe_advance_conversation_thread(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    tick: int = 0,
) -> Dict[str, Any]:
    """Create/advance one bounded NPC-to-NPC conversation thread.

    Deterministic v1 trigger:
    - player waits/listens/idles/observes
    - current location has at least two present NPCs

    This function intentionally mutates only:
    - conversation_thread_state
    - world_event_state via bounded npc_conversation event
    """
    simulation_state = _safe_dict(simulation_state)
    state = ensure_conversation_thread_state(simulation_state)
    location_id = current_location_id(simulation_state)
    location = get_location(location_id)

    if not is_ambient_wait_or_listen_intent(player_input):
        state["debug"] = {
            "last_triggered": False,
            "reason": "not_wait_or_listen_turn",
            "location_id": location_id,
        }
        return {
            "triggered": False,
            "reason": "not_wait_or_listen_turn",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }

    participants = select_conversation_participants(simulation_state, limit=2)
    if len(participants) < 2:
        state["debug"] = {
            "last_triggered": False,
            "reason": "not_enough_present_npcs",
            "location_id": location_id,
            "present_npc_count": len(participants),
        }
        return {
            "triggered": False,
            "reason": "not_enough_present_npcs",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }

    topic_payload = _topic_for_location(location_id)
    thread_id = _thread_id_for(location_id=location_id, participants=participants)
    existing = _find_thread(state, thread_id)

    if existing:
        thread = existing
    else:
        thread = {
            "thread_id": thread_id,
            "location_id": location_id,
            "location_name": _safe_str(location.get("name")),
            "participants": deepcopy(participants),
            "topic_id": _safe_str(topic_payload.get("topic_id")),
            "topic": _safe_str(topic_payload.get("topic")),
            "status": "active",
            "beats": [],
            "world_signals": [],
            "created_tick": int(tick or 0),
            "updated_tick": int(tick or 0),
            "source": "deterministic_conversation_thread_runtime",
        }
        threads = _safe_list(state.get("threads"))
        threads.append(thread)
        if len(threads) > MAX_CONVERSATION_THREADS:
            del threads[:-MAX_CONVERSATION_THREADS]
        state["threads"] = threads

    beats = _safe_list(thread.get("beats"))
    beat_index = len(beats) + 1
    if beat_index > MAX_BEATS_PER_THREAD:
        thread["status"] = "paused"
        state["debug"] = {
            "last_triggered": False,
            "reason": "thread_beat_limit_reached",
            "thread_id": thread_id,
            "location_id": location_id,
        }
        return {
            "triggered": False,
            "reason": "thread_beat_limit_reached",
            "thread": deepcopy(thread),
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }

    beat = _make_beat(
        thread_id=thread_id,
        participants=participants,
        location_id=location_id,
        tick=tick,
        beat_index=beat_index,
        topic_payload=topic_payload,
    )
    beats.append(beat)
    thread["beats"] = beats
    thread["updated_tick"] = int(tick or 0)

    signal = {
        "signal_id": f"world_signal:conversation:{int(tick or 0)}:{thread_id}:{beat_index}",
        "kind": _safe_str(topic_payload.get("signal_kind")),
        "strength": 1,
        "topic_id": _safe_str(topic_payload.get("topic_id")),
        "summary": _safe_str(topic_payload.get("summary")),
        "source_thread_id": thread_id,
        "source_beat_id": _safe_str(beat.get("beat_id")),
        "location_id": location_id,
        "tick": int(tick or 0),
        "source": "deterministic_conversation_thread_runtime",
    }
    signal = _append_world_signal(state, signal)
    thread_signals = _safe_list(thread.get("world_signals"))
    thread_signals.append(signal)
    if len(thread_signals) > MAX_BEATS_PER_THREAD:
        del thread_signals[:-MAX_BEATS_PER_THREAD]
    thread["world_signals"] = thread_signals

    active_ids = _safe_list(state.get("active_thread_ids"))
    if thread_id not in active_ids:
        active_ids.append(thread_id)
    state["active_thread_ids"] = active_ids[-MAX_CONVERSATION_THREADS:]

    world_event = add_world_event(
        simulation_state,
        {
            "event_id": f"world:event:npc_conversation:{int(tick or 0)}:{thread_id}:{beat_index}",
            "kind": "npc_conversation",
            "title": "NPC conversation",
            "summary": f"{beat['speaker_name']} speaks with {beat['listener_name']} about {beat['topic']}.",
            "thread_id": thread_id,
            "beat_id": beat["beat_id"],
            "location_id": location_id,
            "tick": int(tick or 0),
            "source": "deterministic_conversation_thread_runtime",
        },
    )

    state["debug"] = {
        "last_triggered": True,
        "reason": "wait_or_listen_turn",
        "thread_id": thread_id,
        "beat_id": beat["beat_id"],
        "participant_ids": [_safe_str(p.get("id")) for p in participants],
        "location_id": location_id,
    }

    return {
        "triggered": True,
        "reason": "wait_or_listen_turn",
        "thread": deepcopy(thread),
        "beat": deepcopy(beat),
        "world_signal": deepcopy(signal),
        "world_event": deepcopy(world_event),
        "conversation_thread_state": get_conversation_thread_state(simulation_state),
        "source": "deterministic_conversation_thread_runtime",
    }
