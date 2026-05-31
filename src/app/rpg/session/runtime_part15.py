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

def _maybe_resolve_general_interaction_turn(
    player_input: Any,
    runtime_state: Any,
    current_tick: Any,
) -> Dict[str, Any] | None:
    if _player_input_requests_general_interaction(player_input):
        simulation_state, interaction_result = resolve_general_interaction_v2(
            simulation_state,
            runtime_state,
            player_input,
        )

        resolved_result = {
            "action_type": interaction_result.get("action_type", "interact"),
            "visible_interaction_reason": f"interaction_{interaction_result.get('reason')}",
            "outcome": interaction_result.get("reason"),
            "interaction_result": interaction_result,
            "general_interaction_result": interaction_result,
            "forbidden_narration": interaction_result.get("forbidden_narration", []),
            "conversation_result": {
                "triggered": False,
                "reason": "general_interaction",
            },
        }

        narration = _fallback_general_interaction_narration(interaction_result)

        grounded = _derive_grounded_scene_context(
            simulation_state,
            runtime_state,
            resolved_result,
        )

        return {
            "ok": True,
            "simulation_state": simulation_state,
            "runtime_state": runtime_state,
            "session": {
                "simulation_state": simulation_state,
                "runtime_state": runtime_state,
            },
            "result": resolved_result,
            "resolved_result": resolved_result,
            "interaction_result": interaction_result,
            "general_interaction_result": interaction_result,
            "visible_interaction_reason": resolved_result["visible_interaction_reason"],
            "action_type": resolved_result["action_type"],
            "outcome": resolved_result["outcome"],
            "conversation_result": resolved_result["conversation_result"],
            "narration": narration,
            "final_narration": narration,
            "summary": narration,
            "narration_context": {
                "player_input": player_input,
                "action_type": resolved_result["action_type"],
                "resolved_result": resolved_result,
                "simulation_state": simulation_state,
                "runtime_state": runtime_state,
                "combat_result": {},
                "npc_combat_result": {},
                "combat_state": {},
                "grounded": grounded,
                "xp_result": {},
                "skill_xp_result": {},
                "level_up": [],
                "skill_level_ups": [],
                "settings": runtime_state.get("runtime_settings", {}),
                "conversation_threads": [],
                "forbidden_narration": interaction_result.get("forbidden_narration", []),
            },
            "turn_id": _build_turn_id(runtime_state),
            "tick": current_tick,
        }
    return None

