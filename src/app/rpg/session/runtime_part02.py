from __future__ import annotations

# Generated split module for app.rpg.session.runtime.
from .runtime_part01 import *

from app.rpg.world.companion_dialogue import (
    build_companion_join_dialogue,
    build_companion_presence_summary,
)
from app.rpg.world.location_registry import ensure_location_state
from app.rpg.world.npc_dialogue_recall import player_input_requests_recall
from app.rpg.world.travel_graph import (
    apply_travel_result_to_state,
    build_travel_state_delta,
    build_travel_world_event,
    list_available_routes,
    resolve_travel_destination,
)
from app.rpg.world.world_event_director import (
    apply_world_behavior_to_events,
    build_world_event_candidates,
    convert_events_to_ambient_updates,
    filter_world_events,
)


def _active_companion_profiles_summary(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    party_state = _safe_dict(_safe_dict(simulation_state.get("player_state")).get("party_state"))
    summaries = {}
    for companion in _safe_list(party_state.get("companions")):
        companion = _safe_dict(companion)
        npc_id = _safe_str(companion.get("npc_id"))
        if not npc_id:
            continue
        profile = load_npc_profile(npc_id)
        if profile:
            draft_summary = profile_draft_summary(npc_id)
            summaries[npc_id] = {
                "npc_id": npc_id,
                "name": _safe_str(profile.get("name")),
                "origin": _safe_str(profile.get("origin")),
                "biography": _safe_dict(profile.get("biography")),
                "personality": _safe_dict(profile.get("personality")),
                "morality": _safe_dict(profile.get("morality")),
                "evolution": _safe_dict(profile.get("evolution")),
                "card_edit_state": _safe_dict(profile.get("card_edit_state")),
                "draft_summary": copy.deepcopy(draft_summary),
                "source": "deterministic_dynamic_npc_profile_store",
            }

    return {
        "profiles": summaries,
        "count": len(summaries),
        "source": "deterministic_dynamic_npc_profile_store",
    }


def _is_companion_actor_id(actor_id: str) -> bool:
    actor_id = _safe_str(actor_id).strip()
    return actor_id.startswith("npc:") or actor_id.startswith("companion:")


def _first_active_companion_actor_id(combat_state: Dict[str, Any]) -> str:
    for actor_id, participant in _safe_dict(_safe_dict(combat_state).get("participants")).items():
        participant = _safe_dict(participant)
        if not _is_companion_actor_id(str(actor_id)):
            continue
        if _safe_int(participant.get("hp"), 0) <= 0:
            continue
        if _safe_str(participant.get("status")).strip().lower() in {"downed", "unconscious", "defeated", "dead", "fled"}:
            continue
        return str(actor_id)
    return ""


def _player_input_requests_reposition(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    return "move closer" in text or "close distance" in text or "reposition" in text or "move to frontline" in text or "fall back" in text


def _requested_reposition_values(player_input: str) -> Dict[str, str]:
    text = _safe_str(player_input).strip().lower()
    if "fall back" in text or "backline" in text or "far" in text:
        return {"zone": "backline", "range_band": "far"}
    return {"zone": "frontline", "range_band": "near"}


def _player_input_requests_general_interaction(player_input: str) -> bool:
    return bool(detect_interaction_intent(player_input))


def _fallback_general_interaction_narration(interaction_result: Dict[str, Any]) -> str:
    interaction_result = _safe_dict(interaction_result)
    target_name = _safe_str(
        interaction_result.get("target_name")
        or interaction_result.get("target_id")
        or "the object"
    ).strip()

    reason = _safe_str(interaction_result.get("reason")).strip()

    if interaction_result.get("resolved") is True:
        if reason == "unlocked":
            return f"Result: You unlock {target_name}."
        if reason == "opened":
            return f"Result: You open {target_name}."
        if reason == "closed":
            return f"Result: You close {target_name}."
        if reason == "items_taken":
            return f"Result: You take the contents from {target_name}."
        return f"Result: {reason}"

    if reason == "missing_required_item":
        required = _safe_str(interaction_result.get("required_item_id") or "the required item")
        return f"Result: You cannot unlock {target_name}; you do not have {required}."
    if reason == "target_locked":
        return f"Result: {target_name} is locked."
    if reason == "container_closed":
        return f"Result: {target_name} is closed."
    if reason == "target_not_found":
        return "Result: You cannot find that object here."
    if reason == "target_not_reachable":
        return f"Result: You cannot reach {target_name}."
    if reason == "already_unlocked":
        return f"Result: {target_name} is already unlocked."
    if reason == "already_open":
        return f"Result: {target_name} is already open."
    if reason == "nothing_to_take":
        return f"Result: There is nothing to take from {target_name}."

    return f"Result: {reason}"


def _player_party_state_from_simulation(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(
        _safe_dict(
            _safe_dict(simulation_state.get("player_state")).get("party_state")
        )
    )


def _sync_session_simulation_state_for_early_return(
    session: Dict[str, Any],
    simulation_state: Dict[str, Any],
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """Persist simulation_state for early-return turn paths.

    Normal apply_turn flows eventually pass through the standard session update
    and save path. The companion-acceptance early return bypasses that path, so
    without this helper Bran is present in Turn 4's returned result but missing
    from Turn 5 after the manual runner reloads the saved session.
    """
    session = _safe_dict(session)
    simulation_state = _safe_dict(simulation_state)

    session["simulation_state"] = simulation_state

    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup_payload["metadata"] = metadata
    session["setup_payload"] = setup_payload

    # Best-effort save. Lazy import avoids module-level circular imports.
    try:
        from app.rpg.session.service import save_session

        save_session(session)
    except Exception as exc:
        session["early_return_persistence_warning"] = {
            "reason": _safe_str(reason),
            "error": f"{type(exc).__name__}: {exc}",
            "source": "deterministic_session_runtime",
        }

    return session


def _companion_runtime_mutated_state(
    *,
    companion_relationship_drift_result: Dict[str, Any] | None = None,
    companion_quest_progress_result: Dict[str, Any] | None = None,
    companion_memory_result: Dict[str, Any] | None = None,
    companion_command_result: Dict[str, Any] | None = None,
) -> bool:
    """Return true when companion systems changed persistent simulation state."""
    drift = _safe_dict(companion_relationship_drift_result)
    quest = _safe_dict(companion_quest_progress_result)
    memory = _safe_dict(companion_memory_result)
    command = _safe_dict(companion_command_result)

    if drift.get("applied") is True:
        return True
    if quest.get("progressed") is True:
        return True
    if _safe_dict(quest.get("seed_result")).get("seeded_any") is True:
        return True
    if memory.get("recorded") is True:
        return True
    if command.get("accepted") is True:
        return True

    return False


def _sync_session_if_companion_runtime_mutated(
    session: Dict[str, Any],
    simulation_state: Dict[str, Any],
    *,
    reason: str,
    companion_relationship_drift_result: Dict[str, Any] | None = None,
    companion_quest_progress_result: Dict[str, Any] | None = None,
    companion_memory_result: Dict[str, Any] | None = None,
    companion_command_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not _companion_runtime_mutated_state(
        companion_relationship_drift_result=companion_relationship_drift_result,
        companion_quest_progress_result=companion_quest_progress_result,
        companion_memory_result=companion_memory_result,
        companion_command_result=companion_command_result,
    ):
        return session

    return _sync_session_simulation_state_for_early_return(
        session,
        simulation_state,
        reason=reason,
    )


def _try_resolve_pending_companion_offer_at_turn_start(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    tick: int,
) -> Dict[str, Any]:
    """Resolve pending companion offer before ordinary action handling.

    This is intentionally above the conversation-thread runtime. A pending
    companion offer is a deterministic yes/no state machine, not an ambient
    conversation trigger. This catches ordinary player input like:

        Yes. Let's go.

    before semantic action handling can classify it as travel/observe.
    """
    simulation_state = _safe_dict(simulation_state)

    companion_debug = get_pending_companion_offer_debug(
        simulation_state,
        player_input=player_input,
    )

    if not companion_debug.get("has_any_pending_offer"):
        return {
            "resolved": False,
            "reason": "no_pending_companion_offer",
            "companion_acceptance_debug": companion_debug,
            "source": "deterministic_session_runtime",
        }

    if not companion_debug.get("accepts") and not companion_debug.get("rejects"):
        return {
            "resolved": False,
            "reason": "player_input_did_not_accept_or_reject_pending_companion_offer",
            "companion_acceptance_debug": companion_debug,
            "source": "deterministic_session_runtime",
        }

    thread_pending = _safe_dict(
        _safe_dict(simulation_state.get("conversation_thread_state")).get(
            "pending_companion_offers"
        )
    )
    if thread_pending:
        hydrate_companion_acceptance_from_pending_offers(
            simulation_state,
            thread_pending,
        )

    acceptance_result = resolve_pending_companion_offer_response(
        simulation_state,
        player_input=player_input,
        tick=tick,
    )

    if not acceptance_result.get("resolved"):
        return {
            "resolved": False,
            "reason": _safe_str(acceptance_result.get("reason")) or "pending_companion_offer_not_resolved",
            "companion_acceptance_result": copy.deepcopy(acceptance_result),
            "companion_acceptance_debug": get_pending_companion_offer_debug(
                simulation_state,
                player_input=player_input,
            ),
            "source": "deterministic_session_runtime",
        }

    npc_id = _safe_str(acceptance_result.get("npc_id"))
    eligibility = _safe_dict(acceptance_result.get("party_join_eligibility_result"))
    npc_name = (
        _safe_str(eligibility.get("name"))
        or npc_id.replace("npc:", "")
        or "Companion"
    )

    companion_dialogue_result: Dict[str, Any] = {}
    if acceptance_result.get("accepted"):
        companion_dialogue_result = build_companion_join_dialogue(
            npc_id=npc_id,
            npc_name=npc_name,
            acceptance_result=acceptance_result,
        )

    npc_response_beat = {}
    if companion_dialogue_result.get("created"):
        npc_response_beat = copy.deepcopy(
            _safe_dict(companion_dialogue_result.get("beat"))
        )

    conversation_result = {
        "triggered": True,
        "reason": "pending_companion_offer_resolved",
        "source_reason": "session_runtime_turn_start",
        "autonomous": False,
        "participation_mode": "companion_acceptance",
        "companion_acceptance_result": copy.deepcopy(acceptance_result),
        "companion_dialogue_result": copy.deepcopy(companion_dialogue_result),
        "companion_presence_summary": copy.deepcopy(
            build_companion_presence_summary(simulation_state)
        ),
        "companion_acceptance_state": copy.deepcopy(
            _safe_dict(simulation_state.get("companion_acceptance_state"))
        ),
        "companion_acceptance_debug": get_pending_companion_offer_debug(
            simulation_state,
            player_input=player_input,
        ),
        "party_state": _player_party_state_from_simulation(simulation_state),
        "npc_response_beat": npc_response_beat,
        "npc_profile_summary": copy.deepcopy(_active_companion_profiles_summary(simulation_state)),
        "character_cards_summary": copy.deepcopy(list_character_cards_for_simulation_state(simulation_state)),
        "conversation_thread_state": copy.deepcopy(
            _safe_dict(simulation_state.get("conversation_thread_state"))
        ),
        "source": "deterministic_session_runtime",
    }

    npc_profile_summary = copy.deepcopy(_active_companion_profiles_summary(simulation_state))
    _character_cards_summary = copy.deepcopy(list_character_cards_for_simulation_state(simulation_state))
    return {
        "resolved": True,
        "accepted": bool(acceptance_result.get("accepted")),
        "rejected": bool(acceptance_result.get("rejected")),
        "reason": "pending_companion_offer_resolved",
        "conversation_result": conversation_result,
        "companion_acceptance_result": copy.deepcopy(acceptance_result),
        "companion_dialogue_result": copy.deepcopy(companion_dialogue_result),
        "party_state": _player_party_state_from_simulation(simulation_state),
        "npc_profile_summary": npc_profile_summary,
        "character_cards_summary": _character_cards_summary,
        "source": "deterministic_session_runtime",
    }


_advance_simulation_for_idle = advance_simulation_for_idle
_build_idle_player_context = build_idle_player_context

_extract_equipment = extract_equipment
_pickup_item_action = pickup_item_action
_drop_item_action = drop_item_action
_equip_item_action = equip_item_action
_unequip_item_action = unequip_item_action

_service_action_from_result = service_action_from_result
_service_semantic_action_from_result = service_semantic_action_from_result
_service_authoritative_result = service_authoritative_result

_SCHEMA_VERSION = 4
_MAX_HISTORY = 64
_MAX_PERF_TRACE_ENTRIES = 20
_DEFAULT_STORY_POLICY = {"save_load_stable": True, "strict_replay": False, "record_replay_artifacts": False}

# Phase F — quiet-window ticks after player action
_DEFAULT_POST_PLAYER_QUIET_TICKS = 1

_ALLOWED_IDLE_SECONDS = (15, 30, 60, 300, 600)
_ALLOWED_REACTION_STYLES = ("minimal", "normal", "lively")
_MAX_RECENT_WORLD_EVENT_ROWS = 64
_MAX_WORLD_RUMORS = 64
_MAX_WORLD_PRESSURE = 64
_MAX_LOCATION_CONDITIONS = 64
_MAX_WORLD_CONSEQUENCES = 128
_WORLD_RUMOR_DECAY_TICKS = 6
_WORLD_PRESSURE_DECAY_TICKS = 4
_LOCATION_CONDITION_DECAY_TICKS = 8
_WORLD_CONSEQUENCE_DECAY_TICKS = 6
_MAX_AMBIENT_UPDATES = 64
_MAX_RECENT_EVENTS = 24
_MAX_RECENT_CHANGES = 24
_MAX_DIRECTOR_LOG = 24
_MAX_RECENT_SCENE_BEATS = 32
_MAX_SEMANTIC_PROPOSALS = 32
_MAX_ACCEPTED_STATE_CHANGE_EVENTS = 64
_MAX_APPLIED_PROPOSAL_IDS = 128
_MAX_LLM_PROPOSAL_CANDIDATES = 8
_MAX_PROMPT_SCENE_BEATS = 4
_SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS = 1
_MAX_RECORDED_SEMANTIC_LLM_PROPOSALS = 8
_MAX_SEMANTIC_ACTION_RECORDS = 64
_MAX_RUNTIME_LLM_RECORDS = 256
_MAX_ACTIVE_INTERACTIONS = 8
_DEFAULT_INTERACTION_DURATION_TICKS = 3
_INTERACTION_STALE_GRACE_TICKS = 1
_MAX_NPC_REACTION_RECORDS = 64
_MAX_INTERACTION_REACTION_STATE = 16












def _ensure_narration_artifact_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state.setdefault("narration_artifacts", [])
    runtime_state.setdefault("narration_artifacts_by_turn", {})
    return runtime_state


def _build_turn_id(runtime_state: Dict[str, Any]) -> str:
    tick = int(_safe_dict(runtime_state).get("tick", 0) or 0)
    return f"turn:{tick}"


def _prune_narration_artifacts(runtime_state: Dict[str, Any], max_items: int = 48) -> Dict[str, Any]:
    runtime_state = _ensure_narration_artifact_state(runtime_state)
    artifacts = _safe_list(runtime_state.get("narration_artifacts"))
    if len(artifacts) > max_items:
        artifacts = artifacts[-max_items:]
    runtime_state["narration_artifacts"] = artifacts

    by_turn = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
    allowed_turn_ids = {
        _safe_str(item.get("turn_id")).strip()
        for item in artifacts
        if isinstance(item, dict)
    }
    runtime_state["narration_artifacts_by_turn"] = {
        k: v for k, v in by_turn.items() if k in allowed_turn_ids
    }
    return runtime_state


def _store_narration_artifact(runtime_state: Dict[str, Any], artifact: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _ensure_narration_artifact_state(runtime_state)
    artifact = _safe_dict(artifact)
    turn_id = _safe_str(artifact.get("turn_id")).strip()
    if not turn_id:
        return runtime_state

    artifacts = _safe_list(runtime_state.get("narration_artifacts"))
    artifacts = [a for a in artifacts if _safe_str(_safe_dict(a).get("turn_id")).strip() != turn_id]
    artifacts.append(artifact)
    runtime_state["narration_artifacts"] = artifacts

    by_turn = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
    by_turn[turn_id] = artifact
    runtime_state["narration_artifacts_by_turn"] = by_turn

    return _prune_narration_artifacts(runtime_state)


def _ensure_narration_job_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state.setdefault("narration_jobs", [])
    runtime_state.setdefault("narration_jobs_by_turn", {})
    return runtime_state


def _build_narration_job_id(turn_id: str) -> str:
    turn_id = _safe_str(turn_id).strip() or "turn:unknown"
    return f"narration:{turn_id}"


def _build_ambient_turn_id(thread_id: str, beat_id: str) -> str:
    thread_id = _safe_str(thread_id).strip() or "conv:unknown"
    beat_id = _safe_str(beat_id).strip() or "beat:unknown"
    return f"ambient:{thread_id}:{beat_id}"


_AMBIENT_NARRATION_THREAD_COOLDOWN_TICKS = 2
_MAX_AMBIENT_NARRATION_ENQUEUES_PER_TICK = 2


def _ensure_ambient_narration_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state.setdefault("ambient_narration_state", {})
    ambient = _safe_dict(runtime_state.get("ambient_narration_state"))
    ambient.setdefault("last_narrated_tick_by_thread", {})
    ambient.setdefault("last_enqueued_turn_ids", [])
    runtime_state["ambient_narration_state"] = ambient
    return runtime_state


def _get_last_ambient_narrated_tick(runtime_state: Dict[str, Any], thread_id: str) -> int:
    runtime_state = _ensure_ambient_narration_state(runtime_state)
    ambient = _safe_dict(runtime_state.get("ambient_narration_state"))
    by_thread = _safe_dict(ambient.get("last_narrated_tick_by_thread"))
    return int(by_thread.get(_safe_str(thread_id).strip(), -999999) or -999999)


def _record_ambient_narration_enqueue(runtime_state: Dict[str, Any], thread_id: str, tick: int, turn_id: str) -> Dict[str, Any]:
    runtime_state = _ensure_ambient_narration_state(runtime_state)
    ambient = _safe_dict(runtime_state.get("ambient_narration_state"))

    by_thread = _safe_dict(ambient.get("last_narrated_tick_by_thread"))
    by_thread[_safe_str(thread_id).strip()] = int(tick or 0)
    ambient["last_narrated_tick_by_thread"] = by_thread

    recent_turn_ids = _safe_list(ambient.get("last_enqueued_turn_ids"))
    recent_turn_ids.append(_safe_str(turn_id).strip())
    ambient["last_enqueued_turn_ids"] = recent_turn_ids[-64:]

    runtime_state["ambient_narration_state"] = ambient
    return runtime_state


def _has_narration_artifact_for_turn(runtime_state: Dict[str, Any], turn_id: str) -> bool:
    runtime_state = _safe_dict(runtime_state)
    by_turn = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
    return bool(_safe_dict(by_turn.get(_safe_str(turn_id).strip())))


def _get_narration_job_for_turn(runtime_state: Dict[str, Any], turn_id: str) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    by_turn = _safe_dict(runtime_state.get("narration_jobs_by_turn"))
    return _safe_dict(by_turn.get(_safe_str(turn_id).strip()))


def _is_narration_job_terminal(job: Dict[str, Any]) -> bool:
    status = _safe_str(_safe_dict(job).get("status")).strip().lower()
    return status in {"completed", "failed", "stale", "cancelled"}


def _is_narration_job_active(job: Dict[str, Any]) -> bool:
    status = _safe_str(_safe_dict(job).get("status")).strip().lower()
    return status in {"queued", "processing"}


def _get_authoritative_narration_job_id(runtime_state: Dict[str, Any], turn_id: str) -> str:
    job = _get_narration_job_for_turn(runtime_state, turn_id)
    return _safe_str(job.get("job_id")).strip()


def _has_blocking_player_turn_narration(runtime_state: Dict[str, Any]) -> bool:
    runtime_state = _safe_dict(runtime_state)
    by_turn = _safe_dict(runtime_state.get("narration_jobs_by_turn"))
    artifacts = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))

    if not by_turn:
        jobs = _safe_list(runtime_state.get("narration_jobs"))
        for job in jobs:
            turn_id = _safe_str(job.get("turn_id")).strip()
            raw_job = job
            job = _safe_dict(raw_job)
            if (_safe_str(job.get("job_kind")).strip() or "player_turn") != "player_turn":
                continue
            status = _safe_str(job.get("status")).strip().lower()
            if status != "queued":
                continue
            artifact = _safe_dict(artifacts.get(turn_id))
            if not artifact:
                return True
    else:
        for turn_id, raw_job in by_turn.items():
            job = _safe_dict(raw_job)
            if (_safe_str(job.get("job_kind")).strip() or "player_turn") != "player_turn":
                continue
            status = _safe_str(job.get("status")).strip().lower()
            if status != "queued":
                continue
            artifact = _safe_dict(artifacts.get(turn_id))
            if not artifact:
                return True
    return False


def _select_latest_ambient_conversation_beats_per_active_thread(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    conversations = _safe_dict(_safe_dict(simulation_state.get("social_state")).get("conversations"))
    beats_by_thread = _safe_dict(conversations.get("beats_by_thread"))
    if not beats_by_thread:
        return []

    active_ids = [
        _safe_str(_safe_dict(c).get("conversation_id")).strip()
        for c in _safe_list(conversations.get("active"))
        if isinstance(c, dict)
    ]

    selected: List[Dict[str, Any]] = []
    for thread_id in active_ids:
        rows = [b for b in _safe_list(beats_by_thread.get(thread_id)) if isinstance(b, dict)]
        if not rows:
            continue
        selected.append(_safe_dict(rows[-1]))

    selected.sort(
        key=lambda b: (
            -int(_safe_dict(b).get("tick", 0) or 0),
            _safe_str(_safe_dict(b).get("thread_id")),
        )
    )
    return selected


def _build_ambient_conversation_narration_request(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    beat: Dict[str, Any],
) -> Dict[str, Any]:
    beat = _safe_dict(beat)
    if not beat:
        return {}

    thread_id = _safe_str(beat.get("thread_id")).strip()
    beat_id = _safe_str(beat.get("beat_id")).strip()
    turn_id = _build_ambient_turn_id(thread_id, beat_id)

    current_scene = _safe_dict(runtime_state.get("current_scene"))
    return {
        "turn_id": turn_id,
        "tick": int(beat.get("tick", runtime_state.get("tick", 0)) or 0),
        "session_id": _safe_str(runtime_state.get("session_id")),
        "scene": current_scene,
        "narration_context": {
            "mode": "ambient_conversation",
            "beat": beat,
            "thread_id": thread_id,
            "speaker_id": _safe_str(beat.get("speaker_id")),
            "addressed_to": _safe_list(beat.get("addressed_to")),
            "summary": _safe_str(beat.get("summary")),
            "stance": _safe_str(beat.get("stance")),
            "mentions": _safe_list(beat.get("mentions")),
            "player_relevant": bool(beat.get("player_relevant")),
        },
        "performance": {
            "enable_live_narration_llm": True,
            "enable_narration_retry": False,
        },
        "job_kind": "ambient_conversation",
        "priority": 20,
    }


def _maybe_enqueue_latest_ambient_conversation_narration(
    session_id: str,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    runtime_state = _ensure_ambient_narration_state(runtime_state)
    settings = _safe_dict(runtime_state.get("conversation_settings"))
    if not bool(settings.get("ambient_conversations_enabled", True)):
        return {"ok": True, "status": "disabled", "enqueued": 0}

    beats = _select_latest_ambient_conversation_beats_per_active_thread(simulation_state, runtime_state)
    if not beats:
        return {"ok": True, "status": "no_beats", "enqueued": 0}

    enqueued = 0
    results = []

    for beat in beats:
        if enqueued >= _MAX_AMBIENT_NARRATION_ENQUEUES_PER_TICK:
            break

        beat = _safe_dict(beat)
        thread_id = _safe_str(beat.get("thread_id")).strip()
        beat_tick = int(beat.get("tick", runtime_state.get("tick", 0)) or 0)

        last_tick = _get_last_ambient_narrated_tick(runtime_state, thread_id)
        if (beat_tick - last_tick) < _AMBIENT_NARRATION_THREAD_COOLDOWN_TICKS:
            continue

        request = _build_ambient_conversation_narration_request(simulation_state, runtime_state, beat)
        turn_id = _safe_str(request.get("turn_id")).strip()
        if not turn_id:
            continue

        if _has_narration_artifact_for_turn(runtime_state, turn_id):
            continue

        runtime_state, job, _ = _enqueue_narration_request(runtime_state, turn_id, beat_tick, request, "ambient_conversation", 20)
        results.append({"ok": bool(job), "job": job})

        if job:
            enqueued += 1
            runtime_state = _record_ambient_narration_enqueue(runtime_state, thread_id, beat_tick, turn_id)

    return {
        "ok": True,
        "status": "processed",
        "enqueued": enqueued,
        "results": results,
        "runtime_state": runtime_state,
    }


def _prune_narration_jobs(runtime_state: Dict[str, Any], max_items: int = 64) -> Dict[str, Any]:
    runtime_state = _ensure_narration_job_state(runtime_state)
    jobs = _safe_list(runtime_state.get("narration_jobs"))
    if len(jobs) > max_items:
        jobs = jobs[-max_items:]
    runtime_state["narration_jobs"] = jobs

    by_turn = _safe_dict(runtime_state.get("narration_jobs_by_turn"))
    allowed_turn_ids = {
        _safe_str(_safe_dict(job).get("turn_id")).strip()
        for job in jobs
        if isinstance(job, dict)
    }
    runtime_state["narration_jobs_by_turn"] = {
        k: v for k, v in by_turn.items() if k in allowed_turn_ids
    }
    return runtime_state


def _upsert_narration_job(runtime_state: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _ensure_narration_job_state(runtime_state)
    job = _safe_dict(job)
    turn_id = _safe_str(job.get("turn_id")).strip()
    if not turn_id:
        return runtime_state

    jobs = _safe_list(runtime_state.get("narration_jobs"))
    jobs = [j for j in jobs if _safe_str(_safe_dict(j).get("turn_id")).strip() != turn_id]
    jobs.append(job)
    runtime_state["narration_jobs"] = jobs

    by_turn = _safe_dict(runtime_state.get("narration_jobs_by_turn"))
    by_turn[turn_id] = job
    runtime_state["narration_jobs_by_turn"] = by_turn

    return _prune_narration_jobs(runtime_state)


def _mark_narration_job_status(
    runtime_state: Dict[str, Any],
    turn_id: str,
    *,
    status: str,
    worker_token: str = "",
    error: str = "",
) -> Dict[str, Any]:
    runtime_state = _ensure_narration_job_state(runtime_state)
    turn_id = _safe_str(turn_id).strip()
    if not turn_id:
        return runtime_state

    by_turn = _safe_dict(runtime_state.get("narration_jobs_by_turn"))
    job = _safe_dict(by_turn.get(turn_id))
    if not job:
        job = {
            "job_id": _build_narration_job_id(turn_id),
            "turn_id": turn_id,
            "tick": 0,
            "status": "queued",
            "created_at": _utc_now_iso(),
            "started_at": None,
            "completed_at": None,
            "error": "",
            "attempts": 0,
            "max_attempts": 3,
        }

    job["status"] = status
    if status == "processing" and not job.get("started_at"):
        job["started_at"] = _utc_now_iso()
    if status in {"completed", "failed", "stale"}:
        job["completed_at"] = _utc_now_iso()
    if error:
        job["error"] = _safe_str(error)
    if worker_token:
        job["worker_token"] = _safe_str(worker_token)

    return _upsert_narration_job(runtime_state, job)

__all__ = [name for name in globals() if not name.startswith("__")]
