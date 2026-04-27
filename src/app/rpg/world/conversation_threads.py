from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.session.ambient_intent import is_ambient_wait_or_listen_intent
from app.rpg.world.conversation_effects import (
    build_conversation_world_signal,
    strip_forbidden_conversation_effects,
    validate_conversation_effects,
)
from app.rpg.world.conversation_pivots import detect_conversation_topic_pivot
from app.rpg.world.conversation_rumor_propagation import (
    add_rumor_seed,
    expire_stale_signals,
)
from app.rpg.world.conversation_settings import normalize_conversation_settings
from app.rpg.world.conversation_social_state import (
    choose_npc_response_style,
    get_npc_relationship_summary,
    record_npc_response_beat,
    record_player_joined_conversation,
)
from app.rpg.world.conversation_director import select_conversation_intent
from app.rpg.world.npc_history_state import add_npc_history_entry, prune_npc_history_state
from app.rpg.world.npc_reputation_state import (
    get_npc_reputation,
    response_style_from_reputation,
    update_npc_reputation,
)
from app.rpg.world.conversation_topics import (
    detect_topic_pivot_hint,
    select_conversation_topic,
    topic_is_backed_by_state,
)
from app.rpg.world.location_registry import (
    current_location_id,
    get_location,
    present_npcs_for_current_location,
)
from app.rpg.world.npc_biography_registry import get_npc_biography
from app.rpg.world.npc_dialogue_profile import (
    build_npc_dialogue_profile,
    deterministic_biography_line,
)
from app.rpg.world.npc_goal_state import (
    dominant_goal_for_npc,
    goal_topic_bias,
    record_goal_influence,
    response_style_from_goal,
    seed_default_npc_goals,
)
from app.rpg.world.world_event_log import add_world_event

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
    if not isinstance(state.get("pending_player_response"), dict):
        state["pending_player_response"] = {}
    if not isinstance(state.get("cooldowns"), dict):
        state["cooldowns"] = {}
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
    participation_mode: str = "overheard",
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
        "line": _conversation_line_for_topic(
            speaker=speaker,
            location_id=location_id,
            beat_index=beat_index,
            topic=topic_payload,
            participation_mode=participation_mode,
        ),
        "topic_id": _safe_str(topic_payload.get("topic_id")),
        "topic_type": _safe_str(topic_payload.get("topic_type")),
        "topic": _safe_str(topic_payload.get("title") or topic_payload.get("topic")),
        "tick": int(tick or 0),
        "source": "deterministic_conversation_thread_runtime",
    }


def _deterministic_percent(seed: str, tick: int) -> int:
    total = sum(ord(ch) for ch in _safe_str(seed))
    return (total + int(tick or 0) * 37 + 19) % 100


def _select_participation_mode(
    *,
    settings: Dict[str, Any],
    topic: Dict[str, Any],
    tick: int,
    force_player_mode: str = "",
) -> str:
    if force_player_mode in {"overheard", "player_addressed", "player_invited"}:
        return force_player_mode

    settings = normalize_conversation_settings(settings)
    if not settings.get("allow_player_addressed") and not settings.get("allow_player_invited"):
        return "overheard"

    chance = int(settings.get("player_inclusion_chance_percent") or 0)
    if chance <= 0:
        return "overheard"

    bucket = _deterministic_percent(_safe_str(topic.get("topic_id")), tick)
    if bucket >= chance:
        return "overheard"

    if settings.get("allow_player_invited"):
        return "player_invited"
    if settings.get("allow_player_addressed"):
        return "player_addressed"
    return "overheard"


def _apply_goal_bias_to_player_inclusion(
    simulation_state: Dict[str, Any],
    *,
    settings: Dict[str, Any],
    participants: List[Dict[str, Any]],
    tick: int,
    location_id: str,
) -> Dict[str, Any]:
    """Adjust player_inclusion_chance_percent based on the dominant NPC goal."""
    if not settings.get("allow_npc_goal_influence", True):
        return {"settings": settings, "goal_bias": 0, "goal": {}}
    seed_default_npc_goals(simulation_state, tick=tick, location_id=location_id)
    speaker = _safe_dict(participants[0] if participants else {})
    npc_id = _safe_str(speaker.get("id"))
    goal = dominant_goal_for_npc(simulation_state, npc_id, tick=tick, location_id=location_id)
    bias_payload = goal_topic_bias(goal)
    cap = max(0, _safe_int(settings.get("goal_player_invitation_bias_cap"), 20))
    bias = max(-cap, min(cap, _safe_int(bias_payload.get("player_invitation_bias"), 0)))
    if not bias:
        return {"settings": settings, "goal_bias": 0, "goal": goal}
    adjusted = dict(settings)
    adjusted["player_inclusion_chance_percent"] = max(
        0,
        min(100, _safe_int(settings.get("player_inclusion_chance_percent"), 0) + bias),
    )
    record_goal_influence(
        simulation_state,
        tick=tick,
        npc_id=npc_id,
        goal=goal,
        influence_kind="player_invitation_bias",
        details={"bias": bias, "adjusted_chance": adjusted["player_inclusion_chance_percent"]},
    )
    return {"settings": adjusted, "goal_bias": bias, "goal": goal}