def _apply_advisory_phase(
    player_input: Any,
    action: Any,
    simulation_state: Any,
    runtime_state: Any,
    current_tick: Any,
    _get_llm_gateway: Any,
    _stage_started: Any,
    advisory: Any,
    key: Any,
    mode: Any,
    perf: Any,
    record: Any,
    record_replay_artifacts: Any,
    recorded_policy: Any,
    semantic_advisory: Any,
    semantic_key: Any,
    semantic_record: Any,
    semantic_record_capture: Any,
    turn_exec_index: Any,
    turn_exec_key: Any,
) -> tuple[Any, Any, Any, Any]:
    if mode == "live":
        record_turn_perf_trace(
            "authoritative_advisory_policy",
            enable_action_advisory=bool(perf.get("enable_action_advisory")),
            enable_semantic_action_advisory=bool(perf.get("enable_semantic_action_advisory")),
            deferred_runtime_advisory_suppressed=bool(runtime_state.get("deferred_runtime_advisory_suppressed")),
        )
        if perf["enable_action_advisory"]:
            _stage_started = __import__("time").perf_counter()
            try:
                advisory = get_action_advisory(
                    llm_gateway=_get_llm_gateway(),
                    player_input=player_input,
                    simulation_state=simulation_state,
                    runtime_state=runtime_state,
                    candidate_action=action,
                )
                record = {
                    "type": "action_advisory",
                    "tick": current_tick,
                    "player_input": player_input,
                    "candidate_action": {
                        "action_type": _safe_str(action.get("action_type")),
                        "target_id": _safe_str(action.get("target_id")),
                        "npc_id": _safe_str(action.get("npc_id")),
                        "item_id": _safe_str(action.get("item_id")),
                    },
                    "output": _safe_dict(advisory),
                }
                if record_replay_artifacts:
                    runtime_state["llm_records"].append(record)
                    runtime_state["llm_records_index"][f"action_advisory:{current_tick}"] = record
            except Exception as e:
                logger.warning(f"Action advisory failed: {e}", exc_info=True)
                advisory = {}
            record_elapsed_turn_stage(
                "authoritative_action_advisory",
                _stage_started,
                advisory_present=bool(advisory),
            )

        if perf["enable_semantic_action_advisory"]:
            _stage_started = __import__("time").perf_counter()
            try:
                semantic_advisory = get_semantic_action_advisory(
                    llm_gateway=_get_llm_gateway(),
                    player_input=player_input,
                    simulation_state=simulation_state,
                    runtime_state=runtime_state,
                    candidate_action=action,
                )
                semantic_record_capture = {
                    "type": "semantic_action_advisory",
                    "tick": current_tick,
                    "player_input": player_input,
                    "candidate_action": {
                        "action_type": _safe_str(action.get("action_type")),
                        "target_id": _safe_str(action.get("target_id")),
                    },
                    "output": _safe_dict(semantic_advisory),
                }
                if record_replay_artifacts:
                    runtime_state["llm_records"].append(semantic_record_capture)
                    runtime_state["llm_records_index"][f"semantic_action_advisory:{current_tick}"] = semantic_record_capture
            except Exception as e:
                logger.warning(f"Semantic action advisory failed: {e}", exc_info=True)
                semantic_advisory = {}
            record_elapsed_turn_stage(
                "authoritative_semantic_action_advisory",
                _stage_started,
                semantic_advisory_present=bool(semantic_advisory),
            )
        if record_replay_artifacts:
            runtime_state = _prune_llm_records_state(runtime_state)
    else:
        turn_exec_index = _safe_dict(runtime_state.get("turn_execution_index"))
        if turn_exec_key not in turn_exec_index:
            raise RuntimeError(f"missing_replay_turn_execution_policy_for_tick:{current_tick}")
        recorded_policy = _safe_dict(turn_exec_index.get(turn_exec_key))

        key = f"action_advisory:{current_tick}"
        record = _safe_dict(runtime_state.get("llm_records_index")).get(key)
        if record:
            advisory = _safe_dict(record.get("output"))
        elif recorded_policy.get("enable_action_advisory", True):
            raise RuntimeError(f"missing_replay_action_advisory_for_tick:{current_tick}")

        semantic_key = f"semantic_action_advisory:{current_tick}"
        semantic_record = _safe_dict(runtime_state.get("llm_records_index")).get(semantic_key)
        if semantic_record:
            semantic_advisory = _safe_dict(semantic_record.get("output"))
        elif recorded_policy.get("enable_semantic_action_advisory", True):
            raise RuntimeError(f"missing_replay_semantic_action_advisory_for_tick:{current_tick}")
    return runtime_state, _stage_started, advisory, semantic_advisory


