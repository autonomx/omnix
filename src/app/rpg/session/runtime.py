"""Canonical RPG session runtime.

Single source of truth for:
- building a persisted session from adventure-builder startup
- loading/saving canonical sessions
- executing player turns against canonical session state
- shaping turn/bootstrap payloads for the frontend

This replaces the legacy in-memory GameSession / pipeline.py / routes.py flow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.rpg.ai.world_scene_narrator import play_scene as narrate_scene
from app.rpg.creator.defaults import apply_adventure_defaults
from app.rpg.creator.world_player_actions import (
    ESCALATE_CONFLICT,
    INTERVENE_THREAD,
    SUPPORT_FACTION,
    apply_player_action,
)
from app.rpg.creator.world_scene_generator import generate_scenes_from_simulation
from app.rpg.creator.world_simulation import (
    build_initial_simulation_state,
    step_simulation_state,
    summarize_simulation_step,
)
from app.rpg.memory.actor_memory_state import ensure_actor_memory_state
from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)
from app.rpg.memory.memory_state import ensure_memory_state
from app.rpg.memory.world_memory_state import ensure_world_memory_state
from app.rpg.player import ensure_player_party, ensure_player_state
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.presentation import (
    build_runtime_presentation_payload,
    build_scene_presentation_payload,
)
from app.rpg.presentation.personality_state import ensure_personality_state
from app.rpg.presentation.visual_state import ensure_visual_state
from app.rpg.session.service import load_session as load_canonical_session
from app.rpg.session.service import save_session as save_canonical_session

_SCHEMA_VERSION = 2
_MAX_HISTORY = 64


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_dict(value: Any) -> Dict[str, Any]:
    return dict(_safe_dict(value))


def _build_opening_text(generated: Dict[str, Any]) -> str:
    opening_situation = _safe_dict(generated.get("opening_situation"))
    parts: List[str] = []
    summary = _safe_str(opening_situation.get("summary")).strip()
    location = _safe_str(opening_situation.get("location")).strip()
    present_actors = [str(v) for v in _safe_list(opening_situation.get("present_actors")) if str(v).strip()]
    if summary:
        parts.append(summary)
    if location:
        parts.append(f"You find yourself in {location}.")
    if present_actors:
        parts.append(f"Present: {', '.join(present_actors)}.")
    return " ".join(parts).strip() or "Your adventure begins…"


def _build_world_payload(setup: Dict[str, Any], generated: Dict[str, Any], canon_summary: Dict[str, Any]) -> Dict[str, Any]:
    world_frame = _safe_dict(generated.get("world_frame"))
    return {
        "title": _safe_str(setup.get("title") or world_frame.get("title")),
        "genre": _safe_str(setup.get("genre")),
        "setting": _safe_str(setup.get("setting")),
        "premise": _safe_str(setup.get("premise")),
        "summary": _safe_str(canon_summary.get("summary")),
    }


def _build_npc_cards(generated: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for npc in _safe_list(generated.get("seed_npcs")):
        npc = _safe_dict(npc)
        if not npc:
            continue
        cards.append({
            "id": _safe_str(npc.get("npc_id")),
            "name": _safe_str(npc.get("name") or "Unknown"),
            "role": _safe_str(npc.get("role")),
            "description": _safe_str(npc.get("description")),
            "faction_id": npc.get("faction_id"),
            "location_id": npc.get("location_id"),
        })
    return cards


def _ensure_simulation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _copy_dict(simulation_state)
    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    return simulation_state


def _initial_scene_state(generated: Dict[str, Any]) -> Dict[str, Any]:
    opening = _safe_dict(generated.get("opening_situation"))
    anchor = _safe_dict(generated.get("initial_scene_anchor"))
    scene_id = _safe_str(anchor.get("scene_id") or anchor.get("anchor_id") or "scene:opening")
    location_id = _safe_str(anchor.get("location_id") or opening.get("location_id"))
    location_name = _safe_str(anchor.get("location_name") or opening.get("location"))
    body = _safe_str(anchor.get("summary") or opening.get("summary"))
    present_actors = _safe_list(opening.get("present_actors"))
    return {
        "scene_id": scene_id,
        "scene": body or "Your adventure begins…",
        "summary": body or "Your adventure begins…",
        "location_id": location_id,
        "location_name": location_name,
        "actors": [{"id": _safe_str(name), "name": _safe_str(name)} for name in present_actors if _safe_str(name)],
        "options": [],
        "meta": {"origin": "adventure_start"},
        "metadata": {"origin": "adventure_start"},
    }


def build_session_from_start_result(setup_payload: Dict[str, Any], start_result: Dict[str, Any]) -> Dict[str, Any]:
    setup = apply_adventure_defaults(dict(setup_payload or {}))
    generated = _safe_dict(start_result.get("generated"))
    canon_summary = _safe_dict(start_result.get("canon_summary"))
    setup_id = _safe_str(setup.get("setup_id")).strip() or f"adventure_{_utc_now_iso()}"
    now = _utc_now_iso()

    metadata = _safe_dict(setup.get("metadata"))
    simulation_state = _safe_dict(metadata.get("simulation_state"))
    if not simulation_state:
        simulation_state = build_initial_simulation_state(setup)
        metadata["simulation_state"] = simulation_state
        setup["metadata"] = metadata

    simulation_state = _ensure_simulation_state(simulation_state)
    world = _build_world_payload(setup, generated, canon_summary)
    npcs = _build_npc_cards(generated)
    opening = _build_opening_text(generated)
    current_scene = _initial_scene_state(generated)

    session = {
        "manifest": {
            "id": setup_id,
            "schema_version": _SCHEMA_VERSION,
            "title": _safe_str(setup.get("title") or world.get("title") or "Untitled Adventure"),
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "source_pack_id": "",
            "source_template_id": _safe_str(metadata.get("template_name")),
        },
        "setup_payload": setup,
        "simulation_state": simulation_state,
        "runtime_state": {
            "tick": int(simulation_state.get("tick", 0) or 0),
            "opening": opening,
            "world": world,
            "npcs": npcs,
            "current_scene": current_scene,
            "last_turn_result": {},
            "turn_history": [],
            "voice_assignments": {},
        },
    }
    return session


def build_frontend_bootstrap_payload(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    simulation_state = _safe_dict(session.get("simulation_state"))
    world = _safe_dict(runtime_state.get("world"))
    npcs = _safe_list(runtime_state.get("npcs"))
    opening = _safe_str(runtime_state.get("opening"))
    turn_result = _safe_dict(runtime_state.get("last_turn_result"))

    return {
        "success": True,
        "session_id": _safe_str(manifest.get("id")),
        "title": _safe_str(manifest.get("title")),
        "opening": opening,
        "world": world,
        "player": _safe_dict(simulation_state.get("player_state")),
        "npcs": npcs,
        "memory": _safe_list(_safe_dict(simulation_state.get("memory_state")).get("short_term")),
        "worldEvents": _safe_list(simulation_state.get("events"))[-8:],
        "world_events": _safe_list(simulation_state.get("events"))[-8:],
        "presentation": build_runtime_presentation_payload(simulation_state),
        "scene": _safe_dict(runtime_state.get("current_scene")),
        "voice_assignments": _safe_dict(runtime_state.get("voice_assignments")),
        "last_turn_result": turn_result,
    }


def _find_target_by_name(bucket: Dict[str, Any], text: str) -> str:
    text_lc = text.lower()
    for entity_id, entity in sorted(bucket.items()):
        entity = _safe_dict(entity)
        candidates = [
            _safe_str(entity_id),
            _safe_str(entity.get("name")),
            _safe_str(entity.get("title")),
            _safe_str(entity.get("summary")),
        ]
        for candidate in candidates:
            candidate = candidate.strip().lower()
            if candidate and candidate in text_lc:
                return _safe_str(entity_id)
    return ""


def derive_player_action(simulation_state: Dict[str, Any], player_input: str) -> Dict[str, Any]:
    text = _safe_str(player_input).strip()
    text_lc = text.lower()
    threads = _safe_dict(simulation_state.get("threads"))
    factions = _safe_dict(simulation_state.get("factions"))

    if not text:
        return {}

    if any(token in text_lc for token in ("help", "intervene", "stop", "de-escalate", "defuse")):
        target_id = _find_target_by_name(threads, text)
        if target_id:
            return {
                "type": INTERVENE_THREAD,
                "target_id": target_id,
                "action_id": f"action:{int(simulation_state.get('tick', 0) or 0)}:{target_id}:intervene",
            }

    if any(token in text_lc for token in ("support", "aid", "ally with", "back ")) or text_lc.startswith("support "):
        target_id = _find_target_by_name(factions, text)
        if target_id:
            return {
                "type": SUPPORT_FACTION,
                "target_id": target_id,
                "action_id": f"action:{int(simulation_state.get('tick', 0) or 0)}:{target_id}:support",
            }

    if any(token in text_lc for token in ("attack", "escalate", "strike", "provoke")):
        target_id = _find_target_by_name(threads, text)
        if target_id:
            return {
                "type": ESCALATE_CONFLICT,
                "target_id": target_id,
                "action_id": f"action:{int(simulation_state.get('tick', 0) or 0)}:{target_id}:escalate",
            }

    return {}


def _fallback_scene(simulation_state: Dict[str, Any], player_input: str) -> Dict[str, Any]:
    return {
        "scene_id": f"scene:tick:{int(simulation_state.get('tick', 0) or 0)}",
        "scene": f"You act: {player_input}",
        "summary": f"You act: {player_input}",
        "location_id": _safe_str(_safe_dict(simulation_state.get("player_state")).get("location_id")),
        "actors": [],
        "options": [],
        "meta": {"origin": "fallback"},
        "metadata": {"origin": "fallback"},
    }


def _build_turn_payload(session: Dict[str, Any], narration_result: Dict[str, Any], summary: List[str]) -> Dict[str, Any]:
    session = _safe_dict(session)
    simulation_state = _safe_dict(session.get("simulation_state"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    memory_context = build_dialogue_memory_context(
        simulation_state,
        actor_id="player",
    )
    return {
        "success": True,
        "session_id": _safe_str(_safe_dict(session.get("manifest")).get("id")),
        "narration": _safe_str(narration_result.get("narrative") or current_scene.get("summary")),
        "choices": _safe_list(narration_result.get("choices")),
        "npcs": _safe_list(runtime_state.get("npcs")),
        "player": _safe_dict(simulation_state.get("player_state")),
        "memory": _safe_list(memory_context.get("items")),
        "worldEvents": _safe_list(simulation_state.get("events"))[-8:],
        "world_events": _safe_list(simulation_state.get("events"))[-8:],
        "summary": summary[:8],
        "scene": current_scene,
        "scene_presentation": build_scene_presentation_payload(simulation_state, current_scene),
        "presentation": build_runtime_presentation_payload(simulation_state),
        "dialogue_memory_context": memory_context,
        "llm_memory_prompt_block": build_llm_memory_prompt_block(memory_context),
        "voice_assignments": _safe_dict(runtime_state.get("voice_assignments")),
        "npc_reactions": _safe_list(narration_result.get("npc_reactions")),
        "dialogue_blocks": _safe_list(narration_result.get("dialogue_blocks")),
        "metadata": _safe_dict(narration_result.get("metadata")),
        "turn": int(runtime_state.get("tick", 0) or 0),
    }


def load_runtime_session(session_id: str) -> Dict[str, Any] | None:
    if not session_id:
        return None
    return load_canonical_session(session_id)


def save_runtime_session(session: Dict[str, Any]) -> Dict[str, Any]:
    return save_canonical_session(session)


def apply_turn(session_id: str, player_input: str, action: Dict[str, Any] | None = None) -> Dict[str, Any]:
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    session = _copy_dict(session)
    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _copy_dict(session.get("runtime_state"))
    setup = apply_adventure_defaults(_copy_dict(session.get("setup_payload")))
    simulation_state = _ensure_simulation_state(_safe_dict(session.get("simulation_state")))

    action = _safe_dict(action)
    if not action:
        action = derive_player_action(simulation_state, player_input)

    metadata = _safe_dict(setup.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup["metadata"] = metadata

    if action:
        applied_state = apply_player_action(simulation_state, action)
        metadata["simulation_state"] = applied_state
        setup["metadata"] = metadata

    step_result = step_simulation_state(setup)
    next_setup = _safe_dict(step_result.get("next_setup"))
    after_state = _ensure_simulation_state(_safe_dict(step_result.get("after_state")))
    scenes = generate_scenes_from_simulation(after_state)
    current_scene = _safe_dict(scenes[0]) if scenes else _fallback_scene(after_state, player_input)

    llm_gateway = build_app_llm_gateway()

    narration_result = narrate_scene(
        current_scene,
        {"simulation_state": after_state, "player_input": player_input},
        llm_gateway=llm_gateway,
        tone="dramatic",
    )
    summary = summarize_simulation_step(step_result)

    runtime_state["tick"] = int(after_state.get("tick", runtime_state.get("tick", 0)) or 0)
    runtime_state["current_scene"] = current_scene
    runtime_state["last_turn_result"] = {
        "player_input": player_input,
        "action": action,
        "summary": summary[:8],
        "narration": _safe_str(narration_result.get("narrative")),
        "llm_live": bool(llm_gateway),
        "llm_attempted": bool(llm_gateway),
    }
    turn_history = _safe_list(runtime_state.get("turn_history"))
    turn_history.append(_copy_dict(runtime_state["last_turn_result"]))
    runtime_state["turn_history"] = turn_history[-_MAX_HISTORY:]

    session["setup_payload"] = next_setup or setup
    session["simulation_state"] = after_state
    session["runtime_state"] = runtime_state
    manifest["updated_at"] = _utc_now_iso()
    session["manifest"] = manifest
    session = save_runtime_session(session)

    return {
        "ok": True,
        "session": session,
        "payload": _build_turn_payload(session, narration_result, summary),
    }