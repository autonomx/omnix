from __future__ import annotations

# RPG session runtime responsibility module.
# PR.1.14 override: keep legacy session attack turns reward-consistent
# with the newer direct combat runtime API.
from app.rpg.combat.lifecycle import (
    build_combat_participants as build_combat_participants, evaluate_combat_exit as evaluate_combat_exit,
)
from app.rpg.combat.initiative import (
    advance_turn as advance_turn, begin_combat as begin_combat,
)
from app.rpg.session.semantic_state_changes import (
    _set_combat_state as _set_combat_state,
)
from app.rpg.combat.state import (
    get_current_actor_id as get_current_actor_id,
)
from app.rpg.session.state_normalization import (
    _safe_dict as _safe_dict, _safe_str as _safe_str,
)
from app.rpg.session.combat_intent import (
    _actor_is_player as _actor_is_player, _build_combat_gate_result as _build_combat_gate_result, _derive_grounded_scene_context as _derive_grounded_scene_context,
)
from app.rpg.ai.conversation_threads import (
    build_conversation_thread_prompt_context as build_conversation_thread_prompt_context,
)
from app.rpg.combat.models import (
    AttackIntent as AttackIntent,
)
from app.rpg.combat.resolver import (
    resolve_attack as resolve_attack,
)
from app.rpg.combat.apply import (
    apply_attack_resolution as apply_attack_resolution,
)
from app.rpg.combat.npc_turns import (
    run_npc_turn as run_npc_turn,
)
from typing import (
    Any as Any, Dict as Dict,
)


from app.rpg.interactions.loot_runtime import generate_loot_from_table


def _session_attack_reward_session_id(runtime_state: Any, turn_id: Any) -> str:
    return _safe_str(
        _safe_dict(runtime_state).get("session_id")
        or _safe_dict(runtime_state).get("id")
        or turn_id
        or "session-attack-runtime"
    )


def _attach_session_attack_defeat_reward(
    *,
    after_action_state: Any,
    runtime_state: Any,
    combat_state: Any,
    combat_result: Any,
    target_id: Any,
    turn_id: Any,
    tick: Any,
) -> Dict[str, Any]:
    combat_result = _safe_dict(combat_result)
    combat_state = _safe_dict(combat_state)
    target_id = _safe_str(target_id)

    if not combat_result.get("defeated"):
        return combat_result
    if combat_state.get("active"):
        return combat_result
    if _safe_str(combat_state.get("ended_reason")) != "enemy_side_defeated":
        return combat_result
    if _safe_dict(combat_result.get("xp_result")):
        return combat_result

    participants = _safe_dict(combat_state.get("participants"))
    defeated_target = _safe_dict(participants.get(target_id))
    loot_table_id = _safe_str(defeated_target.get("loot_table_id") or "loot:bandit_common")
    loot_result = generate_loot_from_table(
        after_action_state,
        loot_table_id=loot_table_id,
        source_id=target_id,
        session_id=_session_attack_reward_session_id(runtime_state, turn_id),
        tick=int(tick or 0),
        add_to_inventory=True,
    )
    combat_result["loot_result"] = _safe_dict(loot_result)
    xp_result = _safe_dict(_safe_dict(loot_result).get("xp_result"))
    if xp_result:
        combat_result["xp_result"] = xp_result
    return combat_result


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
        combat_result = _attach_session_attack_defeat_reward(
            after_action_state=after_action_state,
            runtime_state=runtime_state,
            combat_state=combat_state,
            combat_result=combat_result,
            target_id=target_id,
            turn_id=turn_id,
            tick=final_tick,
        )
        authoritative['simulation_state'] = after_action_state
        resolved_result['combat_result'] = combat_result
        if _safe_dict(combat_result.get('loot_result')):
            resolved_result['loot_result'] = _safe_dict(combat_result.get('loot_result'))
        if _safe_dict(combat_result.get('xp_result')):
            resolved_result['xp_result'] = _safe_dict(combat_result.get('xp_result'))
        if npc_combat_result:
            resolved_result['npc_combat_result'] = npc_combat_result
        authoritative['result'] = resolved_result
    return {"return_result": None, "after_action_state": after_action_state, "runtime_state": runtime_state, "resolved_result": resolved_result, "combat_state": combat_state, "combat_result": combat_result, "npc_combat_result": npc_combat_result}


__all__ = ['_apply_attack_combat_action', '_attach_session_attack_defeat_reward', '_session_attack_reward_session_id']