def _force_combat_utility_action_type(
    player_input: Any,
    action: Any,
    simulation_state: Any,
    runtime_state: Any,
    current_tick: Any,
    semantic_action_record: Any,
    _stage_started: Any,
    mode: Any,
    perf: Any,
    record_replay_artifacts: Any,
    semantic_advisory: Any,
    semantic_compiled_capture: Any,
    semantic_compiled_key: Any,
    semantic_compiled_record: Any,
) -> tuple[Any, Any]:
    if mode == "live":
        _stage_started = __import__("time").perf_counter()
        if perf["enable_semantic_action_advisory"]:
            semantic_action_record = _compile_semantic_action_record(
                simulation_state=simulation_state,
                runtime_state=runtime_state,
                player_input=player_input,
                action=action,
                semantic_advisory=semantic_advisory,
            )
        else:
            semantic_action_record = _build_fast_semantic_action_record(
                player_input, action, simulation_state,
            )
        record_elapsed_turn_stage(
            "authoritative_semantic_action_compile",
            _stage_started,
            advisory_enabled=bool(perf.get("enable_semantic_action_advisory")),
            semantic_action_type=_safe_str(_safe_dict(semantic_action_record).get("semantic_action_type")),
            semantic_family=_safe_str(_safe_dict(semantic_action_record).get("semantic_family")),
        )
        semantic_compiled_capture = {
            "type": "semantic_action_compiled",
            "tick": current_tick,
            "player_input": player_input,
            "output": _safe_dict(semantic_action_record),
        }
        if record_replay_artifacts:
            runtime_state["llm_records"].append(semantic_compiled_capture)
            runtime_state["llm_records_index"][semantic_compiled_key] = semantic_compiled_capture
            runtime_state = _prune_llm_records_state(runtime_state)
    else:
        semantic_compiled_record = _safe_dict(runtime_state.get("llm_records_index")).get(semantic_compiled_key)
        if not semantic_compiled_record:
            raise RuntimeError(f"missing_replay_semantic_action_compiled_for_tick:{current_tick}")
        semantic_action_record = _safe_dict(semantic_compiled_record.get("output"))
    return runtime_state, semantic_action_record


def _apply_ambient_conversation_result(
    after_action_state: Any,
    resolved_result: Any,
    authoritative: Any,
    ambient_tick_result: Any,
    conversation_result: Any,
) -> tuple[Any]:
    if ambient_tick_result:
        conversation_result = _safe_dict(ambient_tick_result.get("conversation_result"))
        resolved_result["action_type"] = "ambient_tick"
        resolved_result["semantic_action_type"] = "ambient_tick"
        resolved_result["semantic_family"] = "ambient"
        resolved_result["activity_label"] = "autonomous_ambient_tick"
        resolved_result["service_result"] = {
            "matched": False,
            "kind": "not_service",
            "status": "not_service",
            "reason": "ambient_tick",
        }
        resolved_result["travel_result"] = {}
        resolved_result["ambient_tick_result"] = ambient_tick_result
        resolved_result["conversation_result"] = conversation_result
        resolved_result["conversation_thread_state"] = _safe_dict(after_action_state.get("conversation_thread_state"))
        resolved_result["world_event_state"] = _safe_dict(after_action_state.get("world_event_state"))
        authoritative["action_type"] = "ambient_tick"
        authoritative["semantic_action_type"] = "ambient_tick"
        authoritative["semantic_family"] = "ambient"
        authoritative["activity_label"] = "autonomous_ambient_tick"
        authoritative["service_result"] = {
            "matched": False,
            "kind": "not_service",
            "status": "not_service",
            "reason": "ambient_tick",
        }
        authoritative["travel_result"] = {}
        authoritative["ambient_tick_result"] = ambient_tick_result
        authoritative["conversation_result"] = conversation_result
        authoritative["conversation_thread_state"] = _safe_dict(after_action_state.get("conversation_thread_state"))
        authoritative["world_event_state"] = _safe_dict(after_action_state.get("world_event_state"))
        authoritative["simulation_state"] = after_action_state
    return conversation_result