def _player_participation_payload(
    *,
    mode: str,
    topic: Dict[str, Any],
    tick: int,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    pending = mode == "player_invited"
    return {
        "included": mode in {"player_addressed", "player_invited", "player_joined"},
        "mode": mode,
        "pending_response": pending,
        "prompt": (
            f"NPCs invite your response about {_safe_str(topic.get('title') or topic.get('topic_id'))}."
            if pending
            else ""
        ),
        "topic_id": _safe_str(topic.get("topic_id")),
        "created_tick": int(tick or 0) if pending else 0,
        "expires_tick": int(tick or 0) + int(settings.get("pending_response_timeout_ticks") or 3) if pending else 0,
    }


def _thread_on_cooldown(
    state: Dict[str, Any],
    *,
    thread_id: str,
    tick: int,
) -> bool:
    cooldowns = _safe_dict(state.get("cooldowns"))
    until = _safe_int(cooldowns.get(thread_id), 0)
    return bool(until and int(tick or 0) < until)


def _set_thread_cooldown(
    state: Dict[str, Any],
    *,
    thread_id: str,
    tick: int,
    settings: Dict[str, Any],
) -> None:
    cooldowns = _safe_dict(state.get("cooldowns"))
    cooldowns[thread_id] = int(tick or 0) + int(settings.get("thread_cooldown_ticks") or 0)
    state["cooldowns"] = cooldowns


def _conversation_line_for_topic(
    *,
    speaker: Dict[str, Any],
    location_id: str,
    beat_index: int,
    topic: Dict[str, Any],
    participation_mode: str,
) -> str:
    topic_type = _safe_str(topic.get("topic_type"))
    facts = _safe_list(topic.get("allowed_facts"))
    fact = _safe_str(facts[0] if facts else topic.get("summary"))
    speaker_id = _safe_str(speaker.get("npc_id") or speaker.get("id"))
    profile = build_npc_dialogue_profile(
        npc_id=speaker_id,
        simulation_state={},
        runtime_state={},
        topic=topic,
        listener_id="",
        response_intent="ambient_comment",
    )
    role = _safe_str(profile.get("role")).lower()

    if participation_mode == "player_invited":
        if "tavern" in role:
            return f"You look like you have ears worth using. What do you make of this: {fact}"
        if "informant" in role:
            return f"You heard that too, didn't you? {fact}"
        if "guard" in role:
            return f"If you know anything useful about this, say it plainly: {fact}"
        return f"What do you make of this: {fact}"
    if participation_mode == "player_addressed":
        if "tavern" in role:
            return f"You heard the room turning that over too: {fact}"
        if "informant" in role:
            return f"You noticed the same thread, I expect: {fact}"
        if "guard" in role:
            return f"You heard the report as well: {fact}"
        return f"You heard the talk about this too: {fact}"

    if topic_type == "quest":
        if "tavern" in role:
            return f"People do not avoid a road for nothing. {fact}"
        if "informant" in role:
            return f"That keeps coming up in whispers: {fact}"
        if "guard" in role:
            return f"Reports agree on this much: {fact}"
        return f"I keep hearing about it: {fact}"
    if topic_type == "recent_event":
        if "tavern" in role:
            return f"It has the room talking into their cups: {fact}"
        if "informant" in role:
            return f"Everyone repeats it differently, but this part stays the same: {fact}"
        if "guard" in role:
            return f"Recent reports mention this: {fact}"
        return f"That recent trouble still has people talking: {fact}"
    if topic_type == "rumor":
        if "tavern" in role:
            return f"Taverns breed rumors, but this one keeps returning: {fact}"
        if "informant" in role:
            return f"The rumor is not proof, but it has a shape: {fact}"
        if "guard" in role:
            return f"I would call that unverified, but worth noting: {fact}"
        return f"Rumor has it: {fact}"
    if topic_type == "memory":
        return f"People remember this clearly: {fact}"

    return _line_for_participant(
        speaker,
        location_id=location_id,
        beat_index=beat_index,
    )


def _biography_grounded_npc_response(
    *,
    speaker_id: str,
    listener_id: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
    topic: Dict[str, Any] | None = None,
    pivot: Dict[str, Any] | None = None,
    response_style: str = "",
    response_intent: str = "answer",
) -> Dict[str, Any]:
    profile = build_npc_dialogue_profile(
        npc_id=speaker_id,
        simulation_state=simulation_state,
        runtime_state=runtime_state or {},
        topic=topic or {},
        listener_id=listener_id,
        response_intent=response_intent,
    )
    line_payload = deterministic_biography_line(
        profile=profile,
        topic=topic or {},
        pivot=pivot or {},
        response_style=response_style,
    )
    return {
        "profile": profile,
        "line_payload": line_payload,
        "line": _safe_str(line_payload.get("line")),
        "biography_role": _safe_str(line_payload.get("biography_role")),
        "roleplay_source": _safe_str(line_payload.get("roleplay_source") or "deterministic_template"),
        "used_fact_ids": _safe_list(line_payload.get("used_fact_ids")),
        "response_style": _safe_str(line_payload.get("response_style") or response_style),
        "source": "deterministic_biography_grounded_npc_response",
    }


# ── Bundle H: NPC response beat after player joins ───────────────────────────


def _npc_response_line_for_player_join(
    *,
    topic: Dict[str, Any],
    topic_pivot: Dict[str, Any],
    response_style: str,
    recent_lines: List[str] | None = None,
) -> str:
    """Deterministic NPC reply line after player joins conversation.

    Picks from 3 candidates per style, avoiding lines already in recent_lines.
    Hard constraint: never creates quests, rewards, or inventory changes.
    """
    topic = _safe_dict(topic)
    facts = _safe_list(topic.get("allowed_facts"))
    fact = _safe_str(facts[0] if facts else topic.get("summary"))
    title = _safe_str(topic.get("title") or topic.get("topic") or topic.get("topic_id"))
    recent = {_safe_str(line).strip().lower() for line in (recent_lines or []) if _safe_str(line).strip()}
    candidates: List[str]
    if topic_pivot.get("requested") and not topic_pivot.get("accepted"):
        candidates = [
            "I have no reliable word of that. I will not dress guesses up as fact.",
            "That is not something I can ground in anything known here.",
            "If that tale is true, it has not reached this room as more than smoke.",
        ]
    elif response_style == "helpful":
        candidates = [
            f"Aye. What I know is this: {fact}",
            f"The useful part is this: {fact}",
            f"If you need something solid, start here: {fact}",
        ]
    elif response_style == "friendly":
        candidates = [
            f"I can tell you this much about {title}: {fact}",
            f"Since you ask plain, here it is: {fact}",
            f"Between us, the talk around {title} is simple enough: {fact}",
        ]
    elif response_style == "annoyed":
        candidates = [
            f"Mind your tone. Still, the fact of it is: {fact}",
            f"You ask like you expect trouble. The answer is: {fact}",
            f"Fine. But do not make a scene of it: {fact}",
        ]
    elif response_style == "evasive":
        candidates = [
            f"People are careful when speaking about {title}.",
            f"I would not say more than this: {fact}",
            f"That is the sort of matter best spoken of quietly: {fact}",
        ]
    else:
        candidates = [
            f"That's what folk are saying about {title}: {fact}",
            f"The talk comes back to this: {fact}",
            f"What reaches my ears is this: {fact}",
        ]
    for line in candidates:
        if line.strip().lower() not in recent:
            return line
    return candidates[0]


def _make_npc_response_beat(
    *,
    npc: Dict[str, Any],
    thread: Dict[str, Any],
    topic: Dict[str, Any],
    topic_pivot: Dict[str, Any],
    response_style: str,
    tick: int,
    thread_id: str,
    beat_index: int,
) -> Dict[str, Any]:
    """Build an NPC response beat dict with avoid-repeat logic."""
    recent_lines = [
        _safe_str(beat.get("line"))
        for beat in _safe_list(_safe_dict(thread).get("beats"))
        if _safe_str(beat.get("speaker_id")).startswith("npc:")
    ]
    return {
        "beat_id": f"conversation:npc_response:{int(tick or 0)}:{thread_id}:{beat_index}",
        "thread_id": thread_id,
        "beat_index": beat_index,
        "speaker_id": _safe_str(npc.get("id")),
        "speaker_name": _safe_str(npc.get("name")),
        "listener_id": "player",
        "listener_name": "Player",
        "line": _npc_response_line_for_player_join(
            topic=topic,
            topic_pivot=topic_pivot,
            response_style=response_style,
            recent_lines=recent_lines,
        ),
        "topic_id": _safe_str(topic.get("topic_id")),
        "topic_type": _safe_str(topic.get("topic_type")),
        "topic": _safe_str(topic.get("title") or topic.get("topic")),
        "tick": int(tick or 0),
        "response_style": response_style,
        "participation_mode": "player_joined",
        "source": "deterministic_conversation_thread_runtime",
    }


def maybe_advance_conversation_thread(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    tick: int = 0,
    settings: Dict[str, Any] | None = None,
    autonomous: bool = False,
    force: bool = False,
    force_player_mode: str = "",
    forced_topic_type: str = "",
    exclude_event_ids: List[str] | None = None,
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
    settings = normalize_conversation_settings(settings or {})
    location_id = current_location_id(simulation_state)
    location = get_location(location_id)

    # J2: expire stale rumor seeds before advancing the conversation.
    expire_stale_signals(simulation_state, current_tick=tick, settings=settings)

    if not settings.get("enabled", True):
        return {
            "triggered": False,
            "reason": "conversation_settings_disabled",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }

    if not force and not autonomous and not is_ambient_wait_or_listen_intent(player_input):
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

    seed_default_npc_goals(simulation_state, tick=tick, location_id=location_id)

    # QRS: Prune NPC history before starting a new conversation beat.
    prune_npc_history_state(
        simulation_state,
        current_tick=tick,
        max_entries_per_npc=int(settings.get("npc_history_max_entries_per_npc") or 20),
    )

    # QRS: Ask the conversation director for a preferred intent.
    director_intent: Dict[str, Any] = {}
    if settings.get("conversation_director_enabled", True):
        director_intent = select_conversation_intent(
            simulation_state,
            settings=settings,
            tick=tick,
        )

    if director_intent.get("selected"):
        speaker_npc_id = _safe_str(director_intent.get("speaker_id"))
        listener_npc_id = _safe_str(director_intent.get("listener_id"))
        speaker_bio = get_npc_biography(speaker_npc_id)
        listener_bio = get_npc_biography(listener_npc_id)
        participants = [
            {
                "id": speaker_npc_id,
                "name": _safe_str(speaker_bio.get("name")) or speaker_npc_id.replace("npc:", ""),
                "role": "",
            },
            {
                "id": listener_npc_id,
                "name": _safe_str(listener_bio.get("name")) or listener_npc_id.replace("npc:", ""),
                "role": "",
            },
        ]
        topic_payload = _safe_dict(director_intent.get("topic")) or {}
    else:
        topic_payload = select_conversation_topic(
            simulation_state,
            settings=settings,
            forced_topic_type=forced_topic_type,
            exclude_event_ids=exclude_event_ids or [],
        )
        if not topic_payload:
            topic_payload = _topic_for_location(location_id)
    if not topic_is_backed_by_state(topic_payload):
        return {
            "triggered": False,
            "reason": "conversation_topic_not_backed_by_state",
            "topic": topic_payload,
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }
    participation_mode = _select_participation_mode(
        settings=_safe_dict(
            _apply_goal_bias_to_player_inclusion(
                simulation_state,
                settings=settings,
                participants=participants,
                tick=tick,
                location_id=location_id,
            ).get("settings")
        ),
        topic=topic_payload,
        tick=tick,
        force_player_mode=force_player_mode,
    )
    thread_id = _thread_id_for(location_id=location_id, participants=participants)
    if _thread_on_cooldown(state, thread_id=thread_id, tick=tick):
        return {
            "triggered": False,
            "reason": "thread_on_cooldown",
            "thread_id": thread_id,
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }
    existing = _find_thread(state, thread_id)

    if existing:
        thread = existing
        if force_player_mode in {"overheard", "player_addressed", "player_invited"}:
            participation_mode = force_player_mode
            thread["participation_mode"] = participation_mode
            thread["player_participation"] = _player_participation_payload(
                mode=participation_mode,
                topic=topic_payload,
                tick=tick,
                settings=settings,
            )
        else:
            participation_mode = _safe_str(thread.get("participation_mode") or participation_mode or "overheard")
    else:
        # Enforce max_active_threads: don't open a new thread when the cap is reached.
        active_ids = _safe_list(state.get("active_thread_ids"))
        max_threads = max(1, _safe_int(settings.get("max_active_threads"), 2))
        if len(active_ids) >= max_threads:
            state["debug"] = {
                "last_triggered": False,
                "reason": "max_active_threads_reached",
                "location_id": location_id,
                "active_thread_count": len(active_ids),
                "max_active_threads": max_threads,
            }
            return {
                "triggered": False,
                "reason": "max_active_threads_reached",
                "active_thread_count": len(active_ids),
                "max_active_threads": max_threads,
                "conversation_thread_state": get_conversation_thread_state(simulation_state),
            }
        thread = {
            "thread_id": thread_id,
            "location_id": location_id,
            "location_name": _safe_str(location.get("name")),
            "participants": deepcopy(participants),
            "topic_id": _safe_str(topic_payload.get("topic_id")),
            "topic_type": _safe_str(topic_payload.get("topic_type")),
            "topic": _safe_str(topic_payload.get("title") or topic_payload.get("topic")),
            "topic_payload": deepcopy(topic_payload),
            "participation_mode": participation_mode,
            "player_participation": _player_participation_payload(
                mode=participation_mode,
                topic=topic_payload,
                tick=tick,
                settings=settings,
            ),
            "status": "active",
            "beats": [],
            "world_signals": [],
            "world_events": [],
            "player_responses": [],
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
    max_beats = int(settings.get("max_beats_per_thread") or MAX_BEATS_PER_THREAD)
    if beat_index > max_beats:
        thread["status"] = "paused"
        _set_thread_cooldown(state, thread_id=thread_id, tick=tick, settings=settings)
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
        participation_mode=participation_mode,
    )
    beats.append(beat)
    thread["beats"] = beats
    thread["updated_tick"] = int(tick or 0)

    signal = {}
    if settings.get("allow_world_signals", True):
        signal = build_conversation_world_signal(
            tick=tick,
            thread_id=thread_id,
            beat_id=_safe_str(beat.get("beat_id")),
            topic=topic_payload,
            settings=settings,
        )
        # Enforce max signals per thread.
        if len(_safe_list(thread.get("world_signals"))) < int(settings.get("max_world_signals_per_thread") or 0):
            signal = _append_world_signal(state, signal)
        else:
            signal = {}
    thread_signals = _safe_list(thread.get("world_signals"))
    if signal:
        thread_signals.append(signal)
    if len(thread_signals) > MAX_BEATS_PER_THREAD:
        del thread_signals[:-MAX_BEATS_PER_THREAD]
    thread["world_signals"] = thread_signals

    # J1: seed a rumor from eligible signals.
    rumor_seed = {}
    if signal:
        rumor_seed = add_rumor_seed(
            simulation_state,
            signal=signal,
            topic=topic_payload,
            tick=tick,
            location_id=location_id,
            settings=settings,
        )

    active_ids = _safe_list(state.get("active_thread_ids"))
    if thread_id not in active_ids:
        active_ids.append(thread_id)
    state["active_thread_ids"] = active_ids[-MAX_CONVERSATION_THREADS:]

    player_participation = _safe_dict(thread.get("player_participation"))
    if player_participation.get("pending_response"):
        state["pending_player_response"] = {
            "thread_id": thread_id,
            "topic_id": _safe_str(topic_payload.get("topic_id")),
            "prompt": _safe_str(player_participation.get("prompt")),
            "created_tick": int(tick or 0),
            "expires_tick": _safe_int(player_participation.get("expires_tick"), 0),
            "source": "deterministic_conversation_thread_runtime",
        }

    world_event = {}
    thread_world_event_count = len(_safe_list(thread.get("world_events")))
    if (
        settings.get("allow_world_events", True)
        and thread_world_event_count < int(settings.get("max_world_events_per_thread") or 0)
    ):
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
        thread_events = _safe_list(thread.get("world_events"))
        thread_events.append(world_event)
        thread["world_events"] = thread_events[-MAX_BEATS_PER_THREAD:]

    state["debug"] = {
        "last_triggered": True,
        "reason": "wait_or_listen_turn",
        "thread_id": thread_id,
        "beat_id": beat["beat_id"],
        "participant_ids": [_safe_str(p.get("id")) for p in participants],
        "location_id": location_id,
    }

    result = {
        "triggered": True,
        "reason": "wait_or_listen_turn",
        "autonomous": bool(autonomous),
        "participation_mode": participation_mode,
        "player_participation": deepcopy(_safe_dict(thread.get("player_participation"))),
        "topic": deepcopy(topic_payload),
        "thread": deepcopy(thread),
        "beat": deepcopy(beat),
        "world_signal": deepcopy(signal),
        "world_event": deepcopy(world_event),
        "rumor_seed": deepcopy(rumor_seed),
        "director_intent": deepcopy(director_intent),
        "present_npcs": _safe_list(
            director_intent.get("present_npcs")
            or _safe_dict(_safe_dict(simulation_state.get("conversation_director_state")).get("debug")).get("present_npcs")
        ),
        "npc_history_state": deepcopy(_safe_dict(simulation_state.get("npc_history_state"))),
        "npc_reputation_state": deepcopy(_safe_dict(simulation_state.get("npc_reputation_state"))),
        "conversation_thread_state": get_conversation_thread_state(simulation_state),
        "source": "deterministic_conversation_thread_runtime",
    }
    validation = validate_conversation_effects(result, settings=settings)
    result["conversation_effect_validation"] = validation
    result = strip_forbidden_conversation_effects(result)
    return result


def has_pending_player_conversation_response(
    simulation_state: Dict[str, Any],
    *,
    tick: int = 0,
) -> bool:
    state = ensure_conversation_thread_state(simulation_state)
    pending = _safe_dict(state.get("pending_player_response"))
    if not pending:
        return False
    # Return True even after expiry so the next player turn can clear the
    # stale pending response deterministically instead of leaving it stuck.
    return bool(_safe_str(pending.get("thread_id")))


def handle_pending_player_conversation_response(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    tick: int = 0,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    state = ensure_conversation_thread_state(simulation_state)
    settings = normalize_conversation_settings(settings or {})
    pending = _safe_dict(state.get("pending_player_response"))
    response_text = _safe_str(player_input).strip()
    if not pending:
        return {
            "triggered": False,
            "reason": "no_pending_player_response",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
            "source": "deterministic_conversation_thread_runtime",
        }
    if not response_text:
        return {
            "triggered": False,
            "reason": "empty_player_response",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
            "source": "deterministic_conversation_thread_runtime",
        }

    expires_tick = _safe_int(pending.get("expires_tick"), 0)
    if expires_tick and int(tick or 0) > expires_tick:
        state["pending_player_response"] = {}
        state["debug"] = {
            "last_triggered": False,
            "reason": "pending_player_response_expired",
            "expires_tick": expires_tick,
            "tick": int(tick or 0),
        }
        return {
            "triggered": False,
            "reason": "pending_player_response_expired",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
            "source": "deterministic_conversation_thread_runtime",
        }

    thread_id = _safe_str(pending.get("thread_id"))
    thread = _find_thread(state, thread_id)
    if not thread:
        state["pending_player_response"] = {}
        state["debug"] = {
            "last_triggered": False,
            "reason": "pending_player_response_stale_thread",
            "thread_id": thread_id,
        }
        return {
            "triggered": False,
            "reason": "pending_player_response_stale_thread",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
            "source": "deterministic_conversation_thread_runtime",
        }

    topic_payload = _safe_dict(thread.get("topic_payload"))
    participants = _safe_list(thread.get("participants"))
    listener = _safe_dict(participants[0] if participants else {})
    beats = _safe_list(thread.get("beats"))
    beat_index = len(beats) + 1
    player_response = {
        "beat_id": f"conversation:player_response:{int(tick or 0)}:{thread_id}:{beat_index}",
        "thread_id": thread_id,
        "beat_index": beat_index,
        "speaker_id": "player",
        "speaker_name": "Player",
        "listener_id": _safe_str(listener.get("id")),
        "listener_name": _safe_str(listener.get("name")),
        "line": response_text[:500],
        "topic_id": _safe_str(pending.get("topic_id") or topic_payload.get("topic_id") or thread.get("topic_id")),
        "topic_type": _safe_str(topic_payload.get("topic_type") or thread.get("topic_type")),
        "topic": _safe_str(topic_payload.get("title") or thread.get("topic")),
        "tick": int(tick or 0),
        "participation_mode": "player_joined",
        "source": "deterministic_conversation_thread_runtime",
    }
    beats.append(player_response)
    thread["beats"] = beats[-MAX_BEATS_PER_THREAD:]
    thread["updated_tick"] = int(tick or 0)
    thread["participation_mode"] = "player_joined"
    thread["player_participation"] = {
        "included": True,
        "mode": "player_joined",
        "pending_response": False,
        "topic_id": _safe_str(player_response.get("topic_id")),
        "responded_tick": int(tick or 0),
        "response_preview": response_text[:220],
        "source": "deterministic_conversation_thread_runtime",
    }
    responses = _safe_list(thread.get("player_responses"))
    responses.append(player_response)
    thread["player_responses"] = responses[-MAX_BEATS_PER_THREAD:]

    # ── Bundle H1: topic pivot detection ────────────────────────────────────
    topic_pivot = detect_conversation_topic_pivot(
        simulation_state,
        response_text,
        current_topic=topic_payload,
        settings=settings,
    )
    pivot_accepted = topic_pivot.get("accepted", False)
    active_topic = _safe_dict(topic_pivot.get("selected_topic")) if pivot_accepted else topic_payload

    if pivot_accepted:
        thread["topic_payload"] = deepcopy(active_topic)
        thread["topic_id"] = _safe_str(active_topic.get("topic_id"))
        thread["topic_type"] = _safe_str(active_topic.get("topic_type"))
        thread["topic"] = _safe_str(active_topic.get("title") or active_topic.get("topic"))

    # ── Bundle H1 + I1: NPC response beat ───────────────────────────────────
    npc_response_beat: Dict[str, Any] = {}
    response_style = ""
    if settings.get("allow_npc_response_beats", True) and participants:
        npc = _safe_dict(participants[0])
        npc_id = _safe_str(npc.get("id"))
        forced_speaker_id = _safe_str(settings.get("test_force_conversation_speaker_id"))
        if forced_speaker_id.startswith("npc:"):
            npc_id = forced_speaker_id
            npc["id"] = npc_id
            npc["name"] = _safe_str(get_npc_biography(forced_speaker_id).get("name")) or forced_speaker_id.replace("npc:", "")
        response_style = choose_npc_response_style(
            simulation_state,
            thread=thread,
            player_response=player_response,
            topic_pivot=topic_pivot,
            tick=tick,
            settings=settings,
        )
        # Goal-style override (only when not already in a negative mode)
        if settings.get("allow_npc_goal_influence", True):
            goal = dominant_goal_for_npc(
                simulation_state,
                npc_id,
                tick=tick,
                location_id=_safe_str(thread.get("location_id")),
            )
            goal_style = response_style_from_goal(goal)
            if goal_style and response_style not in {"evasive", "annoyed"}:
                response_style = goal_style
                record_goal_influence(
                    simulation_state,
                    tick=tick,
                    npc_id=npc_id,
                    goal=goal,
                    influence_kind="npc_response_style_override",
                    details={"response_style": response_style},
                )
        npc_beat_index = len(_safe_list(thread.get("beats"))) + 1
        biography_response = _biography_grounded_npc_response(
            speaker_id=_safe_str(npc.get("id")),
            listener_id="player",
            simulation_state=simulation_state,
            runtime_state={},
            topic=active_topic,
            pivot=topic_pivot,
            response_style=response_style,
            response_intent="answer" if _safe_dict(topic_pivot).get("accepted") else "deflect",
        )
        npc_response_beat = _make_npc_response_beat(
            npc=npc,
            thread=thread,
            topic=active_topic,
            topic_pivot=topic_pivot,
            response_style=response_style,
            tick=tick,
            thread_id=thread_id,
            beat_index=npc_beat_index,
        )
        if _safe_str(biography_response.get("line")):
            bio_line = _safe_str(biography_response.get("line"))
            recent_npc_lines = {
                _safe_str(beat.get("line")).strip().lower()
                for beat in _safe_list(thread.get("beats"))
                if _safe_str(beat.get("speaker_id")).startswith("npc:")
            }
            if bio_line.strip().lower() not in recent_npc_lines:
                npc_response_beat["line"] = bio_line
        npc_response_beat["biography_role"] = _safe_str(biography_response.get("biography_role"))
        npc_response_beat["roleplay_source"] = _safe_str(biography_response.get("roleplay_source") or "deterministic_template")
        npc_response_beat["used_fact_ids"] = _safe_list(biography_response.get("used_fact_ids"))
        npc_response_beat["dialogue_profile"] = _safe_dict(biography_response.get("profile"))

        # QRS: Override response style based on NPC reputation before appending beat.
        if settings.get("npc_reputation_enabled", True):
            reputation = get_npc_reputation(simulation_state, npc_id=npc_id)
            response_style = response_style_from_reputation(reputation, fallback=response_style)

        record_npc_response_beat(simulation_state, beat=npc_response_beat, tick=tick)
        all_beats = _safe_list(thread.get("beats"))
        all_beats.append(npc_response_beat)
        thread["beats"] = all_beats[-MAX_BEATS_PER_THREAD:]
        thread["updated_tick"] = int(tick or 0)

        # QRS: Record NPC history and update reputation from player interaction.
        responder_id = _safe_str(npc.get("id"))
        responder_name = _safe_str(npc.get("name")) or responder_id.replace("npc:", "")
        topic_title = _safe_str(active_topic.get("title") or active_topic.get("topic") or active_topic.get("topic_id"))
        topic_id_str = _safe_str(active_topic.get("topic_id"))
        if settings.get("npc_history_enabled", True):
            add_npc_history_entry(
                simulation_state,
                npc_id=responder_id,
                kind="player_conversation_reply",
                summary=f"The player replied to {responder_name} about {topic_title or topic_id_str}.",
                topic_id=topic_id_str,
                tick=tick,
                importance=2,
                ttl_ticks=int(settings.get("npc_history_ttl_ticks") or 1000),
            )
        if settings.get("npc_reputation_enabled", True):
            update_npc_reputation(
                simulation_state,
                npc_id=responder_id,
                tick=tick,
                familiarity_delta=1,
                trust_delta=1 if topic_pivot.get("accepted") else 0,
                annoyance_delta=1 if topic_pivot.get("requested") and not topic_pivot.get("accepted") else 0,
                reason="player_joined_conversation",
            )

    state["pending_player_response"] = {}

    world_event = {}
    thread_world_event_count = len(_safe_list(thread.get("world_events")))
    if (
        settings.get("allow_world_events", True)
        and thread_world_event_count < int(settings.get("max_world_events_per_thread") or 0)
    ):
        world_event = add_world_event(
            simulation_state,
            {
                "event_id": f"world:event:npc_conversation_player_response:{int(tick or 0)}:{thread_id}:{beat_index}",
                "kind": "npc_conversation_player_response",
                "title": "Player joined NPC conversation",
                "summary": f"The player responded to the conversation about {player_response['topic']}.",
                "thread_id": thread_id,
                "beat_id": player_response["beat_id"],
                "topic_id": _safe_str(player_response.get("topic_id")),
                "location_id": _safe_str(thread.get("location_id")),
                "tick": int(tick or 0),
                "source": "deterministic_conversation_thread_runtime",
            },
        )
        thread_events = _safe_list(thread.get("world_events"))
        if world_event:
            thread_events.append(world_event)
        thread["world_events"] = thread_events[-MAX_BEATS_PER_THREAD:]

    social_state = record_player_joined_conversation(
        simulation_state,
        tick=tick,
        thread=thread,
        player_response=player_response,
        topic=topic_payload,
    )

    state["debug"] = {
        "last_triggered": True,
        "reason": "pending_player_response_consumed",
        "thread_id": thread_id,
        "beat_id": player_response["beat_id"],
        "tick": int(tick or 0),
        "requested_topic_hint": topic_pivot["requested_topic_hint"],
        "pivot_result": "accepted" if pivot_accepted else "rejected",
        "selected_topic_id": topic_pivot["selected_topic_id"],
        "selected_topic_type": topic_pivot["selected_topic_type"],
        "pivot_rejected_reason": topic_pivot["pivot_rejected_reason"],
        "response_style": response_style,
        "response_style_source": "deterministic_conversation_social_state",
    }

    result = {
        "triggered": True,
        "reason": "pending_player_response_consumed",
        "autonomous": False,
        "participation_mode": "player_joined",
        "player_participation": deepcopy(_safe_dict(thread.get("player_participation"))),
        "player_response": deepcopy(player_response),
        "topic": deepcopy(active_topic),
        "topic_pivot": topic_pivot,
        "npc_response_beat": deepcopy(npc_response_beat),
        "dialogue_profile": deepcopy(_safe_dict(npc_response_beat.get("dialogue_profile"))),
        "roleplay_source": _safe_str(npc_response_beat.get("roleplay_source")),
        "used_fact_ids": _safe_list(npc_response_beat.get("used_fact_ids")),
        "npc_response_style": response_style,
        "thread": deepcopy(thread),
        "beat": deepcopy(player_response),
        "world_signal": {},
        "world_event": deepcopy(world_event),
        "conversation_social_state": deepcopy(social_state),
        "npc_goal_state": deepcopy(_safe_dict(simulation_state.get("npc_goal_state"))),
        "npc_history_state": deepcopy(_safe_dict(simulation_state.get("npc_history_state"))),
        "npc_reputation_state": deepcopy(_safe_dict(simulation_state.get("npc_reputation_state"))),
        "conversation_thread_state": get_conversation_thread_state(simulation_state),
        "source": "deterministic_conversation_thread_runtime",
    }
    validation = validate_conversation_effects(result, settings=settings)
    result["conversation_effect_validation"] = validation
    result = strip_forbidden_conversation_effects(result)
    return result


# Alias for test imports
maybe_consume_pending_player_response = handle_pending_player_conversation_response

