from __future__ import annotations

from typing import Any, Dict

from app.rpg.lore.transitions import apply_lore_transition
from app.rpg.memory.observation import record_event_observations
from app.rpg.puzzles.transitions import apply_puzzle_transition
from app.rpg.quests.transitions import apply_quest_transition
from app.rpg.social.reputation import apply_social_deltas
from app.rpg.story_arcs.state import (
    apply_story_arc_pressure_delta,
    set_story_arc_flag,
    set_story_arc_stage,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ensure_world_event_log(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = simulation_state.setdefault("world_event_state", {})
    if not isinstance(state, dict):
        state = {}
        simulation_state["world_event_state"] = state
    state.setdefault("version", 1)
    state.setdefault("events", [])
    return state


def _emit_world_event(
    simulation_state: Dict[str, Any],
    effect: Dict[str, Any],
    *,
    source_event: Dict[str, Any],
    turn_index: int,
) -> Dict[str, Any]:
    state = _ensure_world_event_log(simulation_state)
    row = {
        "event_id": str(effect.get("world_event_id") or f"world:{source_event.get('event_id')}"),
        "source_story_event_id": source_event.get("event_id"),
        "kind": str(effect.get("kind") or source_event.get("kind") or "story_event"),
        "summary": str(effect.get("summary") or source_event.get("summary") or ""),
        "location_id": str(effect.get("location_id") or source_event.get("location_id") or ""),
        "turn_index": int(turn_index or 0),
        "tags": list(effect.get("tags") or source_event.get("tags") or [])[:20],
    }
    if not any(existing.get("event_id") == row["event_id"] for existing in state["events"] if isinstance(existing, dict)):
        state["events"].append(row)
    state["events"] = state["events"][-200:]
    return {"ok": True, "kind": "world_event_emit", "world_event": row}


def apply_story_event_effect(
    simulation_state: Dict[str, Any],
    effect: Dict[str, Any],
    *,
    source_event: Dict[str, Any],
    turn_index: int = 0,
) -> Dict[str, Any]:
    effect = _safe_dict(effect)
    effect_type = str(effect.get("type") or "")

    if effect_type == "arc_pressure_delta":
        return dict(
            apply_story_arc_pressure_delta(
                simulation_state,
                str(effect.get("arc_id") or source_event.get("arc_id") or ""),
                int(effect.get("delta") or 0),
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "arc_stage_set":
        return dict(
            set_story_arc_stage(
                simulation_state,
                str(effect.get("arc_id") or source_event.get("arc_id") or ""),
                str(effect.get("stage") or ""),
                status=effect.get("status"),
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "arc_flag_set":
        return dict(
            set_story_arc_flag(
                simulation_state,
                str(effect.get("arc_id") or source_event.get("arc_id") or ""),
                str(effect.get("flag") or ""),
                effect.get("value", True),
            ),
            effect_type=effect_type,
        )

    if effect_type == "lore_reveal":
        return dict(
            apply_lore_transition(
                simulation_state,
                {
                    "action": "reveal_to_player",
                    "lore_id": str(effect.get("lore_id") or ""),
                },
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "lore_truth_status_set":
        return dict(
            apply_lore_transition(
                simulation_state,
                {
                    "action": "set_truth_status",
                    "lore_id": str(effect.get("lore_id") or ""),
                    "truth_status": str(effect.get("truth_status") or ""),
                },
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "lore_known_by_add":
        return dict(
            apply_lore_transition(
                simulation_state,
                {
                    "action": "add_known_by",
                    "lore_id": str(effect.get("lore_id") or ""),
                    "entity_id": str(effect.get("entity_id") or ""),
                },
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "lore_tag_add":
        return dict(
            apply_lore_transition(
                simulation_state,
                {
                    "action": "add_tag",
                    "lore_id": str(effect.get("lore_id") or ""),
                    "tag": str(effect.get("tag") or ""),
                },
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "quest_transition":
        return dict(
            apply_quest_transition(
                simulation_state,
                _safe_dict(effect.get("transition")),
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "puzzle_transition":
        return dict(
            apply_puzzle_transition(
                simulation_state,
                _safe_dict(effect.get("transition")),
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "memory_event":
        event = dict(source_event)
        event.update(_safe_dict(effect.get("event")))
        return dict(
            record_event_observations(
                simulation_state,
                event,
                observer_entity_ids=effect.get("observer_entity_ids"),
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    if effect_type == "social_delta":
        deltas = {
            key: int(effect.get(key) or 0)
            for key in ("trust", "fear", "respect", "hostility", "reputation")
            if key in effect
        }
        if effect.get("last_stance"):
            deltas["last_stance"] = effect.get("last_stance")
        return dict(
            apply_social_deltas(
                simulation_state,
                str(effect.get("npc_id") or ""),
                deltas,
                actor_id=str(effect.get("actor_id") or "player"),
            ),
            effect_type=effect_type,
        )

    if effect_type == "world_event_emit":
        return dict(
            _emit_world_event(
                simulation_state,
                effect,
                source_event=source_event,
                turn_index=turn_index,
            ),
            effect_type=effect_type,
        )

    return {
        "ok": False,
        "effect_type": effect_type,
        "reason": f"unknown_effect_type:{effect_type}",
    }