def _build_and_apply_turn_contract_phase(
    player_input: Any,
    action: Any,
    simulation_state: Any,
    before_state: Any,
    after_action_state: Any,
    runtime_state: Any,
    resolved_result: Any,
    semantic_action_record: Any,
    before_state_for_contract: Any,
    contract_resolved: Any,
    resolved_for_contract: Any,
    resolved_from_contract: Any,
    runtime_settings_for_contract: Any,
    turn_contract: Any,
) -> tuple[Any, Any, Any]:
    if _safe_bool(runtime_settings_for_contract.get("enable_turn_contract"), True):
        before_state_for_contract = _safe_dict(before_state if "before_state" in locals() else simulation_state)
        turn_contract = build_turn_contract(
            player_input=player_input,
            action=action,
            resolved_action=resolved_result,
            simulation_state_before=before_state_for_contract,
            simulation_state_after=after_action_state,
            runtime_state=runtime_state,
        )
        if turn_contract:
            turn_contract["semantic_action"] = semantic_action_record
            resolved_for_contract = _safe_dict(
                turn_contract.get("resolved_result") or turn_contract.get("resolved_action")
            )
            resolved_for_contract["semantic_action"] = semantic_action_record
            turn_contract["resolved_result"] = resolved_for_contract
            turn_contract["resolved_action"] = resolved_for_contract

            resolved_from_contract = _safe_dict(
                turn_contract.get("resolved_result")
                or turn_contract.get("resolved_action")
            )
            if resolved_from_contract:
                resolved_from_contract = _apply_visible_interaction_reason_to_resolved_result(
                    resolved_from_contract,
                    general_interaction_result=general_interaction_result,
                )
                if "resolved_result" in turn_contract:
                    turn_contract["resolved_result"] = resolved_from_contract
                else:
                    turn_contract["resolved_action"] = resolved_from_contract

            turn_contract["visible_interaction_reason"] = _interaction_visible_result_reason(
                general_interaction_result
            )
            if turn_contract["visible_interaction_reason"]:
                turn_contract = _patch_visible_interaction_reason_into_payload_text(
                    turn_contract,
                    visible_reason=turn_contract["visible_interaction_reason"],
                )

            if combat_narration_contract:
                turn_contract["combat_narration_contract"] = deepcopy(combat_narration_contract)
            if combat_narration_validation:
                turn_contract["combat_narration_validation"] = deepcopy(combat_narration_validation)

            resolved_from_contract = _safe_dict(
                turn_contract.get("resolved_result")
                or turn_contract.get("resolved_action")
            )
            if resolved_from_contract:
                resolved_from_contract["llm_called"] = combat_llm_called
                resolved_from_contract["llm_purpose"] = "combat_narration" if combat_llm_called else ""
                resolved_from_contract["combat_narration_contract"] = deepcopy(combat_narration_contract)
                resolved_from_contract["combat_narration_validation"] = deepcopy(combat_narration_validation)
                resolved_from_contract["combat_narration_payload"] = deepcopy(combat_narration_payload)
                resolved_from_contract["combat_narration_error"] = combat_llm_error
                if "resolved_result" in turn_contract:
                    turn_contract["resolved_result"] = resolved_from_contract
                else:
                    turn_contract["resolved_action"] = resolved_from_contract

                contract_resolved = _safe_dict(
                    turn_contract.get("resolved_result")
                    or turn_contract.get("resolved_action")
                )
                if contract_resolved:
                    contract_resolved = _patch_visible_interaction_reason_into_payload_text(
                        contract_resolved,
                        visible_reason=turn_contract["visible_interaction_reason"],
                    )
                    if "resolved_result" in turn_contract:
                        turn_contract["resolved_result"] = contract_resolved
                    else:
                        turn_contract["resolved_action"] = contract_resolved
        contract_resolved = merge_service_result_into_contract_resolved(
            resolved_result,
            _safe_dict(turn_contract.get("resolved_action") or resolved_result),
        )

        resolved_result = contract_resolved
        after_action_state = apply_state_delta(
            after_action_state,
            _safe_dict(turn_contract.get("state_delta")),
        )
        runtime_state["last_turn_contract"] = turn_contract
    return after_action_state, resolved_result, turn_contract


