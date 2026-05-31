from __future__ import annotations

# Generated split module for app.rpg.session.runtime.
from .runtime_part01 import *
from .runtime_part02 import *
from .runtime_part03 import *
from .runtime_part04 import *
from .runtime_part05 import *
from .runtime_part06 import *
from .runtime_part07 import *
from .runtime_part08 import *
from .runtime_part09 import *
from .runtime_part10 import *
from .runtime_part11 import *
from .runtime_part12 import *
from .runtime_part13 import *
from .runtime_part14 import *
from .runtime_part15 import *

def _apply_turn_authoritative(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    record_turn_perf_trace_stack(
        "authoritative_enter",
        function="_apply_turn_authoritative",
    )
    _t0 = _time.monotonic()
    session = load_runtime_session(session_id)
    if session is None:
        record_turn_perf_trace(
            "authoritative_before_return",
            reason="session_not_found",
            return_keys=[],
            ok=False,
        )
        return {"ok": False, "error": "session_not_found"}
    # IMPORTANT: keep the old apply_turn authoritative pipeline intact.
    # This function should be the previous apply_turn() minus the live
    # narration-generation block, not a redesign of the turn engine.
    session = _copy_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _copy_dict(session.get("runtime_state"))
    setup = apply_adventure_defaults(_copy_dict(session.get("setup_payload")))
    simulation_state = _ensure_simulation_state(_safe_dict(session.get("simulation_state")))
    player_actor_id = "player"
    current_tick = _safe_int(runtime_state.get("tick"), 0)
    _t_load = _time.monotonic()
    if performance_override:
        existing_perf = runtime_state.get("performance") or {}
        if isinstance(existing_perf, dict):
            runtime_state["performance"] = {**existing_perf, **performance_override}
        else:
            runtime_state["performance"] = dict(performance_override)
    perf = _normalize_performance_settings(runtime_state)
    # Playable/deferred mode: keep the authoritative turn synchronous,
    # deterministic, and fast. LLM advisory is useful for richer interpretation,
    # but it is not allowed to block the turn path when narration/LLM work is
    # being deferred. The deterministic semantic action fallback still runs
    # below via _build_fast_semantic_action_record(...).
    defer_runtime_llm_work = bool(
        suppress_provider_runtime_narration()
        or runtime_state.get("autoplay_deferred_narration")
        or runtime_state.get("deferred_runtime_narration")
        or runtime_state.get("narration_mode") == "deferred"
    )
    if defer_runtime_llm_work:
        perf["enable_action_advisory"] = False
        perf["enable_semantic_action_advisory"] = False
        runtime_state["deferred_runtime_advisory_suppressed"] = True
    runtime_state["performance"] = perf
    story_policy = _normalize_story_policy(runtime_state)
    runtime_state["story_policy"] = story_policy
    player_input = _safe_str(player_input).strip()
    manual_encounter_preset = _manual_encounter_preset_from_input(player_input)
    _maybe_start_manual_encounter_result = _maybe_start_manual_encounter(
        player_input=player_input,
        simulation_state=simulation_state,
        current_tick=current_tick,
        manual_encounter_preset=manual_encounter_preset,
    )
    if _maybe_start_manual_encounter_result is not None:
        return _maybe_start_manual_encounter_result
    action = _normalize_structured_action(action, player_input)
    action = _coerce_action_target(simulation_state, action, player_input)
    action = _coerce_action_target_to_active_combat_participant(
        runtime_state,
        action,
        player_input,
    )
    if not action:
        candidates = derive_action_candidates(
            simulation_state,
            player_input,
            runtime_state=runtime_state,
        )
        action = select_primary_action(simulation_state, candidates)
    action = _safe_dict(action)
    action_type = _safe_str(action.get("action_type")).strip()
    if not player_input:
        player_input = _structured_action_prompt(action)
    player_input = player_input or action_type.replace("_", " ").strip() or "Wait"
    service_first_result = resolve_service_turn(
        player_input=player_input,
        action=action,
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )
    if service_first_result.get("matched"):
        action = service_action_from_result(player_input, action, service_first_result)
        action_type = _safe_str(action.get("action_type")).strip()
    # Lazy LLM gateway: build at most once per authoritative turn.
    _llm_gw_holder: List[Any] = []
    def _get_llm_gateway():
        if not _llm_gw_holder:
            _llm_gw_holder.append(build_app_llm_gateway())
        return _llm_gw_holder[0]
    advisory = {}
    semantic_advisory = {}
    semantic_action_record = {}
    runtime_state.setdefault("conversation_settings", {})
    runtime_state.setdefault("offscreen_conversation_summaries", [])
    runtime_state.setdefault("last_player_action", {})
    runtime_state.setdefault("last_conversation_intervention", {})
    record_replay_artifacts = _story_policy_record_replay_artifacts(runtime_state)
    if record_replay_artifacts:
        runtime_state.setdefault("llm_records", [])
        runtime_state["llm_records_index"] = _safe_dict(runtime_state.get("llm_records_index"))
        runtime_state.setdefault("turn_execution_index", {})
    mode = _safe_str(runtime_state.get("mode")).strip().lower() or "live"
    current_tick = _safe_int(runtime_state.get("tick"), 0)
    # Stable turn identifiers for every authoritative path.
    #
    # J19-J21 added early/post-authoritative combat utility paths for:
    # - defend
    # - use_item
    # - flee
    #
    # Those branches can return before the older lower-scope turn_id/final_tick
    # locals are initialized. Define them here so all branches can safely use
    # the same deterministic turn metadata.
    turn_id = _build_turn_id(runtime_state)
    final_tick = current_tick
    ambient_tick_command = is_ambient_tick_command(player_input)
    ambient_tick_result = {}
    recall_request_conversation_result = {}
    if player_input_requests_recall(player_input):
        recall_request_conversation_result = advance_conversation_threads_for_turn(
            player_input=player_input,
            simulation_state=simulation_state,
            resolved_result={
                "action_type": "player_conversation_recall",
                "semantic_action_type": "player_conversation_recall",
                "semantic_family": "conversation",
            },
            tick=current_tick,
            runtime_state=runtime_state,
        )
    turn_exec_key = f"turn:{current_tick}"
    turn_execution_policy = {
        "enable_action_advisory": perf["enable_action_advisory"],
        "enable_semantic_action_advisory": perf["enable_semantic_action_advisory"],
        "enable_live_narration_llm": perf["enable_live_narration_llm"],
        "enable_narration_retry": perf["enable_narration_retry"],
        "fast_turn_mode": perf["fast_turn_mode"],
        "save_load_stable": story_policy["save_load_stable"],
        "strict_replay": story_policy["strict_replay"],
    }
    if mode == "live" and record_replay_artifacts:
        runtime_state["turn_execution_index"][turn_exec_key] = turn_execution_policy
    if mode == "replay" and not record_replay_artifacts:
        raise RuntimeError("replay_disabled_for_save_load_stable_sessions")
    runtime_state["last_player_action"] = {
        "action_id": f"player_action:{current_tick + 1}",
        "action_type": action_type,
        "target_id": _safe_str(action.get("target_id")) if isinstance(action, dict) else "",
        "npc_id": _safe_str(action.get("npc_id")) if isinstance(action, dict) else "",
        "item_id": _safe_str(action.get("item_id")) if isinstance(action, dict) else "",
    }
    runtime_state, _stage_started, advisory, semantic_advisory = _apply_advisory_phase(
        player_input=player_input,
        action=action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        current_tick=current_tick,
        _get_llm_gateway=_get_llm_gateway,
        _stage_started=_stage_started,
        advisory=advisory,
        key=key,
        mode=mode,
        perf=perf,
        record=record,
        record_replay_artifacts=record_replay_artifacts,
        recorded_policy=recorded_policy,
        semantic_advisory=semantic_advisory,
        semantic_key=semantic_key,
        semantic_record=semantic_record,
        semantic_record_capture=semantic_record_capture,
        turn_exec_index=turn_exec_index,
        turn_exec_key=turn_exec_key,
    )
    _t_advisory = _time.monotonic()
    if advisory:
        action = merge_action_advisory(action, advisory)
        action_type = _safe_str(action.get("action_type")).strip()
    # Service intent is deterministic and wins over generic/LLM-advised action
    # labels such as use_item, persuade, deceive, or observe.
    service_after_advisory = resolve_service_turn(
        player_input=player_input,
        action=action,
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )
    if service_after_advisory.get("matched"):
        action = service_action_from_result(player_input, action, service_after_advisory)
        action_type = _safe_str(action.get("action_type")).strip()
    semantic_compiled_key = f"semantic_action_compiled:{current_tick}"
    runtime_state, semantic_action_record = _force_combat_utility_action_type(
        player_input=player_input,
        action=action,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        current_tick=current_tick,
        semantic_action_record=semantic_action_record,
        _stage_started=_stage_started,
        mode=mode,
        perf=perf,
        record_replay_artifacts=record_replay_artifacts,
        semantic_advisory=semantic_advisory,
        semantic_compiled_capture=semantic_compiled_capture,
        semantic_compiled_key=semantic_compiled_key,
        semantic_compiled_record=semantic_compiled_record,
    )
    _t_semantic = _time.monotonic()
    action_metadata = _safe_dict(action.get("metadata"))
    action_metadata["semantic_action"] = semantic_action_record
    action["metadata"] = action_metadata
    action = _force_active_combat_utility_action(
        runtime_state,
        action,
        semantic_action_record,
        player_input,
    )
    action_type = _safe_str(action.get("action_type")).strip()
    service_after_semantic = resolve_service_turn(
        player_input=player_input,
        action=action,
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )
    if service_after_semantic.get("matched"):
        action = service_action_from_result(player_input, action, service_after_semantic)
        action_type = _safe_str(action.get("action_type")).strip()
        semantic_action_record = service_semantic_action_from_result(
            player_input,
            service_after_semantic,
            tick=_safe_int(current_tick, 0),
            existing=semantic_action_record,
        )
        action_metadata = _safe_dict(action.get("metadata"))
        action_metadata["semantic_action"] = semantic_action_record
        action["metadata"] = action_metadata
    runtime_state["last_player_action"] = _build_last_player_action_record(
        tick=current_tick,
        player_input=player_input,
        action=action,
        semantic_action_record=semantic_action_record,
    )
    action = _force_active_combat_utility_action(
        runtime_state,
        action,
        semantic_action_record,
        player_input,
    )
    action_type = _safe_str(action.get("action_type")).strip()
    active_combat_utility_kind = _active_combat_utility_kind(
        runtime_state,
        semantic_action_record,
        player_input,
    )
    if active_combat_utility_kind:
        return _resolve_active_combat_utility_turn(
            runtime_state=runtime_state,
            semantic_action_record=semantic_action_record,
            player_input=player_input,
            simulation_state=simulation_state,
            action=action,
            player_actor_id=player_actor_id,
            active_combat_utility_kind=active_combat_utility_kind,
            current_tick=current_tick,
            turn_id=turn_id,
        )
    ability_id = _ability_id_from_player_input(player_input)
    _maybe_resolve_combat_ability_turn_result = _maybe_resolve_combat_ability_turn(
        player_input=player_input,
        simulation_state=simulation_state,
        current_tick=current_tick,
        ability_id=ability_id,
    )
    if _maybe_resolve_combat_ability_turn_result is not None:
        return _maybe_resolve_combat_ability_turn_result
    companion_command = parse_companion_command(player_input)
    active_combat_state = _active_combat_state_from_runtime_or_simulation(
        runtime_state,
        simulation_state,
    )
    _maybe_resolve_companion_combat_command_turn_result = _maybe_resolve_companion_combat_command_turn(
        player_input=player_input,
        current_tick=current_tick,
        active_combat_state=active_combat_state,
        companion_command=companion_command,
    )
    if _maybe_resolve_companion_combat_command_turn_result is not None:
        return _maybe_resolve_companion_combat_command_turn_result
    active_combat_state = _active_combat_state_from_runtime_or_simulation(
        runtime_state,
        simulation_state,
    )
    _maybe_resolve_reposition_turn_result = _maybe_resolve_reposition_turn(
        player_input=player_input,
        simulation_state=simulation_state,
        current_tick=current_tick,
        active_combat_state=active_combat_state,
    )
    if _maybe_resolve_reposition_turn_result is not None:
        return _maybe_resolve_reposition_turn_result
    before_state = copy.deepcopy(simulation_state)
    combat_state = _safe_dict(_get_combat_state(runtime_state))
    if combat_state.get("active") and _safe_str(combat_state.get("source")).strip() == "deterministic_encounter_builder":
        repaired_combat_state = _repair_generated_encounter_player_turn(combat_state)
        if repaired_combat_state != combat_state:
            runtime_state = _set_combat_state(runtime_state, repaired_combat_state)
            simulation_state["combat_state"] = repaired_combat_state
            combat_state = repaired_combat_state
    authoritative = _apply_authoritative_action(simulation_state, runtime_state, action)
    authoritative_simulation_state = _safe_dict(authoritative.get("simulation_state"))
    post_authoritative_semantic_action_record = _extract_semantic_action_record_for_turn(
        semantic_action_record,
        authoritative,
    )
    post_authoritative_utility_kind = _combat_utility_kind_from_semantic_or_text(
        post_authoritative_semantic_action_record,
        player_input,
    )
    post_authoritative_combat_state = _find_active_combat_state_deep(authoritative)
    # J19-J21:
    # Active-combat utility commands may not see active combat in runtime_state
    # before _apply_authoritative_action(...). In that case, the generic
    # interaction runtime can return unsupported_interaction_kind while carrying
    # the active combat_state inside the authoritative payload. Rescue those
    # commands here and resolve them as combat actions before the unsupported
    # interaction becomes the final visible result.
    if post_authoritative_utility_kind and post_authoritative_combat_state.get("active"):
        return _resolve_post_authoritative_combat_utility_turn(
            runtime_state=runtime_state,
            post_authoritative_utility_kind=post_authoritative_utility_kind,
            post_authoritative_combat_state=post_authoritative_combat_state,
            post_authoritative_semantic_action_record=post_authoritative_semantic_action_record,
            authoritative_simulation_state=authoritative_simulation_state,
            simulation_state=simulation_state,
            action=action,
            player_input=player_input,
            player_actor_id=player_actor_id,
            current_tick=current_tick,
            session_id=session_id,
        )
    if authoritative_simulation_state:
        simulation_state = authoritative_simulation_state
    after_action_state = _ensure_simulation_state(_safe_dict(authoritative.get("simulation_state")))
    resolved_result = _safe_dict(authoritative.get("result"))
    resolved_result.setdefault("action_type", action_type)
    service_resolution = mirror_service_result(
        resolved_result,
        action,
        action_type=action_type,
        semantic_action_record=semantic_action_record,
    )
    resolved_result = _safe_dict(service_resolution.get("resolved_result"))
    action = _safe_dict(service_resolution.get("action"))
    combat_state = _extract_active_combat_state_for_turn(runtime_state, resolved_result)
    if combat_state.get("active"):
        runtime_state = _set_combat_state(runtime_state, combat_state)
    combat_result: Dict[str, Any] = {}
    npc_combat_result: Dict[str, Any] = {}
    normalized_action_type = _safe_str(_safe_dict(action).get("action_type")).strip().lower()
    target_id = _safe_str(_safe_dict(action).get("target_id")).strip()
    # J19-J21:
    # Combat utility actions must be recognized directly from player text when
    # combat is already active. Do not require the general semantic-action layer
    # to classify them first, because otherwise clear commands like "I flee."
    # can fall through to no_supported_semantic_action_detected before the
    # combat runtime sees them.
    if combat_state.get("active"):
        action_obj = _safe_dict(action)
        if not normalized_action_type:
            if _action_requests_combat_defend(action_obj, player_input):
                action_obj = dict(action_obj)
                action_obj["action_type"] = "defend"
                action = action_obj
                normalized_action_type = "defend"
            elif _action_requests_combat_flee(action_obj, player_input):
                action_obj = dict(action_obj)
                action_obj["action_type"] = "flee"
                action = action_obj
                normalized_action_type = "flee"
            elif _action_requests_combat_use_item(action_obj, player_input):
                action_obj = dict(action_obj)
                action_obj["action_type"] = "use_item"
                action = action_obj
                normalized_action_type = "use_item"
    is_combat_attack = _action_requests_hostile_combat(action, player_input)
    is_combat_defend = _action_requests_combat_defend(action, player_input)
    is_combat_flee = _action_requests_combat_flee(action, player_input)
    is_combat_use_item = _action_requests_combat_use_item(action, player_input)
    is_combat_action = is_combat_attack or (
        combat_state.get("active") and (is_combat_defend or is_combat_flee or is_combat_use_item)
    )
    if is_combat_attack and target_id:
        target_actor = _lookup_actor_by_id(after_action_state, target_id)
        if not target_actor:
            is_combat_action = False
    _maybe_resolve_stabilize_turn_result = _maybe_resolve_stabilize_turn(
        player_input=player_input,
        simulation_state=simulation_state,
        current_tick=current_tick,
    )
    if _maybe_resolve_stabilize_turn_result is not None:
        return _maybe_resolve_stabilize_turn_result
    _maybe_resolve_revive_turn_result = _maybe_resolve_revive_turn(
        player_input=player_input,
        simulation_state=simulation_state,
        current_tick=current_tick,
    )
    if _maybe_resolve_revive_turn_result is not None:
        return _maybe_resolve_revive_turn_result
    _maybe_gate_non_player_combat_turn_result = _maybe_gate_non_player_combat_turn(
        player_input=player_input,
        after_action_state=after_action_state,
        runtime_state=runtime_state,
        current_tick=current_tick,
        turn_id=turn_id,
        player_actor_id=player_actor_id,
        combat_state=combat_state,
        normalized_action_type=normalized_action_type,
    )
    if _maybe_gate_non_player_combat_turn_result is not None:
        return _maybe_gate_non_player_combat_turn_result
    _apply_active_non_attack_combat_action_context = _apply_active_non_attack_combat_action(
        player_input=player_input,
        action=action,
        after_action_state=after_action_state,
        runtime_state=runtime_state,
        current_tick=current_tick,
        turn_id=turn_id,
        final_tick=final_tick,
        player_actor_id=player_actor_id,
        resolved_result=resolved_result,
        authoritative=authoritative,
        combat_state=combat_state,
        combat_result=combat_result,
        npc_combat_result=npc_combat_result,
        is_combat_action=is_combat_action,
        is_combat_attack=is_combat_attack,
        is_combat_defend=is_combat_defend,
        is_combat_flee=is_combat_flee,
        is_combat_use_item=is_combat_use_item,
        normalized_action_type=normalized_action_type,
    )
    if _apply_active_non_attack_combat_action_context.get("return_result") is not None:
        return _safe_dict(_apply_active_non_attack_combat_action_context.get("return_result"))
    after_action_state = _apply_active_non_attack_combat_action_context["after_action_state"]
    runtime_state = _apply_active_non_attack_combat_action_context["runtime_state"]
    resolved_result = _apply_active_non_attack_combat_action_context["resolved_result"]
    combat_state = _apply_active_non_attack_combat_action_context["combat_state"]
    combat_result = _apply_active_non_attack_combat_action_context["combat_result"]
    npc_combat_result = _apply_active_non_attack_combat_action_context["npc_combat_result"]
    _apply_attack_combat_action_context = _apply_attack_combat_action(
        player_input=player_input,
        after_action_state=after_action_state,
        runtime_state=runtime_state,
        current_tick=current_tick,
        turn_id=turn_id,
        final_tick=final_tick,
        player_actor_id=player_actor_id,
        resolved_result=resolved_result,
        authoritative=authoritative,
        combat_state=combat_state,
        combat_result=combat_result,
        npc_combat_result=npc_combat_result,
        is_combat_attack=is_combat_attack,
        normalized_action_type=normalized_action_type,
        target_id=target_id,
    )
    if _apply_attack_combat_action_context.get("return_result") is not None:
        return _safe_dict(_apply_attack_combat_action_context.get("return_result"))
    after_action_state = _apply_attack_combat_action_context["after_action_state"]
    runtime_state = _apply_attack_combat_action_context["runtime_state"]
    resolved_result = _apply_attack_combat_action_context["resolved_result"]
    combat_state = _apply_attack_combat_action_context["combat_state"]
    combat_result = _apply_attack_combat_action_context["combat_result"]
    npc_combat_result = _apply_attack_combat_action_context["npc_combat_result"]
    after_action_state = _ensure_simulation_state(_safe_dict(authoritative.get("simulation_state")))
    resolved_result = _safe_dict(authoritative.get("result"))
    resolved_result.setdefault("action_type", action_type)
    pending_conversation_reply = _has_pending_conversation_response(after_action_state)
    service_resolution = mirror_service_result(
        resolved_result,
        action,
        action_type=action_type,
        semantic_action_record=semantic_action_record,
    )
    resolved_result = _safe_dict(service_resolution.get("resolved_result"))
    action = _safe_dict(service_resolution.get("action"))
    if ambient_tick_command:
        ambient_conversation_tick = _safe_int(
            after_action_state.get("tick")
            or after_action_state.get("current_tick")
            or runtime_state.get("tick"),
            current_tick,
        )
        ambient_tick_result = advance_autonomous_ambient_tick(
            player_input=player_input,
            simulation_state=after_action_state,
            runtime_state=runtime_state,
            tick=ambient_conversation_tick,
        )
        authoritative["simulation_state"] = after_action_state
    conversation_result = _apply_ambient_conversation_result(
        after_action_state=after_action_state,
        resolved_result=resolved_result,
        authoritative=authoritative,
        ambient_tick_result=ambient_tick_result,
        conversation_result=conversation_result,
    )
    after_action_state, resolved_result, authoritative = _apply_deterministic_travel_resolution(
        ambient_tick_result=ambient_tick_result,
        resolved_result=resolved_result,
        authoritative=authoritative,
        player_input=player_input,
        after_action_state=after_action_state,
    )
    social_living_world_effects = apply_general_social_effects(
        after_action_state,
        resolved_result,
        tick=current_tick,
    )
    if social_living_world_effects:
        resolved_result["social_living_world_effects"] = social_living_world_effects
        resolved_result["memory_entry"] = (
            resolved_result.get("memory_entry")
            or social_living_world_effects.get("memory_entry")
            or {}
        )
        resolved_result["relationship_state"] = _safe_dict(after_action_state.get("relationship_state"))
        resolved_result["npc_emotion_state"] = _safe_dict(after_action_state.get("npc_emotion_state"))
        resolved_result["memory_state"] = _safe_dict(after_action_state.get("memory_state"))
        authoritative["social_living_world_effects"] = social_living_world_effects
        authoritative["relationship_state"] = _safe_dict(after_action_state.get("relationship_state"))
        authoritative["npc_emotion_state"] = _safe_dict(after_action_state.get("npc_emotion_state"))
        authoritative["memory_state"] = _safe_dict(after_action_state.get("memory_state"))
        authoritative["result"] = resolved_result
    # Always refresh location debug after the turn. This keeps service turns,
    # social turns, and travel turns consistent for transcript/UI inspection.
    ensure_location_state(after_action_state)
    resolved_result["location_state"] = _safe_dict(after_action_state.get("location_state"))
    resolved_result["current_location_id"] = _safe_str(
        _safe_dict(after_action_state.get("location_state")).get("current_location_id")
        or after_action_state.get("location_id")
        or after_action_state.get("current_location_id")
    )
    authoritative["location_state"] = _safe_dict(after_action_state.get("location_state"))
    authoritative["current_location_id"] = resolved_result["current_location_id"]
    authoritative["world_event_state"] = _safe_dict(after_action_state.get("world_event_state"))
    authoritative["simulation_state"] = after_action_state
    if pending_conversation_reply:
        resolved_result["action_type"] = "player_conversation_reply"
        resolved_result["semantic_action_type"] = "player_conversation_reply"
        resolved_result["semantic_family"] = "conversation"
        resolved_result["activity_label"] = "player_conversation_reply"
        service_result = {
            "matched": False,
            "kind": "not_service",
            "status": "not_service",
            "reason": "pending_conversation_response_takes_precedence",
        }
        resolved_result["service_result"] = service_result
        authoritative["action_type"] = "player_conversation_reply"
        authoritative["semantic_action_type"] = "player_conversation_reply"
        authoritative["semantic_family"] = "conversation"
        authoritative["activity_label"] = "player_conversation_reply"
        authoritative["service_result"] = service_result
    service_result = _safe_dict(resolved_result.get("service_result"))
    if ambient_tick_result:
        service_result = {
            "matched": False,
            "kind": "not_service",
            "status": "not_service",
            "reason": "ambient_tick",
        }
        resolved_result["service_result"] = service_result
    if is_ambient_wait_or_listen_intent(player_input) and not service_result.get("matched"):
        resolved_result["action_type"] = "ambient_wait"
        resolved_result["semantic_action_type"] = "ambient_wait"
        resolved_result["semantic_family"] = "ambient"
        resolved_result["activity_label"] = "wait_and_listen"
        authoritative["action_type"] = "ambient_wait"
        authoritative["semantic_action_type"] = "ambient_wait"
        authoritative["semantic_family"] = "ambient"
        authoritative["activity_label"] = "wait_and_listen"
    conversation_result = _safe_dict(
        recall_request_conversation_result
        or resolved_result.get("conversation_result")
    )
    if not conversation_result and not ambient_tick_result:
        conversation_result = advance_conversation_threads_for_turn(
            player_input=player_input,
            simulation_state=after_action_state,
            resolved_result=resolved_result,
            tick=_safe_int(
                after_action_state.get("tick") or after_action_state.get("current_tick"),
                current_tick,
            ),
            runtime_state=runtime_state,
        )
    if conversation_result:
        resolved_result["conversation_result"] = conversation_result
        resolved_result["conversation_thread_state"] = _safe_dict(
            conversation_result.get("conversation_thread_state")
            or after_action_state.get("conversation_thread_state")
        )
        resolved_result["world_event_state"] = _safe_dict(after_action_state.get("world_event_state"))
        authoritative["conversation_result"] = conversation_result
        authoritative["conversation_thread_state"] = _safe_dict(
            after_action_state.get("conversation_thread_state")
        )
        authoritative["world_event_state"] = _safe_dict(after_action_state.get("world_event_state"))
        authoritative["simulation_state"] = after_action_state
    _t_authoritative = _time.monotonic()
    runtime_settings_for_contract = _safe_dict(
        runtime_state.get("runtime_settings") or runtime_state.get("settings")
    )
    turn_contract = {}
    after_action_state, resolved_result, turn_contract = _build_and_apply_turn_contract_phase(
        player_input=player_input,
        action=action,
        simulation_state=simulation_state,
        before_state=before_state,
        after_action_state=after_action_state,
        runtime_state=runtime_state,
        resolved_result=resolved_result,
        semantic_action_record=semantic_action_record,
        before_state_for_contract=before_state_for_contract,
        contract_resolved=contract_resolved,
        resolved_for_contract=resolved_for_contract,
        resolved_from_contract=resolved_from_contract,
        runtime_settings_for_contract=runtime_settings_for_contract,
        turn_contract=turn_contract,
    )
    turn_contract = _build_fallback_turn_contract_phase(
        player_input=player_input,
        action=action,
        simulation_state=simulation_state,
        before_state=before_state,
        runtime_state=runtime_state,
        resolved_result=resolved_result,
        semantic_action_record=semantic_action_record,
        ambient_tick_result=ambient_tick_result,
        service_result=service_result,
        turn_contract=turn_contract,
    )
    progression = _award_progression(after_action_state, resolved_result)
    after_progression_state = _ensure_simulation_state(_safe_dict(progression.get("simulation_state")))
    metadata = _safe_dict(setup.get("metadata"))
    metadata["simulation_state"] = after_progression_state
    setup["metadata"] = metadata
    step_result = step_simulation_state(setup)
    next_setup = _safe_dict(step_result.get("next_setup")) or setup
    # step_simulation_state rebuilds a world-sim slice from scratch. Merge it
    # back over the authoritative per-turn state so player/service/social roots
    # persist across turns.
    after_state = _merge_stepped_simulation_state(
        after_progression_state,
        _safe_dict(step_result.get("after_state")),
    )
    _t_step = _time.monotonic()
    _maybe_resolve_general_interaction_turn_result = _maybe_resolve_general_interaction_turn(
        player_input=player_input,
        runtime_state=runtime_state,
        current_tick=current_tick,
    )
    if _maybe_resolve_general_interaction_turn_result is not None:
        return _maybe_resolve_general_interaction_turn_result
    _log_interaction_trace(
        "apply_turn_before_semantic_apply",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    after_state, runtime_state = _apply_semantic_action_to_runtime(
        simulation_state=after_state,
        runtime_state=runtime_state,
        record=semantic_action_record,
    )
    _log_interaction_trace(
        "apply_turn_after_semantic_apply",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    after_state, runtime_state = _persist_player_interaction_state_after_turn(
        after_state,
        runtime_state,
        player_input,
        semantic_action_record,
        current_tick,
    )
    after_state = _refresh_active_interactions_for_tick(
        after_state,
        _safe_int(after_state.get("tick"), current_tick),
    )
    _log_interaction_trace(
        "apply_turn_after_interaction_creation",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    after_state = _resolve_until_next_command_interactions(
        after_state,
        runtime_state,
        semantic_action_record,
        current_tick,
    )
    after_state = _expire_stale_active_interactions(after_state, _safe_int(after_state.get("tick"), current_tick))
    runtime_state = _clean_resolved_interaction_world_event_rows(after_state, runtime_state)
    runtime_state = normalize_conversation_threads(runtime_state)
    runtime_state = expire_conversation_threads(
        runtime_state,
        current_tick=_safe_int(after_state.get("tick"), current_tick),
    )
    scenes = generate_scenes_from_simulation(after_state)
    current_scene = _safe_dict(scenes[0]) if scenes else _fallback_scene(after_state, player_input)
    current_location_id = _get_player_location_id(after_state, runtime_state)
    current_scene["items"] = list_scene_items(after_state, current_location_id)
    current_scene["nearby_npcs"] = build_nearby_npc_cards(after_state, current_scene)
    narration_context = build_turn_narration_context(
        after_state=after_state,
        player_input=player_input,
        resolved_result=resolved_result,
        turn_contract=turn_contract,
        progression=progression,
        runtime_state=runtime_state,
        current_tick=current_tick,
        combat_result=combat_result,
        npc_combat_result=npc_combat_result,
        combat_state=combat_state,
    )
    # J19-J21 final rescue:
    # If the generic interaction runtime produced unsupported_interaction_kind
    # but the completed resolved_result contains an active combat_state plus a
    # combat utility semantic action, resolve it here before narration sees the
    # unsupported fallback.
    # Build a rescue candidate from both resolved_result and sibling turn fields.
    # In the current pipeline, unsupported_interaction_kind can leave
    # resolved_result as {}, while combat_state and semantic_action_v2 live
    # beside it in the assembled turn payload.
    last_chance_candidate = dict(_safe_dict(resolved_result))
    if not _safe_dict(last_chance_candidate.get("combat_state")).get("active"):
        last_chance_candidate["combat_state"] = _safe_dict(combat_state)
    if not _safe_dict(last_chance_candidate.get("combat_state")).get("active"):
        last_chance_candidate["combat_state"] = _find_active_combat_state_deep(authoritative)
    if not _safe_dict(last_chance_candidate.get("semantic_action_v2")):
        last_chance_candidate["semantic_action_v2"] = _extract_semantic_action_record_for_turn(
            semantic_action_record,
            authoritative,
        )
    if not _safe_str(last_chance_candidate.get("visible_interaction_reason")).strip():
        last_chance_candidate["visible_interaction_reason"] = _safe_str(
            resolved_result.get("visible_interaction_reason")
            or _safe_dict(resolved_result.get("interaction_result")).get("reason")
            or _safe_dict(_safe_dict(authoritative.get("result")).get("interaction_result")).get("reason")
            or _safe_dict(_safe_dict(_safe_dict(authoritative.get("result")).get("general_interaction_result")).get("interaction_result")).get("reason")
        ).strip()
    if not _safe_dict(last_chance_candidate.get("interaction_result")):
        last_chance_candidate["interaction_result"] = _safe_dict(
            _safe_dict(authoritative.get("result")).get("interaction_result")
        )
    if not _safe_dict(last_chance_candidate.get("general_interaction_result")):
        last_chance_candidate["general_interaction_result"] = _safe_dict(
            _safe_dict(authoritative.get("result")).get("general_interaction_result")
        )
    last_chance_utility_kind = _resolved_result_is_unsupported_combat_utility(
        last_chance_candidate,
        player_input,
    )
    after_state, runtime_state, resolved_result = _apply_last_chance_combat_utility_result(
        player_input=player_input,
        action=action,
        after_state=after_state,
        runtime_state=runtime_state,
        current_tick=current_tick,
        resolved_result=resolved_result,
        combat_state=combat_state,
        combat_result=combat_result,
        npc_combat_result=npc_combat_result,
        last_chance_candidate=last_chance_candidate,
        last_chance_utility_kind=last_chance_utility_kind,
    )
    grounded = _derive_grounded_scene_context(after_state, runtime_state, resolved_result)
    current_scene = _apply_grounded_scene_overlay(current_scene, grounded)
    runtime_state["grounded_scene_context"] = grounded
    runtime_state["current_scene"] = current_scene
    runtime_state["tick"] = int(after_state.get("tick", runtime_state.get("tick", 0)) or 0)
    summary = summarize_simulation_step(step_result)
    summary_text = "\n\n".join(_safe_str(line).strip() for line in _safe_list(summary) if _safe_str(line).strip())
    runtime_state["last_turn_result"] = {
        "player_input": player_input,
        "action": action,
        "semantic_action": semantic_action_record,
        "resolved_result": resolved_result,
        "combat_result": _safe_dict(resolved_result.get("combat_result")),
        "xp_result": _safe_dict(progression.get("xp_result")),
        "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
        "level_up": _safe_list(progression.get("level_up")),
        "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
        "summary": summary[:8],
    }
    runtime_state = _clear_stale_last_player_action(runtime_state, _safe_int(runtime_state.get("tick"), current_tick))
    turn_history = _safe_list(runtime_state.get("turn_history"))
    turn_history.append(_copy_dict(runtime_state["last_turn_result"]))
    runtime_state["turn_history"] = turn_history[-_MAX_HISTORY:]
    runtime_state = ensure_ambient_runtime_state(runtime_state)
    runtime_state["last_player_turn_at"] = _utc_now_iso()
    runtime_state = _record_real_player_activity(runtime_state)
    runtime_state["last_player_action_context"] = _classify_player_action_context(
        player_input, resolved_result, after_state, runtime_state,
    )
    runtime_state["post_player_quiet_ticks"] = _DEFAULT_POST_PLAYER_QUIET_TICKS
    session["runtime_state"] = runtime_state
    runtime_state["opening_runtime"] = _check_opening_resolution(session)
    runtime_state = _update_known_npc_ids(runtime_state, after_state)
    session["runtime_state"] = runtime_state
    _log_interaction_trace(
        "apply_turn_before_session_save",
        {
            "tick": _safe_int(after_state.get("tick"), current_tick),
            "last_player_action": _safe_dict(runtime_state.get("last_player_action")),
            "count": len(_safe_list(after_state.get("active_interactions"))),
            "items": _compact_active_interactions(_safe_list(after_state.get("active_interactions"))),
        },
        runtime_state,
    )
    session["simulation_state"] = after_state
    session["runtime_state"] = runtime_state
    session["setup_payload"] = next_setup
    manifest["updated_at"] = _utc_now_iso()
    session["manifest"] = manifest
    _t_pre_save = _time.monotonic()
    session = save_runtime_session(session)
    _t_save = _time.monotonic()
    perf_entry = {
        "tick": current_tick,
        "t_load": round(_t_load - _t0, 4),
        "t_advisory": round(_t_advisory - _t_load, 4),
        "t_semantic": round(_t_semantic - _t_advisory, 4),
        "t_authoritative": round(_t_authoritative - _t_semantic, 4),
        "t_step": round(_t_step - _t_authoritative, 4),
        "t_narration": 0.0,
        "t_pre_save": round(_t_pre_save - _t_step, 4),
        "t_save": round(_t_save - _t_pre_save, 4),
        "t_total": round(_t_save - _t0, 4),
        "fast_turn_mode": perf["fast_turn_mode"],
    }
    perf_entry.update({
        "session_id": session_id,
        "player_input_len": len(player_input or ""),
        "save_count": len(runtime_state.get("perf_trace", [])),
        "simulation_tick_before": current_tick,
        "tick_after": int(after_state.get("tick", current_tick) or current_tick),
    })
    logger.info(
        "[RPG TURN PERF] session=%s tick=%s load=%.3fs advisory=%.3fs semantic=%.3fs authoritative=%.3fs step=%.3fs pre_save=%.3fs save=%.3fs total=%.3fs fast_turn=%s",
        session_id,
        perf_entry["tick_after"],
        perf_entry["t_load"],
        perf_entry["t_advisory"],
        perf_entry["t_semantic"],
        perf_entry["t_authoritative"],
        perf_entry["t_step"],
        perf_entry["t_pre_save"],
        perf_entry["t_save"],
        perf_entry["t_total"],
        perf_entry["fast_turn_mode"],
    )
    runtime_state = _copy_dict(session.get("runtime_state"))
    runtime_state.setdefault("perf_trace", [])
    runtime_state["perf_trace"].append(perf_entry)
    runtime_state["perf_trace"] = runtime_state["perf_trace"][-_MAX_PERF_TRACE_ENTRIES:]
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)
    runtime_state = _copy_dict(session.get("runtime_state"))
    turn_id = _build_turn_id(runtime_state)
    final_tick = int(runtime_state.get("tick", current_tick) or current_tick)
    continuity_rows: List[Dict[str, Any]] = []
    continuity_facts: List[str] = []
    if _runtime_continuity_grounding_enabled(runtime_state):
        continuity_rows = _build_recent_narration_continuity(
            runtime_state,
            _safe_str(turn_id).strip(),
            limit=int(perf.get("continuity_turn_window", 3) or 3),
        )
        continuity_facts = _build_recent_authoritative_turn_facts(
            runtime_state,
            _safe_str(turn_id).strip(),
            limit=int(perf.get("continuity_turn_window", 3) or 3),
        )
    narration_context["recent_turns"] = continuity_rows
    narration_context["recent_authoritative_facts"] = continuity_facts
    narration_request = build_turn_narration_request(
        turn_id=turn_id,
        tick=final_tick,
        session_id=session_id,
        scene=current_scene,
        narration_context=narration_context,
        performance=perf,
    )
    return assemble_turn_narration_response(
        session=session,
        authoritative=authoritative,
        turn_contract=turn_contract,
        narration_request=narration_request,
        runtime_state=runtime_state,
        perf=perf,
        resolved_result=resolved_result,
    )

__all__ = [name for name in globals() if not name.startswith("__")]
