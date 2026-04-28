from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.session.ambient_intent import is_ambient_wait_or_listen_intent
from app.rpg.world.conversation_director import select_conversation_intent
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
    record_npc_response_beat,
    record_player_joined_conversation,
)
from app.rpg.world.conversation_topics import (
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
from app.rpg.world.npc_dialogue_recall import (
    find_recall_capable_npc,
    player_input_requests_recall,
)
from app.rpg.world.npc_goal_state import (
    dominant_goal_for_npc,
    goal_topic_bias,
    record_goal_influence,
    response_style_from_goal,
    seed_default_npc_goals,
)
from app.rpg.world.npc_history_state import (
    add_npc_history_entry,
    prune_npc_history_state,
)
from app.rpg.world.npc_knowledge_state import (
    add_npc_knowledge_from_topic,
    prune_npc_knowledge_state,
)
from app.rpg.world.npc_presence_runtime import present_npcs_at_location
from app.rpg.world.npc_reputation_state import (
    get_npc_reputation,
    response_style_from_reputation,
    update_npc_reputation,
)
from app.rpg.world.player_reputation_consequences import apply_player_reputation_consequence
from app.rpg.world.consequence_signals import emit_consequence_signals
from app.rpg.world.npc_evolution_triggers import evolve_npc_from_reputation_thresholds
from app.rpg.world.npc_referrals import suggest_npc_referral
from app.rpg.world.npc_party_eligibility import evaluate_npc_party_join_eligibility
from app.rpg.world.companion_join_intent import maybe_create_companion_join_intent
from app.rpg.world.npc_arc_continuity import update_npc_arc_continuity
from app.rpg.world.quest_conversation_access import (
    evaluate_quest_conversation_access,
    filter_allowed_topic_facts_for_access,
    requested_topic_access_from_pivot,
)
from app.rpg.world.quest_rumor_propagation import (
    maybe_seed_quest_rumor_from_conversation,
    prune_quest_rumors,
)
from app.rpg.world.scene_continuity_state import (
    update_scene_continuity_from_conversation,
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
        _safe_str(participant.get("npc_id") or participant.get("id"))
        for participant in participants
        if _safe_str(participant.get("npc_id") or participant.get("id"))
    ]

    # NPC-to-NPC conversations should have a stable thread identity regardless
    # of who speaks first on a given tick. Bran->Mira and Mira->Bran are the
    # same conversation thread; individual beats still preserve direction via
    # speaker_id/listener_id.
    npc_ids = [value for value in participant_ids if value.startswith("npc:")]
    non_npc_ids = [value for value in participant_ids if not value.startswith("npc:")]
    if len(npc_ids) >= 2 and not non_npc_ids:
        participant_ids = sorted(set(npc_ids))

    return f"conversation:{location_id}:{':'.join(participant_ids)}"


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


def _apply_forced_player_invite_to_thread(
    *,
    state: Dict[str, Any],
    thread: Dict[str, Any],
    topic_payload: Dict[str, Any],
    tick: int,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """Force a pending player response onto an active thread.

    This is used only for explicit player-invited ticks. It does not mutate
    inventory, currency, quests, journal, location, stock, rewards, or combat.
    """
    thread = _safe_dict(thread)
    state = _safe_dict(state)
    topic_payload = _safe_dict(topic_payload)

    thread_id = _safe_str(thread.get("thread_id"))
    topic_id = _safe_str(
        topic_payload.get("topic_id")
        or thread.get("topic_id")
    )
    topic_type = _safe_str(
        topic_payload.get("topic_type")
        or thread.get("topic_type")
    )
    prompt = _safe_str(
        topic_payload.get("prompt")
        or topic_payload.get("summary")
        or topic_payload.get("title")
        or thread.get("topic")
        or "The NPC invites your response."
    )

    timeout_ticks = max(
        1,
        _safe_int(settings.get("pending_response_timeout_ticks"), 3),
    )
    created_tick = int(tick or 0)
    expires_tick = created_tick + timeout_ticks

    pending = {
        "thread_id": thread_id,
        "topic_id": topic_id,
        "topic_type": topic_type,
        "prompt": prompt[:280],
        "created_tick": created_tick,
        "expires_tick": expires_tick,
        "source": "deterministic_forced_player_invite_runtime",
    }

    participation = _safe_dict(thread.get("player_participation"))
    participation.update(
        {
            "included": True,
            "mode": "player_invited",
            "pending_response": True,
            "prompt": pending["prompt"],
            "topic_id": topic_id,
            "topic_type": topic_type,
            "created_tick": created_tick,
            "expires_tick": expires_tick,
        }
    )

    thread["participation_mode"] = "player_invited"
    thread["player_participation"] = participation
    thread["updated_tick"] = created_tick
    state["pending_player_response"] = pending

    return {
        "pending_player_response": deepcopy(pending),
        "player_participation": deepcopy(participation),
        "source": "deterministic_forced_player_invite_runtime",
    }


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
    player_input: str = "",
    topic: Dict[str, Any] | None = None,
    pivot: Dict[str, Any] | None = None,
    response_style: str = "",
    response_intent: str = "answer",
) -> Dict[str, Any]:
    profile_runtime_state = dict(_safe_dict(runtime_state))
    profile_runtime_state["player_input"] = _safe_str(player_input)
    profile_runtime_state["latest_player_input"] = _safe_str(player_input)
    profile_runtime_state.setdefault("enable_dialogue_recall", True)

    profile = build_npc_dialogue_profile(
        npc_id=speaker_id,
        simulation_state=simulation_state,
        runtime_state=profile_runtime_state,
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
        "dialogue_recall": _safe_dict(profile.get("dialogue_recall")),
        "recalled_history_ids": [
            _safe_str(recall.get("source_history_id"))
            for recall in _safe_list(_safe_dict(profile.get("dialogue_recall")).get("recalls"))
            if _safe_str(recall.get("source_history_id"))
        ],
        "recalled_knowledge_ids": [
            _safe_str(recall.get("source_knowledge_id"))
            for recall in _safe_list(_safe_dict(profile.get("dialogue_recall")).get("recalls"))
            if _safe_str(recall.get("source_knowledge_id"))
        ],
        "response_style": _safe_str(line_payload.get("response_style") or response_style),
        "source": "deterministic_biography_grounded_npc_response",
    }


def _consume_recall_request_as_conversation_reply(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    tick: int,
    settings: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Handle direct player recall questions even when no pending invite exists.

    This creates a presentation/conversation beat only. It does not mutate
    quest/reward/journal/inventory/currency/location/combat state.
    """
    if not player_input_requests_recall(player_input):
        return {
            "triggered": False,
            "reason": "not_recall_request",
        }

    location_id = current_location_id(simulation_state)
    candidate_npcs = present_npcs_at_location(simulation_state, location_id=location_id)
    if not candidate_npcs:
        candidate_npcs = ["npc:Bran", "npc:Mira"]

    # Prefer a current/recent topic when available, but recall selection can
    # work without topic overlap because the player explicitly asked to recall.
    conversation_state = _safe_dict(simulation_state.get("conversation_thread_state"))
    topic_payload: Dict[str, Any] = {}
    threads = _safe_list(conversation_state.get("threads"))
    if threads:
        latest_thread = _safe_dict(threads[-1])
        topic_payload = _safe_dict(latest_thread.get("topic_payload"))

    recall_choice = find_recall_capable_npc(
        simulation_state,
        candidate_npc_ids=candidate_npcs,
        player_input=player_input,
        topic=topic_payload,
        tick=tick,
    )
    if not recall_choice.get("selected"):
        return {
            "triggered": False,
            "reason": _safe_str(recall_choice.get("reason")) or "no_recall_available",
            "recall_choice": recall_choice,
        }

    responder_id = _safe_str(recall_choice.get("npc_id"))
    responder_bio = get_npc_biography(responder_id)
    responder_name = _safe_str(responder_bio.get("name")) or responder_id.replace("npc:", "")

    # Force the profile to see the recall request text.
    profile_runtime_state = dict(_safe_dict(runtime_state))
    profile_runtime_state["player_input"] = _safe_str(player_input)
    profile_runtime_state["latest_player_input"] = _safe_str(player_input)
    profile_runtime_state["tick"] = int(tick or 0)
    profile_runtime_state["enable_dialogue_recall"] = True

    biography_response = _biography_grounded_npc_response(
        speaker_id=responder_id,
        listener_id="player",
        simulation_state=simulation_state,
        runtime_state=profile_runtime_state,
        player_input=player_input,
        topic=topic_payload,
        pivot={},
        response_style="helpful",
        response_intent="recall",
    )

    dialogue_recall = _safe_dict(biography_response.get("dialogue_recall"))
    recalled_history_ids = _safe_list(biography_response.get("recalled_history_ids"))
    recalled_knowledge_ids = _safe_list(biography_response.get("recalled_knowledge_ids"))
    line = _safe_str(biography_response.get("line"))
    if not line:
        recalls = _safe_list(dialogue_recall.get("recalls"))
        summary = _safe_str(_safe_dict(recalls[0]).get("summary")) if recalls else ""
        line = f"I remember this: {summary}" if summary else "I remember you asking, but not enough to add more."

    thread_id = f"conversation:{location_id}:{responder_id}:player:recall"
    thread = _find_thread(conversation_state, thread_id)
    if not thread:
        thread = {
            "thread_id": thread_id,
            "participants": [
                {"npc_id": responder_id, "name": responder_name},
                {"npc_id": "player", "name": "Player"},
            ],
            "location_id": location_id,
            "topic_id": _safe_str(topic_payload.get("topic_id")),
            "topic_type": _safe_str(topic_payload.get("topic_type")),
            "topic": _safe_str(topic_payload.get("title") or topic_payload.get("summary") or "Recall"),
            "topic_payload": deepcopy(topic_payload),
            "participation_mode": "player_joined",
            "player_participation": {
                "included": True,
                "mode": "player_joined",
                "pending_response": False,
                "topic_id": _safe_str(topic_payload.get("topic_id")),
            },
            "beats": [],
            "status": "active",
            "created_tick": int(tick or 0),
            "updated_tick": int(tick or 0),
            "source": "deterministic_recall_request_runtime",
        }
        threads.append(thread)
        conversation_state["threads"] = threads[-MAX_CONVERSATION_THREADS:]

    player_response_beat = {
        "beat_id": f"conversation:beat:{int(tick or 0)}:{thread_id}:player_recall_request",
        "thread_id": thread_id,
        "speaker_id": "player",
        "speaker_name": "Player",
        "listener_id": responder_id,
        "listener_name": responder_name,
        "line": _safe_str(player_input),
        "topic_id": _safe_str(topic_payload.get("topic_id")),
        "topic_type": _safe_str(topic_payload.get("topic_type")),
        "topic": _safe_str(topic_payload.get("title") or topic_payload.get("summary") or "Recall"),
        "tick": int(tick or 0),
        "participation_mode": "player_joined",
        "source": "deterministic_recall_request_runtime",
    }

    npc_response_beat = {
        "beat_id": f"conversation:beat:{int(tick or 0)}:{thread_id}:npc_recall_response",
        "thread_id": thread_id,
        "speaker_id": responder_id,
        "speaker_name": responder_name,
        "listener_id": "player",
        "listener_name": "Player",
        "line": line,
        "topic_id": _safe_str(topic_payload.get("topic_id")),
        "topic_type": _safe_str(topic_payload.get("topic_type")),
        "topic": _safe_str(topic_payload.get("title") or topic_payload.get("summary") or "Recall"),
        "tick": int(tick or 0),
        "participation_mode": "player_joined",
        "response_style": _safe_str(biography_response.get("response_style") or "helpful"),
        "biography_role": _safe_str(biography_response.get("biography_role")),
        "roleplay_source": _safe_str(biography_response.get("roleplay_source") or "deterministic_template"),
        "used_fact_ids": _safe_list(biography_response.get("used_fact_ids")),
        "dialogue_profile": _safe_dict(biography_response.get("profile")),
        "dialogue_recall": dialogue_recall,
        "recalled_history_ids": recalled_history_ids,
        "recalled_knowledge_ids": recalled_knowledge_ids,
        "source": "deterministic_recall_request_runtime",
    }

    beats = _safe_list(thread.get("beats"))
    beats.extend([player_response_beat, npc_response_beat])
    thread["beats"] = beats[-MAX_BEATS_PER_THREAD:]
    thread["updated_tick"] = int(tick or 0)
    thread["participation_mode"] = "player_joined"
    thread["player_participation"] = {
        "included": True,
        "mode": "player_joined",
        "pending_response": False,
        "topic_id": _safe_str(topic_payload.get("topic_id")),
    }

    conversation_state["pending_player_response"] = {}
    simulation_state["conversation_thread_state"] = conversation_state

    return {
        "triggered": True,
        "reason": "recall_request_consumed",
        "participation_mode": "player_joined",
        "thread": deepcopy(thread),
        "beat": deepcopy(player_response_beat),
        "npc_response_beat": deepcopy(npc_response_beat),
        "player_participation": deepcopy(thread["player_participation"]),
        "dialogue_profile": deepcopy(_safe_dict(npc_response_beat.get("dialogue_profile"))),
        "dialogue_recall": deepcopy(dialogue_recall),
        "recalled_history_ids": recalled_history_ids,
        "recalled_knowledge_ids": recalled_knowledge_ids,
        "conversation_thread_state": get_conversation_thread_state(simulation_state),
        "source": "deterministic_recall_request_runtime",
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

    forced_invite_payload = {}

    # J2: expire stale rumor seeds before advancing the conversation.
    expire_stale_signals(simulation_state, current_tick=tick, settings=settings)

    if not settings.get("enabled", True):
        return {
            "triggered": False,
            "reason": "conversation_settings_disabled",
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }

    if (
        settings.get("npc_dialogue_recall_enabled", True)
        and not _safe_dict(state.get("pending_player_response"))
        and player_input_requests_recall(player_input)
    ):
        recall_result = _consume_recall_request_as_conversation_reply(
            simulation_state,
            player_input=player_input,
            tick=tick,
            settings=settings,
            runtime_state={"tick": int(tick or 0), "player_input": player_input},
        )
        if recall_result.get("triggered"):
            return recall_result

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

    if force_player_mode == "player_invited":
        if not settings.get("allow_player_invited", False):
            return {
                "triggered": False,
                "reason": "forced_player_invited_disabled_by_settings",
                "participation_mode": "overheard",
                "player_participation": {
                    "included": False,
                    "mode": "overheard",
                    "pending_response": False,
                },
                "conversation_thread_state": get_conversation_thread_state(simulation_state),
            }
        participation_mode = "player_invited"
    thread_id = _thread_id_for(location_id=location_id, participants=participants)
    if _thread_on_cooldown(state, thread_id=thread_id, tick=tick) and force_player_mode != "player_invited":
        return {
            "triggered": False,
            "reason": "thread_on_cooldown",
            "thread_id": thread_id,
            "conversation_thread_state": get_conversation_thread_state(simulation_state),
        }
    existing = _find_thread(state, thread_id)

    if existing:
        thread = existing
        thread["last_participants"] = deepcopy(participants)
        participation_mode = _safe_str(thread.get("participation_mode") or participation_mode or "overheard")

        if force_player_mode == "player_invited":
            participation_mode = "player_invited"
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
        canonical_participants = participants
        npc_participants = [
            participant
            for participant in participants
            if _safe_str(participant.get("npc_id") or participant.get("id")).startswith("npc:")
        ]
        if len(npc_participants) >= 2 and len(npc_participants) == len(participants):
            canonical_participants = sorted(
                participants,
                key=lambda participant: _safe_str(participant.get("npc_id") or participant.get("id")),
            )

        thread = {
            "thread_id": thread_id,
            "location_id": location_id,
            "location_name": _safe_str(location.get("name")),
            "participants": canonical_participants,
            "last_participants": participants,
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

    if force_player_mode == "player_invited":
        forced_invite_payload = _apply_forced_player_invite_to_thread(
            state=state,
            thread=thread,
            topic_payload=topic_payload,
            tick=tick,
            settings=settings,
        )

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

    # W1: record NPC knowledge from backed topic for speaker and listener.
    if settings.get("npc_knowledge_enabled", True) and topic_is_backed_by_state(topic_payload):
        for _npc_id in {_safe_str(beat.get("speaker_id")), _safe_str(beat.get("listener_id"))}:
            if _npc_id.startswith("npc:"):
                add_npc_knowledge_from_topic(
                    simulation_state,
                    npc_id=_npc_id,
                    topic=topic_payload,
                    tick=tick,
                    confidence=2,
                    ttl_ticks=int(settings.get("npc_knowledge_ttl_ticks") or 2000),
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

    # Y1: update scene continuity from this NPC-to-NPC beat.
    if settings.get("scene_continuity_enabled", True):
        update_scene_continuity_from_conversation(
            simulation_state,
            location_id=location_id,
            topic_id=_safe_str(beat.get("topic_id")),
            topic_type=_safe_str(beat.get("topic_type")),
            speaker_id=_safe_str(beat.get("speaker_id")),
            listener_id=_safe_str(beat.get("listener_id")),
            tick=tick,
        )

    # W1: prune expired NPC knowledge.
    if settings.get("npc_knowledge_enabled", True):
        prune_npc_knowledge_state(
            simulation_state,
            current_tick=tick,
            max_known_facts_per_npc=int(settings.get("npc_knowledge_max_facts_per_npc") or 24),
        )

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
        "participation_mode": _safe_str(thread.get("participation_mode") or participation_mode),
        "player_participation": deepcopy(_safe_dict(thread.get("player_participation"))),
        "pending_player_response": deepcopy(_safe_dict(state.get("pending_player_response"))),
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
        "npc_knowledge_state": deepcopy(_safe_dict(simulation_state.get("npc_knowledge_state"))),
        "scene_continuity_state": deepcopy(_safe_dict(simulation_state.get("scene_continuity_state"))),
        "conversation_thread_state": get_conversation_thread_state(simulation_state),
        "forced_player_invite": deepcopy(forced_invite_payload),
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
    quest_access: Dict[str, Any] = {}
    reputation_consequence: Dict[str, Any] = {}
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

        # Z-AA-AB.1: Compute requested_topic_access from pivot.
        requested_topic_access = requested_topic_access_from_pivot(topic_pivot or {})

        # Z-AA-AB: Evaluate quest conversation access gate before biography response.
        quest_access: Dict[str, Any] = {}
        effective_topic = active_topic
        if settings.get("quest_conversation_access_enabled", True):
            quest_access = evaluate_quest_conversation_access(
                simulation_state,
                npc_id=_safe_str(npc.get("id")),
                topic=active_topic,
                player_input=player_input,
            )
            if quest_access.get("requested"):
                allowed_facts = filter_allowed_topic_facts_for_access(
                    active_topic,
                    access=quest_access,
                )
                effective_topic = {
                    **active_topic,
                    "allowed_facts": allowed_facts,
                    "quest_conversation_access": quest_access,
                }

        biography_response = _biography_grounded_npc_response(
            speaker_id=_safe_str(npc.get("id")),
            listener_id="player",
            simulation_state=simulation_state,
            runtime_state={},
            player_input=player_input,
            topic=effective_topic,
            pivot=topic_pivot,
            response_style=response_style,
            response_intent="answer" if _safe_dict(topic_pivot).get("accepted") else "deflect",
        )
        npc_response_beat = _make_npc_response_beat(
            npc=npc,
            thread=thread,
            topic=effective_topic,
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
        npc_response_beat["dialogue_recall"] = _safe_dict(biography_response.get("dialogue_recall"))
        npc_response_beat["recalled_history_ids"] = _safe_list(biography_response.get("recalled_history_ids"))
        npc_response_beat["recalled_knowledge_ids"] = _safe_list(biography_response.get("recalled_knowledge_ids"))
        npc_response_beat["quest_conversation_access"] = deepcopy(quest_access)

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

        # Z-AA-AB: Apply richer player reputation consequences.
        reputation_consequence: Dict[str, Any] = {}
        if settings.get("player_reputation_consequences_enabled", True):
            reputation_consequence = apply_player_reputation_consequence(
                simulation_state,
                npc_id=responder_id,
                player_input=player_input,
                topic_pivot=topic_pivot or {},
                conversation_result={"reason": "pending_player_response_consumed"},
                tick=tick,
            )
        npc_response_beat["player_reputation_consequence"] = deepcopy(reputation_consequence)
        npc_response_beat["requested_topic_access"] = deepcopy(requested_topic_access)

        # AF-AG-AH: NPC evolution from reputation thresholds.
        npc_evolution_result: Dict[str, Any] = {}
        if settings.get("npc_evolution_enabled", True):
            npc_evolution_result = evolve_npc_from_reputation_thresholds(
                simulation_state,
                npc_id=responder_id,
                tick=tick,
            )
        npc_response_beat["npc_evolution_result"] = deepcopy(npc_evolution_result)
        npc_response_beat["npc_evolution_state"] = deepcopy(_safe_dict(simulation_state.get("npc_evolution_state")))

        # AI: Party eligibility check after evolution.
        party_join_eligibility_result: Dict[str, Any] = {}
        if settings.get("npc_party_eligibility_enabled", True):
            party_join_eligibility_result = evaluate_npc_party_join_eligibility(
                simulation_state,
                npc_id=responder_id,
            )
        npc_response_beat["party_join_eligibility_result"] = deepcopy(party_join_eligibility_result)

        # AJ: Companion join intent from player request.
        companion_join_intent: Dict[str, Any] = {}
        if settings.get("companion_join_intent_enabled", True):
            companion_join_intent = maybe_create_companion_join_intent(
                simulation_state,
                npc_id=responder_id,
                player_input=player_input,
            )
        npc_response_beat["companion_join_intent"] = deepcopy(companion_join_intent)

        # AK: Arc continuity tracking.
        npc_arc_continuity_result: Dict[str, Any] = {}
        if settings.get("npc_arc_continuity_enabled", True):
            npc_arc_continuity_result = update_npc_arc_continuity(
                simulation_state,
                npc_id=responder_id,
                tick=tick,
            )
        npc_response_beat["npc_arc_continuity_result"] = deepcopy(npc_arc_continuity_result)

        # AD: NPC referral suggestion.
        npc_referral: Dict[str, Any] = {}
        if settings.get("npc_referrals_enabled", True):
            npc_referral = suggest_npc_referral(
                simulation_state,
                speaker_id=responder_id,
                topic=effective_topic,
                access=quest_access,
                requested_topic_access=requested_topic_access,
                player_input=player_input,
            )
            if npc_referral.get("suggested") and quest_access.get("access") in {"none", "partial"}:
                npc_response_beat["line"] = f"{npc_response_beat.get('line', '')} {npc_referral.get('line_hint')}".strip()
        npc_response_beat["npc_referral"] = deepcopy(npc_referral)
    else:
        requested_topic_access = requested_topic_access_from_pivot(topic_pivot or {})
        npc_referral = {}

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

    # Y1: update scene continuity after player response NPC beat.
    if settings.get("scene_continuity_enabled", True) and npc_response_beat:
        update_scene_continuity_from_conversation(
            simulation_state,
            location_id=_safe_str(thread.get("location_id")),
            topic_id=_safe_str(active_topic.get("topic_id")),
            topic_type=_safe_str(active_topic.get("topic_type")),
            speaker_id=_safe_str(npc_response_beat.get("speaker_id")),
            listener_id="player",
            tick=tick,
        )

    # W1: knowledge from active_topic for responding NPC.
    if settings.get("npc_knowledge_enabled", True) and npc_response_beat:
        _resp_npc_id = _safe_str(npc_response_beat.get("speaker_id"))
        if _resp_npc_id.startswith("npc:") and topic_is_backed_by_state(active_topic):
            add_npc_knowledge_from_topic(
                simulation_state,
                npc_id=_resp_npc_id,
                topic=active_topic,
                tick=tick,
                confidence=2,
                ttl_ticks=int(settings.get("npc_knowledge_ttl_ticks") or 2000),
            )
        prune_npc_knowledge_state(
            simulation_state,
            current_tick=tick,
            max_known_facts_per_npc=int(settings.get("npc_knowledge_max_facts_per_npc") or 24),
        )

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

    # Build conversation_result snapshot for AC/AE wiring.
    _partial_conversation_result: Dict[str, Any] = {
        "topic_pivot": topic_pivot,
        "quest_conversation_access": deepcopy(quest_access),
        "requested_topic_access": deepcopy(requested_topic_access),
        "player_reputation_consequence": deepcopy(reputation_consequence),
        "npc_referral": deepcopy(npc_referral),
        "npc_response_beat": deepcopy(npc_response_beat),
        "thread": deepcopy(thread),
    }

    # AC: Quest rumor propagation.
    quest_rumor_result: Dict[str, Any] = {}
    if settings.get("quest_rumor_propagation_enabled", True):
        quest_rumor_result = maybe_seed_quest_rumor_from_conversation(
            simulation_state,
            conversation_result=_partial_conversation_result,
            tick=tick,
            ttl_ticks=int(settings.get("quest_rumor_ttl_ticks") or 120),
        )
        prune_quest_rumors(simulation_state, current_tick=tick)

    # AE: Consequence signals.
    _partial_conversation_result["quest_rumor_result"] = deepcopy(quest_rumor_result)
    consequence_signal_result: Dict[str, Any] = {}
    if settings.get("consequence_signals_enabled", True):
        consequence_signal_result = emit_consequence_signals(
            simulation_state,
            conversation_result=_partial_conversation_result,
            tick=tick,
        )

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
        "dialogue_recall": deepcopy(_safe_dict(npc_response_beat.get("dialogue_recall"))),
        "recalled_history_ids": _safe_list(npc_response_beat.get("recalled_history_ids")),
        "recalled_knowledge_ids": _safe_list(npc_response_beat.get("recalled_knowledge_ids")),
        "npc_response_style": response_style,
        "thread": deepcopy(thread),
        "beat": deepcopy(player_response),
        "world_signal": {},
        "world_event": deepcopy(world_event),
        "conversation_social_state": deepcopy(social_state),
        "npc_goal_state": deepcopy(_safe_dict(simulation_state.get("npc_goal_state"))),
        "npc_history_state": deepcopy(_safe_dict(simulation_state.get("npc_history_state"))),
        "npc_reputation_state": deepcopy(_safe_dict(simulation_state.get("npc_reputation_state"))),
        "npc_knowledge_state": deepcopy(_safe_dict(simulation_state.get("npc_knowledge_state"))),
        "npc_evolution_state": deepcopy(_safe_dict(simulation_state.get("npc_evolution_state"))),
        "npc_evolution_result": deepcopy(_safe_dict(npc_response_beat.get("npc_evolution_result"))),
        "party_join_eligibility_result": deepcopy(_safe_dict(npc_response_beat.get("party_join_eligibility_result"))),
        "companion_join_intent": deepcopy(_safe_dict(npc_response_beat.get("companion_join_intent"))),
        "npc_arc_continuity_result": deepcopy(_safe_dict(npc_response_beat.get("npc_arc_continuity_result"))),
        "npc_arc_continuity_state": deepcopy(
            _safe_dict(simulation_state.get("npc_arc_continuity_state"))
        ),
        "scene_continuity_state": deepcopy(_safe_dict(simulation_state.get("scene_continuity_state"))),
        "quest_conversation_access": deepcopy(quest_access),
        "player_reputation_consequence": deepcopy(reputation_consequence),
        "requested_topic_access": deepcopy(requested_topic_access),
        "npc_referral": deepcopy(npc_referral),
        "quest_rumor_result": deepcopy(quest_rumor_result),
        "quest_rumor_state": deepcopy(_safe_dict(simulation_state.get("quest_rumor_state"))),
        "consequence_signal_result": deepcopy(consequence_signal_result),
        "consequence_signal_state": deepcopy(_safe_dict(simulation_state.get("consequence_signal_state"))),
        "conversation_thread_state": get_conversation_thread_state(simulation_state),
        "source": "deterministic_conversation_thread_runtime",
    }
    validation = validate_conversation_effects(result, settings=settings)
    result["conversation_effect_validation"] = validation
    result = strip_forbidden_conversation_effects(result)
    return result


# Alias for test imports
maybe_consume_pending_player_response = handle_pending_player_conversation_response