def _build_fallback_turn_contract_phase(
    player_input: Any,
    action: Any,
    simulation_state: Any,
    before_state: Any,
    runtime_state: Any,
    resolved_result: Any,
    semantic_action_record: Any,
    ambient_tick_result: Any,
    service_result: Any,
    turn_contract: Any,
) -> tuple[Any]:
    if not turn_contract:
        if ambient_tick_result:
            service_result = resolved_result["service_result"]
        else:
            service_result = resolve_service_turn(
                player_input=player_input,
                action=action,
                resolved_action=resolved_result,
                simulation_state=before_state if "before_state" in locals() else simulation_state,
                runtime_state=runtime_state,
            )
        if service_result.get("matched"):
            resolved_result["service_result"] = service_result

        turn_contract = {
            "version": "turn_contract_v1",
            # Keep the primary contract version so downstream tooling treats this
            # bridge payload like the authoritative contract, while still marking
            # the fallback origin explicitly for debugging.
            "contract_source": "runtime_fallback_bridge",
            "player_input": player_input,
            "action": action,
            "resolved_action": resolved_result,
            "resolved_result": resolved_result,
            "service_result": service_result,
            "semantic_action": semantic_action_record,
            "state_delta": {},
            "narration_brief": {
                "summary": _safe_str(
                    resolved_result.get("narrative_brief")
                    or resolved_result.get("message")
                    or resolved_result.get("summary")
                    or player_input
                )
            },
            "presentation": {
                "available_actions": _safe_list(service_result.get("available_actions"))
                if service_result.get("matched")
                else [],
            },
        }
        runtime_state["last_turn_contract"] = turn_contract
    return turn_contract


def _apply_last_chance_combat_utility_result(
    player_input: Any,
    action: Any,
    after_state: Any,
    runtime_state: Any,
    current_tick: Any,
    resolved_result: Any,
    combat_state: Any,
    combat_result: Any,
    npc_combat_result: Any,
    last_chance_candidate: Any,
    last_chance_utility_kind: Any,
) -> tuple[Any, Any, Any]:
    if last_chance_utility_kind:
        rescued_combat_state = normalize_combat_state(
            _safe_dict(last_chance_candidate.get("combat_state"))
        )
        combat_state = rescued_combat_state
        combat_result = {}
        npc_combat_result = {}

        current_actor_id = get_current_actor_id(combat_state)
        if current_actor_id and _safe_str(current_actor_id) != _safe_str("player"):
            resolved_result = _build_combat_gate_result(current_actor_id, "player")

        elif last_chance_utility_kind == "defend":
            defense_resolution = resolve_defend(
                after_state,
                combat_state,
                _safe_str("player"),
            )
            combat_result = defense_resolution.to_dict()
            after_state, combat_state = apply_defense_resolution(
                after_state,
                combat_state,
                combat_result,
            )
            resolved_result["action_type"] = "defend"
            resolved_result["outcome"] = "defended"
            resolved_result["visible_interaction_reason"] = "combat_defend"
            resolved_result["combat_result"] = combat_result
            resolved_result["interaction_result"] = {}
            resolved_result["general_interaction_result"] = {}

        elif last_chance_utility_kind == "flee":
            flee_resolution = resolve_flee(
                after_state,
                combat_state,
                _safe_str("player"),
                turn_id=_build_turn_id(runtime_state),
                tick=current_tick,
            )
            combat_result = flee_resolution.to_dict()
            after_state, combat_state = apply_flee_resolution(
                after_state,
                combat_state,
                combat_result,
            )
            resolved_result["action_type"] = "flee"
            resolved_result["outcome"] = "fled" if combat_result.get("success") else "flee_failed"
            resolved_result["visible_interaction_reason"] = "combat_flee"
            resolved_result["combat_result"] = combat_result
            resolved_result["interaction_result"] = {}
            resolved_result["general_interaction_result"] = {}

        elif last_chance_utility_kind == "use_item":
            item_id = _infer_inventory_item_id_from_text(after_state, action, player_input)
            item_result = apply_item_effects(after_state, item_id)
            after_state = _ensure_simulation_state(
                _safe_dict(item_result.get("simulation_state"))
            )
            combat_result = _safe_dict(item_result.get("result"))
            combat_result.setdefault("action_type", "use_item")
            combat_result.setdefault("combat_id", _safe_str(combat_state.get("combat_id")))
            combat_result.setdefault(
                "notes",
                ["combat_item_used"] if combat_result.get("ok") else ["combat_item_failed"],
            )
            resolved_result["action_type"] = "use_item"
            resolved_result["outcome"] = "item_used" if combat_result.get("ok") else "item_use_failed"
            resolved_result["visible_interaction_reason"] = "combat_use_item"
            resolved_result["combat_result"] = combat_result
            resolved_result["inventory_result"] = combat_result
            resolved_result["interaction_result"] = {}
            resolved_result["general_interaction_result"] = {}

        if combat_state.get("active"):
            combat_state = advance_turn(combat_state)
            current_after_player = get_current_actor_id(combat_state)
            if current_after_player and not _actor_is_player(after_state, current_after_player):
                after_state, combat_state, npc_combat_result = run_npc_turn(
                    after_state,
                    combat_state,
                    tick=current_tick,
                )
                combat_state = evaluate_combat_exit(after_state, combat_state)

        runtime_state = _set_combat_state(runtime_state, combat_state)
        resolved_result["combat_state"] = combat_state

        if npc_combat_result:
            resolved_result["npc_combat_result"] = npc_combat_result
    return after_state, runtime_state, resolved_result

