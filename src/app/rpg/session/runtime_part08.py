from __future__ import annotations

# Generated split module for app.rpg.session.runtime.
from .runtime_part01 import *
from .runtime_part02 import *
from .runtime_part03 import *
from .runtime_part04 import *
from .runtime_part05 import *
from .runtime_part06 import *
from .runtime_part07 import *

def _force_active_combat_utility_action(
    runtime_state: Dict[str, Any],
    action: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    player_input: str,
) -> Dict[str, Any]:
    combat_state = _get_combat_state(runtime_state)
    if not _safe_dict(combat_state).get("active"):
        return _safe_dict(action)

    if _player_input_requests_combat_ability(player_input):
        return _safe_dict(action)

    action = dict(_safe_dict(action))
    text = _safe_str(player_input).strip().lower()
    semantic_kind = _safe_str(
        _safe_dict(semantic_action_record).get("kind")
        or _safe_dict(semantic_action_record).get("action_type")
    ).strip().lower()

    if semantic_kind == "defend" or any(term in text for term in ("defend", "guard", "block", "brace", "take cover")):
        action["action_type"] = "defend"
        action.pop("target_id", None)
        return action

    if semantic_kind == "flee" or any(term in text for term in ("flee", "run away", "retreat", "escape", "withdraw")):
        action["action_type"] = "flee"
        action.pop("target_id", None)
        return action

    if semantic_kind == "use_item" or any(term in text for term in ("use ", "drink ", "quaff ", "consume ", "eat ")):
        action["action_type"] = "use_item"
        action.pop("target_id", None)
        return action

    return action