def _apply_active_non_attack_combat_action(
    player_input: Any,
    action: Any,
    after_action_state: Any,
    runtime_state: Any,
    current_tick: Any,
    turn_id: Any,
    final_tick: Any,
    player_actor_id: Any,
    resolved_result: Any,
    authoritative: Any,
    combat_state: Any,
    combat_result: Any,
    npc_combat_result: Any,
    is_combat_action: Any,
    is_combat_attack: Any,
    is_combat_defend: Any,
    is_combat_flee: Any,
    is_combat_use_item: Any,
    normalized_action_type: Any,
) -> Dict[str, Any]:
    if combat_state.get('active') and is_combat_action and (not is_combat_attack):
        current_actor_id = get_current_actor_id(combat_state)
        if current_actor_id and _safe_str(current_actor_id) != _safe_str(player_actor_id):
            resolved_result = _build_combat_gate_result(current_actor_id, player_actor_id)
            grounded = _derive_grounded_scene_context(after_action_state, runtime_state, resolved_result)
            narration_context = {'player_input': player_input, 'action_type': normalized_action_type, 'resolved_result': resolved_result, 'simulation_state': after_action_state, 'runtime_state': runtime_state, 'combat_result': {}, 'npc_combat_result': {}, 'combat_state': combat_state, 'grounded': grounded, 'xp_result': {}, 'skill_xp_result': {}, 'level_up': [], 'skill_level_ups': [], 'settings': runtime_state.get('runtime_settings', {}), 'conversation_threads': build_conversation_thread_prompt_context(runtime_state, current_tick=current_tick, limit=4)}
            return {'return_result': {'ok': True, 'simulation_state': after_action_state, 'runtime_state': runtime_state, 'result': resolved_result, 'narration_context': narration_context, 'turn_id': _build_turn_id(runtime_state), 'tick': current_tick}}
        if is_combat_defend:
            defense_resolution = resolve_defend(after_action_state, combat_state, _safe_str(player_actor_id))
            defense_dict = defense_resolution.to_dict()
            after_action_state, combat_state = apply_defense_resolution(after_action_state, combat_state, defense_dict)
            if combat_state.get('active'):
                combat_state = advance_turn(combat_state)
                current_after_player = get_current_actor_id(combat_state)
                if current_after_player and (not _actor_is_player(after_action_state, current_after_player)):
                    after_action_state, combat_state, npc_combat_result = run_npc_turn(after_action_state, combat_state, tick=current_tick)
                    combat_state = evaluate_combat_exit(after_action_state, combat_state)
            runtime_state = _set_combat_state(runtime_state, combat_state)
            combat_result = defense_dict
            authoritative['simulation_state'] = after_action_state
            resolved_result['combat_result'] = combat_result
            resolved_result['action_type'] = 'defend'
            resolved_result['outcome'] = 'defended'
            resolved_result['visible_interaction_reason'] = 'combat_defend'
            resolved_result['interaction_result'] = {}
            if npc_combat_result:
                resolved_result['npc_combat_result'] = npc_combat_result
            authoritative['result'] = resolved_result
        elif is_combat_flee:
            flee_resolution = resolve_flee(after_action_state, combat_state, _safe_str(player_actor_id), turn_id=turn_id, tick=final_tick)
            flee_dict = flee_resolution.to_dict()
            after_action_state, combat_state = apply_flee_resolution(after_action_state, combat_state, flee_dict)
            if combat_state.get('active'):
                combat_state = advance_turn(combat_state)
                current_after_player = get_current_actor_id(combat_state)
                if current_after_player and (not _actor_is_player(after_action_state, current_after_player)):
                    after_action_state, combat_state, npc_combat_result = run_npc_turn(after_action_state, combat_state, tick=current_tick)
                    combat_state = evaluate_combat_exit(after_action_state, combat_state)
            runtime_state = _set_combat_state(runtime_state, combat_state)
            combat_result = flee_dict
            authoritative['simulation_state'] = after_action_state
            resolved_result['combat_result'] = combat_result
            resolved_result['action_type'] = 'flee'
            resolved_result['outcome'] = 'fled' if flee_dict.get('success') else 'flee_failed'
            resolved_result['visible_interaction_reason'] = 'combat_flee'
            resolved_result['interaction_result'] = {}
            if npc_combat_result:
                resolved_result['npc_combat_result'] = npc_combat_result
            authoritative['result'] = resolved_result
        elif is_combat_use_item:
            item_id = _infer_inventory_item_id_from_text(after_action_state, action, player_input)
            item_result = apply_item_effects(after_action_state, item_id)
            after_action_state = _ensure_simulation_state(_safe_dict(item_result.get('simulation_state')))
            use_result = _safe_dict(item_result.get('result'))
            use_result.setdefault('action_type', 'use_item')
            use_result.setdefault('combat_id', _safe_str(combat_state.get('combat_id')))
            use_result.setdefault('notes', ['combat_item_used'] if use_result.get('ok') else ['combat_item_failed'])
            recent = list(combat_state.get('recent_events') or [])
            recent.append({'type': 'use_item_resolution', 'actor_id': _safe_str(player_actor_id), 'item_id': item_id, 'ok': bool(use_result.get('ok')), 'reason': _safe_str(use_result.get('reason'))})
            combat_state['recent_events'] = recent[-24:]
            combat_state['last_resolution'] = dict(use_result)
            if combat_state.get('active'):
                combat_state = advance_turn(combat_state)
                current_after_player = get_current_actor_id(combat_state)
                if current_after_player and (not _actor_is_player(after_action_state, current_after_player)):
                    after_action_state, combat_state, npc_combat_result = run_npc_turn(after_action_state, combat_state, tick=current_tick)
                    combat_state = evaluate_combat_exit(after_action_state, combat_state)
            runtime_state = _set_combat_state(runtime_state, combat_state)
            combat_result = use_result
            authoritative['simulation_state'] = after_action_state
            resolved_result['combat_result'] = combat_result
            resolved_result['action_type'] = 'use_item'
            resolved_result['outcome'] = 'item_used' if use_result.get('ok') else 'item_use_failed'
            resolved_result['visible_interaction_reason'] = 'combat_use_item'
            resolved_result['interaction_result'] = {}
            resolved_result['inventory_result'] = use_result
            if npc_combat_result:
                resolved_result['npc_combat_result'] = npc_combat_result
            authoritative['result'] = resolved_result
    _maybe_return_completed_combat_utility_turn_result = _maybe_return_completed_combat_utility_turn(player_input=player_input, after_action_state=after_action_state, runtime_state=runtime_state, current_tick=current_tick, combat_result=combat_result, combat_state=combat_state, is_combat_action=is_combat_action, is_combat_attack=is_combat_attack, normalized_action_type=normalized_action_type, npc_combat_result=npc_combat_result, resolved_result=resolved_result)
    if _maybe_return_completed_combat_utility_turn_result is not None:
        return {'return_result': _maybe_return_completed_combat_utility_turn_result}
    return {"return_result": None, "after_action_state": after_action_state, "runtime_state": runtime_state, "resolved_result": resolved_result, "combat_state": combat_state, "combat_result": combat_result, "npc_combat_result": npc_combat_result}


def _apply_attack_combat_action(
    player_input: Any,
    after_action_state: Any,
    runtime_state: Any,
    current_tick: Any,
    turn_id: Any,
    final_tick: Any,
    player_actor_id: Any,
    resolved_result: Any,
    authoritative: Any,
    combat_state: Any,
    combat_result: Any,
    npc_combat_result: Any,
    is_combat_attack: Any,
    normalized_action_type: Any,
    target_id: Any,
) -> Dict[str, Any]:
    if is_combat_attack and target_id:
        if not combat_state.get('active'):
            participant_ids = build_combat_participants(after_action_state, [player_actor_id, target_id])
            combat_state = begin_combat(after_action_state, combat_state, participant_ids, combat_id=f'combat:{turn_id}', tick=final_tick, initial_target_id=target_id)
            runtime_state = _set_combat_state(runtime_state, combat_state)
        current_actor_id = get_current_actor_id(combat_state)
        if not combat_state.get('active') or not current_actor_id:
            is_combat_action = False
        if current_actor_id and _safe_str(current_actor_id) != _safe_str(player_actor_id):
            resolved_result = _build_combat_gate_result(current_actor_id, player_actor_id)
            grounded = _derive_grounded_scene_context(after_action_state, runtime_state, resolved_result)
            narration_context = {'player_input': player_input, 'action_type': normalized_action_type, 'resolved_result': resolved_result, 'simulation_state': after_action_state, 'runtime_state': runtime_state, 'combat_result': {}, 'npc_combat_result': {}, 'combat_state': combat_state, 'grounded': grounded, 'xp_result': {}, 'skill_xp_result': {}, 'level_up': [], 'skill_level_ups': [], 'settings': runtime_state.get('runtime_settings', {}), 'conversation_threads': build_conversation_thread_prompt_context(runtime_state, current_tick=current_tick, limit=4)}
            return {'return_result': {'ok': True, 'simulation_state': after_action_state, 'runtime_state': runtime_state, 'result': resolved_result, 'narration_context': narration_context, 'turn_id': turn_id, 'tick': current_tick}}
        intent = AttackIntent(actor_id=_safe_str(player_actor_id), target_id=target_id, action_type='unarmed_attack' if normalized_action_type in {'punch', 'unarmed_attack', 'attack_unarmed'} else 'melee_attack')
        resolution = resolve_attack(after_action_state, combat_state, intent, turn_id=turn_id, tick=final_tick)
        after_action_state, combat_state = apply_attack_resolution(after_action_state, combat_state, resolution.to_dict())
        combat_state = evaluate_combat_exit(after_action_state, combat_state)
        if combat_state.get('active'):
            combat_state = advance_turn(combat_state)
            current_after_player = get_current_actor_id(combat_state)
            if current_after_player and (not _actor_is_player(after_action_state, current_after_player)):
                after_action_state, combat_state, npc_combat_result = run_npc_turn(after_action_state, combat_state, tick=current_tick)
                combat_state = evaluate_combat_exit(after_action_state, combat_state)
        runtime_state = _set_combat_state(runtime_state, combat_state)
        combat_result = resolution.to_dict()
        authoritative['simulation_state'] = after_action_state
        resolved_result['combat_result'] = combat_result
        if npc_combat_result:
            resolved_result['npc_combat_result'] = npc_combat_result
        authoritative['result'] = resolved_result
    return {"return_result": None, "after_action_state": after_action_state, "runtime_state": runtime_state, "resolved_result": resolved_result, "combat_state": combat_state, "combat_result": combat_result, "npc_combat_result": npc_combat_result}

__all__ = [name for name in globals() if not name.startswith("__")]