def _extract_active_combat_state_for_turn(
    runtime_state: Dict[str, Any],
    resolved_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    combat_state = _safe_dict(_get_combat_state(runtime_state))
    if combat_state.get("active"):
        return combat_state

    resolved_result = _safe_dict(resolved_result)
    direct = _safe_dict(resolved_result.get("combat_state"))
    if direct.get("active"):
        return normalize_combat_state(direct)

    interaction_result = _safe_dict(resolved_result.get("interaction_result"))
    interaction_combat = _safe_dict(_safe_dict(interaction_result.get("combat_result")).get("combat_state"))
    if interaction_combat.get("active"):
        return normalize_combat_state(interaction_combat)

    return combat_state


def _lookup_actor_by_id(simulation_state: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    for collection_key in ("actor_states", "npc_states"):
        for actor in _safe_list(simulation_state.get(collection_key)):
            if _safe_str(actor.get("id")).strip() == _safe_str(actor_id).strip():
                return actor
    return {}


def _actor_is_player(simulation_state: Dict[str, Any], actor_id: str) -> bool:
    actor = _lookup_actor_by_id(simulation_state, actor_id)
    return bool(actor.get("is_player")) or _safe_str(actor.get("type")).strip().lower() == "player"


def _build_combat_gate_result(current_actor_id: str, player_actor_id: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "blocked": True,
        "message": "It is not your turn in combat.",
        "reason": "combat_turn_gated",
        "expected_actor_id": current_actor_id,
        "player_actor_id": player_actor_id,
    }


def _action_requests_hostile_combat(action: Dict[str, Any], player_input: str) -> bool:
    action = _safe_dict(action)
    action_type = _safe_str(action.get("action_type")).strip().lower()
    if action_type in {"melee_attack", "unarmed_attack", "attack_melee", "attack_unarmed"}:
        return True
    if action_type in {"attack", "punch"}:
        text = _safe_str(player_input).strip().lower()
        hostile_terms = ("attack", "punch", "hit", "kick", "strike", "stab", "slash", "smash", "kill")
        return any(term in text for term in hostile_terms)
    return False


def _action_requests_combat_defend(action: Dict[str, Any], player_input: str) -> bool:
    action = _safe_dict(action)
    action_type = _safe_str(action.get("action_type")).strip().lower()
    text = _safe_str(player_input).strip().lower()
    return action_type in {"defend", "block", "dodge", "guard"} or any(
        term in text for term in ("defend", "block", "guard", "brace", "take cover")
    )


def _action_requests_combat_flee(action: Dict[str, Any], player_input: str) -> bool:
    action = _safe_dict(action)
    action_type = _safe_str(action.get("action_type")).strip().lower()
    text = _safe_str(player_input).strip().lower()
    return action_type in {"flee", "retreat", "escape"} or any(
        term in text for term in ("flee", "run away", "retreat", "escape", "withdraw")
    )


def _action_requests_combat_use_item(action: Dict[str, Any], player_input: str) -> bool:
    action = _safe_dict(action)
    action_type = _safe_str(action.get("action_type")).strip().lower()
    text = _safe_str(player_input).strip().lower()
    return action_type == "use_item" or any(
        term in text for term in ("use ", "drink ", "eat ", "consume ", "quaff ")
    )


def _action_requests_stabilize(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    return "stabilize" in text or "staunch" in text or "stop the bleeding" in text


def _action_requests_revive_or_heal_other(player_input: str) -> bool:
    text = _safe_str(player_input).strip().lower()
    return ("revive" in text or "heal" in text or "healing potion" in text) and any(
        name in text for name in ("bran", "companion", "ally")
    )


def _infer_recovery_target_actor_id(runtime_state: Dict[str, Any], player_input: str) -> str:
    text = _safe_str(player_input).strip().lower()
    combat_state = _safe_dict(_get_combat_state(runtime_state))
    participants = _safe_dict(combat_state.get("participants"))

    for actor_id, participant in participants.items():
        participant = _safe_dict(participant)
        name = _safe_str(participant.get("name")).strip().lower()
        if name and name in text:
            return str(actor_id)

    if "bran" in text:
        for actor_id, participant in participants.items():
            if "bran" in _safe_str(_safe_dict(participant).get("name")).strip().lower():
                return str(actor_id)

    for actor_id, participant in participants.items():
        participant = _safe_dict(participant)
        if _safe_str(participant.get("side")).strip() == "party" and actor_id != "player":
            return str(actor_id)

    return ""


def _infer_inventory_item_id_from_text(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
    player_input: str,
) -> str:
    explicit = _safe_str(action.get("item_id")).strip()
    if explicit:
        return explicit

    text = _safe_str(player_input).strip().lower()
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = normalize_inventory_state(_safe_dict(player_state.get("inventory_state")))

    for item in _safe_list(inventory_state.get("items")):
        item = _safe_dict(item)
        item_id = _safe_str(item.get("item_id")).strip()
        if not item_id:
            continue
        names = [
            _safe_str(item.get("name")),
            _safe_str(item.get("definition_id")),
            item_id,
        ]
        names.extend([_safe_str(x) for x in _safe_list(item.get("aliases"))])
        for name in names:
            name_lc = name.strip().lower()
            if name_lc and name_lc in text:
                return item_id

    # Safe fallback for common phrasing like "drink a potion".
    for item in _safe_list(inventory_state.get("items")):
        item = _safe_dict(item)
        item_id = _safe_str(item.get("item_id")).strip()
        name_lc = _safe_str(item.get("name")).strip().lower()
        if item_id and any(token in name_lc for token in ("potion", "draught", "elixir", "food", "ration")):
            return item_id

    return ""


def _interaction_trace_enabled(runtime_state: Dict[str, Any]) -> bool:
    runtime_state = _safe_dict(runtime_state)
    settings = _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings")))
    raw = settings.get("interaction_trace")
    if raw is None:
        return True
    return _safe_bool(raw, True)


def _compact_active_interactions(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for raw in _safe_list(items)[:8]:
        item = _safe_dict(raw)
        state = _safe_dict(item.get("state"))
        out.append(
            {
                "id": _safe_str(item.get("id")),
                "action_type": _safe_str(item.get("action_type")),
                "subtype": _safe_str(item.get("subtype")),
                "phase": _safe_str(item.get("phase")),
                "resolved": _safe_bool(item.get("resolved"), False),
                "updated_tick": _safe_int(item.get("updated_tick"), 0),
                "expires_tick": _safe_int(item.get("expires_tick"), 0),
                "participants": _safe_list(item.get("participants"))[:4],
                "mode": _safe_str(state.get("duration_mode")),
                "summary": _safe_str(state.get("summary"))[:120],
            }
        )
    return out


def _log_interaction_trace(label: str, payload: Dict[str, Any], runtime_state: Dict[str, Any] | None = None) -> None:
    if runtime_state is not None and not _interaction_trace_enabled(runtime_state):
        return
    try:
        print(f"INTERACTION TRACE {label} = {payload}")
    except Exception:
        pass



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()




def _stable_unique_labeled_items(values: List[Any], limit: int) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in _safe_list(values):
        if isinstance(raw, dict):
            value = (
                _safe_str(raw.get("summary")).strip()
                or _safe_str(raw.get("description")).strip()
                or _safe_str(raw.get("title")).strip()
                or _safe_str(raw.get("label")).strip()
                or _safe_str(raw.get("name")).strip()
            )
        else:
            value = _safe_str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= limit:
            break
    return out

def _build_world_advance_recap(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    debug_trace: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    debug_trace = _safe_dict(debug_trace)

    # Pull recent world signals
    world_events = _safe_list(simulation_state.get("recent_events"))
    consequences = _safe_list(simulation_state.get("recent_consequences"))
    threads = _safe_list(simulation_state.get("active_threads"))
    npcs = _safe_list(simulation_state.get("npc_states"))
    recent_changes = _safe_list(simulation_state.get("recent_changes"))
    director_log = _safe_list(runtime_state.get("director_log"))
    scene_beats = _safe_list(runtime_state.get("recent_scene_beats"))

    scene_title = (
        _safe_str(simulation_state.get("scene_title")) or
        _safe_str(debug_trace.get("scene_title"))
    )
    location_name = (
        _safe_str(simulation_state.get("location_name")) or
        _safe_str(debug_trace.get("location_name"))
    )

    # Fallbacks for current engine state shape.
    if not world_events:
        world_events = (
            _safe_list(simulation_state.get("events")) or
            _safe_list(simulation_state.get("world_events")) or
            _safe_list(runtime_state.get("world_events")) or
            _safe_list(runtime_state.get("recent_events"))
        )
    if not consequences:
        consequences = (
            _safe_list(simulation_state.get("effects")) or
            recent_changes or
            _safe_list(runtime_state.get("recent_changes"))
        )
    if not threads:
        threads = (
            _safe_list(simulation_state.get("threads")) or
            _safe_list(simulation_state.get("story_threads")) or
            _safe_list(runtime_state.get("threads"))
        )
    if not npcs:
        npcs = (
            _safe_list(simulation_state.get("actors")) or
            _safe_list(simulation_state.get("npcs")) or
            _safe_list(runtime_state.get("npc_states"))
        )

    # Highest-value sources first: active-scene beats, then consequences,
    # threads, recent changes, director activity, world events, NPC state.
    scene_beats_out = _choose_meaningful_recap_lines(scene_beats, limit=5)
    high_value_consequences = consequences if consequences else recent_changes
    consequences_out = _choose_meaningful_recap_lines(high_value_consequences, limit=5)
    threads_out = _choose_meaningful_recap_lines(threads, limit=4)
    director_activity_out = _choose_meaningful_recap_lines(director_log, limit=4)
    world_events_out = _choose_meaningful_recap_lines(world_events, limit=5)
    npc_updates_out = _choose_meaningful_recap_lines(npcs, limit=4)

    # Only backfill higher-value sections. Do NOT restore low-value world/NPC
    # filler after filtering, or the recap regresses to idle noise.
    if not scene_beats_out:
        scene_beats_out = _coerce_recap_labels(scene_beats, limit=5)
    if not consequences_out:
        consequences_out = _coerce_recap_labels(high_value_consequences, limit=5)
    if not threads_out:
        threads_out = _coerce_recap_labels(threads, limit=4)
    if not director_activity_out:
        director_activity_out = _coerce_recap_labels(director_log, limit=4)

    # Prefer scene beats and other higher-value sections over idle/filler event lines.
    if scene_beats_out or consequences_out or threads_out or director_activity_out:
        world_events_out = [
            x for x in world_events_out if _is_meaningful_recap_text(x)
        ]
        npc_updates_out = [
            x for x in npc_updates_out if _is_meaningful_recap_text(x)
        ]
    if scene_beats_out:
        # Keep scene beats in their own section. Do not duplicate them under world events.
        world_events_out = []

    has_sections = bool(
        scene_beats_out or consequences_out or threads_out or director_activity_out or world_events_out or npc_updates_out
    )

    recap = {
        "kind": "world_advance_recap",
        "summary": _build_player_facing_resume_summary(
            scene_title,
            location_name,
            debug_trace.get("advance_ticks", 0),
            has_sections,
        ),
        "additional_moments": int(debug_trace.get("advance_ticks", 0) or 0),
        "scene_beats": scene_beats_out,
        "world_events": world_events_out,
        "consequences": consequences_out,
        "threads": threads_out,
        "npc_updates": npc_updates_out,
        "director_activity": director_activity_out,
    }
    if not _recap_has_meaningful_sections(recap):
        recap["summary"] = _build_player_facing_resume_summary(scene_title, location_name, debug_trace.get("advance_ticks", 0), False)
    return recap


def _recap_has_meaningful_sections(recap: Dict[str, Any]) -> bool:
    recap = _safe_dict(recap)
    return bool(
        _safe_list(recap.get("scene_beats")) or
        _safe_list(recap.get("world_events")) or
        _safe_list(recap.get("consequences")) or
        _safe_list(recap.get("threads")) or
        _safe_list(recap.get("npc_updates")) or
        _safe_list(recap.get("director_activity"))
    )




def _interaction_memory_key(interaction: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    return _safe_str(interaction.get("id")) or "interaction"


def _snapshot_interaction_for_memory(interaction: Dict[str, Any]) -> Dict[str, Any]:
    interaction = _safe_dict(interaction)
    return {
        "id": _safe_str(interaction.get("id")),
        "type": _safe_str(interaction.get("type")),
        "subtype": _safe_str(interaction.get("subtype")),
        "phase": _safe_str(interaction.get("phase")),
        "resolved": bool(interaction.get("resolved")),
        "winner": _safe_str(interaction.get("winner")),
        "participants": [_safe_str(x) for x in _safe_list(interaction.get("participants")) if _safe_str(x)],
        "state": _safe_dict(interaction.get("state")),
    }


def _detect_interaction_changes(prev_interaction: Dict[str, Any], interaction: Dict[str, Any]) -> List[Dict[str, Any]]:
    prev_interaction = _safe_dict(prev_interaction)
    interaction = _safe_dict(interaction)
    prev_state = _safe_dict(prev_interaction.get("state"))
    state = _safe_dict(interaction.get("state"))

    changes: List[Dict[str, Any]] = []
    if not prev_interaction:
        changes.append({"change_type": "started"})

    prev_phase = _safe_str(prev_interaction.get("phase"))
    phase = _safe_str(interaction.get("phase"))
    if phase and phase != prev_phase:
        changes.append({"change_type": "phase_changed", "from": prev_phase, "to": phase})

    prev_momentum = _safe_str(prev_state.get("momentum") or prev_state.get("advantage"))
    momentum = _safe_str(state.get("momentum") or state.get("advantage"))
    if momentum and momentum != prev_momentum:
        changes.append({"change_type": "momentum_shift", "from": prev_momentum, "to": momentum})

    prev_player_progress = _safe_int(prev_state.get("player_progress"), 0)
    player_progress = _safe_int(state.get("player_progress"), 0)
    if player_progress > prev_player_progress + 1:
        changes.append({
            "change_type": "player_progress",
            "delta": player_progress - prev_player_progress,
        })

    prev_opponent_progress = _safe_int(
        prev_state.get("opponent_progress", prev_state.get("npc_progress")),
        0,
    )
    opponent_progress = _safe_int(
        state.get("opponent_progress", state.get("npc_progress")),
        0,
    )
    if opponent_progress > prev_opponent_progress + 1:
        changes.append({
            "change_type": "opponent_progress",
            "delta": opponent_progress - prev_opponent_progress,
        })

    prev_tone = _safe_str(prev_state.get("tone"))
    tone = _safe_str(state.get("tone"))
    if tone and tone != prev_tone:
        changes.append({"change_type": "tone_changed", "from": prev_tone, "to": tone})

    prev_clue = bool(prev_state.get("clue_found"))
    clue = bool(state.get("clue_found"))
    if clue and not prev_clue:
        changes.append({"change_type": "clue_found"})

    prev_resolved = bool(prev_interaction.get("resolved"))
    resolved = bool(interaction.get("resolved"))
    if resolved and not prev_resolved:
        changes.append({"change_type": "resolved", "winner": _safe_str(interaction.get("winner"))})

    return changes


def _format_generic_interaction_beat(interaction: Dict[str, Any], change: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    change = _safe_dict(change)
    name = _safe_str(interaction.get("display_name")) or "your opponent"
    subtype = _safe_str(interaction.get("subtype")) or _safe_str(interaction.get("type")) or "interaction"
    change_type = _safe_str(change.get("change_type"))

    if change_type == "started":
        return f"A {subtype.replace('_', ' ')} involving {name} begins."
    if change_type == "phase_changed":
        to_phase = _safe_str(change.get("to")).replace("_", " ")
        return f"The {subtype.replace('_', ' ')} with {name} shifts into a {to_phase} phase."
    if change_type == "momentum_shift":
        to_side = _safe_str(change.get("to"))
        if to_side == "player":
            return f"You gain the upper hand against {name}."
        return f"{name} gains the upper hand."
    if change_type == "player_progress":
        return f"You make visible progress against {name}."
    if change_type == "opponent_progress":
        return f"{name} pushes back and makes progress."
    if change_type == "tone_changed":
        tone = _safe_str(change.get("to")).replace("_", " ")
        return f"The exchange with {name} turns more {tone}."
    if change_type == "clue_found":
        return f"A useful clue emerges during the exchange with {name}."
    if change_type == "resolved":
        winner = _safe_str(change.get("winner"))
        if winner == "player":
            return f"The exchange with {name} ends in your favor."
        if winner:
            return f"{name} comes out ahead as the exchange concludes."
        return f"The exchange with {name} comes to an end."
    return ""


def _format_arm_wrestling_beat(interaction: Dict[str, Any], change: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    change = _safe_dict(change)
    name = _safe_str(interaction.get("display_name")) or "your opponent"
    change_type = _safe_str(change.get("change_type"))

    if change_type == "started":
        return f"You and {name} lock hands as the arm-wrestling match begins."
    if change_type == "momentum_shift":
        to_side = _safe_str(change.get("to"))
        if to_side == "player":
            return f"{name} starts losing leverage as you force the match your way."
        return f"{name} surges forward, straining to overpower you."
    if change_type == "player_progress":
        return f"{name} struggles to stop your push as the table creaks under the strain."
    if change_type == "opponent_progress":
        return f"{name} digs in and drives your arm back toward the center."
    if change_type == "resolved":
        winner = _safe_str(change.get("winner"))
        if winner == "player":
            return f"{name}'s resistance breaks and the match ends in your favor."
        if winner:
            return f"{name} wins the match after a final burst of strength."
        return f"The arm-wrestling match between you and {name} comes to an end."
    return _format_generic_interaction_beat(interaction, change)


def _format_interaction_beat(interaction: Dict[str, Any], change: Dict[str, Any]) -> str:
    interaction = _safe_dict(interaction)
    interaction_type = _safe_str(interaction.get("type"))
    interaction_subtype = _safe_str(interaction.get("subtype"))

    if interaction_subtype == "arm_wrestling" or interaction_type == "arm_wrestling":
        return _format_arm_wrestling_beat(interaction, change)
    return _format_generic_interaction_beat(interaction, change)


def _emit_scene_beats_from_active_interactions(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_ambient_runtime_state(_safe_dict(runtime_state))

    interactions = _normalize_active_interactions(simulation_state, runtime_state)
    prev_memory = _safe_dict(runtime_state.get("scene_beat_memory"))
    next_memory: Dict[str, Any] = {}
    tick = _safe_int(runtime_state.get("tick", 0), 0)

    for interaction in interactions:
        # Skip resolved interactions — no new beats should be emitted for them.
        if _safe_bool(interaction.get("resolved"), False):
            continue
        key = _interaction_memory_key(interaction)
        prev_interaction = _safe_dict(prev_memory.get(key))
        changes = _detect_interaction_changes(prev_interaction, interaction)

        for idx, change in enumerate(changes):
            summary = _format_interaction_beat(interaction, change)
            if not _safe_str(summary):
                continue
            runtime_state = emit_scene_beat(
                runtime_state,
                tick=tick,
                summary=summary,
                kind="interaction_beat",
                priority=95 - idx,
                scene_id=_safe_str(interaction.get("scene_id")),
                interaction_id=_safe_str(interaction.get("id")),
                actors=[_safe_str(x) for x in _safe_list(interaction.get("participants")) if _safe_str(x)],
                location_id=_safe_str(interaction.get("location_id")),
                recap_level="major" if _safe_str(change.get("change_type")) == "resolved" else "notable",
                tags=["scene", "interaction", _safe_str(interaction.get("type")), _safe_str(interaction.get("subtype"))],
            )

        next_memory[key] = _snapshot_interaction_for_memory(interaction)

    runtime_state["scene_beat_memory"] = next_memory
    return runtime_state


def ensure_ambient_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    runtime_state.setdefault("ambient_queue", [])
    runtime_state.setdefault("ambient_history", [])
    runtime_state.setdefault("director_log", [])
    runtime_state.setdefault("scene_beat_memory", {})
    runtime_state.setdefault("recent_scene_beats", [])
    runtime_state["ambient_queue"] = _safe_list(runtime_state.get("ambient_queue"))[-_MAX_AMBIENT_UPDATES:]
    runtime_state["ambient_history"] = _safe_list(runtime_state.get("ambient_history"))[-_MAX_AMBIENT_UPDATES:]
    runtime_state["director_log"] = _safe_list(runtime_state.get("director_log"))[-_MAX_DIRECTOR_LOG:]
    runtime_state["scene_beat_memory"] = _safe_dict(runtime_state.get("scene_beat_memory"))
    runtime_state = _ensure_recent_scene_beats(runtime_state)
    return runtime_state


def _stable_unique_strs(values: List[Any]) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in values:
        value = _safe_str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _normalize_prompt_location_name(value: str, grounded_fallback: str) -> str:
    value = _safe_str(value).strip()
    if not value:
        return grounded_fallback
    if value.startswith("scene:tick:"):
        return grounded_fallback
    return value


def _resolve_location_name(
    simulation_state: Dict[str, Any],
    location_id: str,
    fallback_name: str = "",
) -> str:
    simulation_state = _safe_dict(simulation_state)
    location_id = _safe_str(location_id).strip()
    if not location_id:
        return _safe_str(fallback_name).strip()

    # Normalize location id (handle both colon and underscore formats)
    normalized_id = location_id.replace(":", "_").replace("-", "_").lower()

    # Modern format: locations is object dict keyed by location_id
    locations_map = _safe_dict(simulation_state.get("locations"))
    for key in locations_map:
        key_normalized = key.replace(":", "_").replace("-", "_").lower()
        if key_normalized == normalized_id:
            loc = _safe_dict(locations_map[key])
            return _safe_str(loc.get("name") or loc.get("title") or fallback_name or location_id)

    # Legacy format: locations is list
    for loc in _safe_list(simulation_state.get("locations")):
        loc = _safe_dict(loc)
        loc_id = _safe_str(loc.get("location_id") or loc.get("id")).replace(":", "_").replace("-", "_").lower()
        if loc_id == normalized_id:
            return _safe_str(loc.get("name") or loc.get("title") or fallback_name or location_id)

    final_fallback = _safe_str(fallback_name).strip() or location_id
    return final_fallback if final_fallback else "Current Location"


def _resolve_actor_names(simulation_state: Dict[str, Any], actor_ids: List[str]) -> List[str]:
    simulation_state = _safe_dict(simulation_state)
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    names: List[str] = []
    for actor_id in _stable_unique_strs(actor_ids):
        npc = _safe_dict(npc_index.get(actor_id))
        names.append(_safe_str(npc.get("name") or actor_id))
    return names


def _derive_grounded_scene_context(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    turn_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    turn_result = _safe_dict(turn_result)

    opening_text = _safe_str(runtime_state.get("opening"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    player_state = _safe_dict(simulation_state.get("player_state"))

    player_loc_id = _safe_str(player_state.get("location_id")).strip()
    nearby_ids = _safe_list(player_state.get("nearby_npc_ids"))
    present_scene_ids = _safe_list(current_scene.get("present_npc_ids"))
    actor_objs = _safe_list(current_scene.get("actors"))
    actor_obj_ids = [
        _safe_str(_safe_dict(a).get("id") or _safe_dict(a).get("npc_id") or _safe_dict(a).get("name"))
        for a in actor_objs
    ]

    location_id = (
        player_loc_id
        or _safe_str(current_scene.get("location_id"))
        or _safe_str(turn_result.get("location_id"))
    ).strip()
    location_name = _resolve_location_name(
        simulation_state,
        location_id,
        _safe_str(current_scene.get("location_name")).strip(),
    )

    present_actor_ids = _stable_unique_strs(nearby_ids + present_scene_ids + actor_obj_ids)
    present_actor_names = _resolve_actor_names(simulation_state, present_actor_ids)

    scene_title = (
        _safe_str(current_scene.get("title")).strip()
        or _safe_str(current_scene.get("scene_title")).strip()
        or location_name
        or "Current Scene"
    )
    scene_summary = (
        _safe_str(current_scene.get("summary")).strip()
        or _safe_str(current_scene.get("scene")).strip()
        or opening_text.strip()
        or "Your adventure continues."
    )

    return {
        "scene_title": scene_title,
        "location_id": location_id,
        "location_name": location_name or "Current Location",
        "scene_summary": scene_summary,
        "present_actor_ids": present_actor_ids,
        "present_actor_names": present_actor_names,
    }


def _apply_grounded_scene_overlay(scene: Dict[str, Any], grounded: Dict[str, Any]) -> Dict[str, Any]:
    scene = _copy_dict(_safe_dict(scene))
    grounded = _safe_dict(grounded)

    scene["title"] = _safe_str(scene.get("title")).strip() or _safe_str(grounded.get("scene_title")) or "Current Scene"
    scene["location_id"] = _safe_str(scene.get("location_id")).strip() or _safe_str(grounded.get("location_id"))
    scene["location_name"] = _safe_str(scene.get("location_name")).strip() or _safe_str(grounded.get("location_name")) or "Current Location"
    scene["summary"] = _safe_str(scene.get("summary")).strip() or _safe_str(grounded.get("scene_summary")) or "Your adventure continues."

    actor_names = _safe_list(grounded.get("present_actor_names"))
    if actor_names:
        scene["actors"] = actor_names

    present_ids = _safe_list(grounded.get("present_actor_ids"))
    if present_ids and not _safe_list(scene.get("present_npc_ids")):
        scene["present_npc_ids"] = present_ids

    return scene


def _ensure_scene_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    return ensure_persistent_scene_runtime_state(runtime_state)


def _filter_salient_player_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only player-meaningful events for idle initiative context."""
    result: List[Dict[str, Any]] = []
    for evt in _safe_list(events):
        evt = _safe_dict(evt)
        text = " ".join(
            [
                _safe_str(evt.get("type")),
                _safe_str(evt.get("event_type")),
                _safe_str(evt.get("description")),
                _safe_str(evt.get("summary")),
                _safe_str(evt.get("text")),
                _safe_str(evt.get("goal")),
                _safe_str(evt.get("label")),
            ]
        ).lower()
        if any(
            p in text
            for p in (
                "maintain awareness",
                "awareness of player",
                "baseline",
                "loyalty baseline",
                "faction loyalty baseline",
                "goal maintenance",
                "state driver",
            )
        ):
            continue
        result.append(evt)
    return result[-4:]


# ── Phase F — effective world behavior config ─────────────────────────────


def get_effective_world_behavior(session: Dict[str, Any]) -> Dict[str, Any]:
    """Merge setup world_behavior with runtime override.

    The setup config provides adventure-level defaults.
    The runtime override lets the player tune mid-game.
    """
    session = _safe_dict(session)
    setup = _safe_dict(session.get("setup_payload"))
    runtime = _safe_dict(session.get("runtime_state"))

    base = normalize_world_behavior_config(_safe_dict(setup.get("world_behavior")))
    override = _safe_dict(runtime.get("world_behavior_override"))

    effective = dict(base)
    from app.rpg.creator.schema import _WORLD_BEHAVIOR_ENUMS
    for key, allowed in _WORLD_BEHAVIOR_ENUMS.items():
        val = override.get(key)
        if isinstance(val, str) and val.strip().lower() in allowed:
            effective[key] = val.strip().lower()

    return effective


# ── Phase 1 — idle tick cadence policy ────────────────────────────────────




# ── Phase 5 — opening-aware runtime metadata ─────────────────────────────


def _build_opening_runtime(setup: Dict[str, Any]) -> Dict[str, Any]:
    """Build opening-aware runtime metadata from setup payload.

    Persisted as runtime_state["opening_runtime"].
    """
    setup = _safe_dict(setup)
    opening = _safe_dict(setup.get("opening"))

    if not opening:
        return {"active": False, "opening_resolved": True}

    return {
        "active": True,
        "scene_frame": _safe_str(opening.get("scene_frame")),
        "immediate_problem": _safe_str(opening.get("immediate_problem")),
        "player_involvement_reason": _safe_str(opening.get("player_involvement_reason")),
        "starter_conflict": _safe_str(setup.get("starter_conflict")),
        "present_npc_ids": _safe_list(opening.get("present_npc_ids")),
        "first_choices": _safe_list(opening.get("first_choices")),
        "opening_resolved": False,
    }

__all__ = [name for name in globals() if not name.startswith("__")]
