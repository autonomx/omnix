"""Canonical RPG session runtime.

Single source of truth for:
- building a persisted session from adventure-builder startup
- loading/saving canonical sessions
- executing player turns against canonical session state
- shaping turn/bootstrap payloads for the frontend

This replaces the legacy in-memory GameSession / pipeline.py / routes.py flow.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from app.rpg.action_resolver import resolve_player_action
from app.rpg.ai.world_scene_narrator import narrate_scene
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
from app.rpg.session.ambient_builder import (
    _MAX_IDLE_TICKS_PER_REQUEST,
    _MAX_RESUME_CATCHUP_TICKS,
    build_ambient_updates,
    coalesce_ambient_updates,
    enqueue_ambient_updates,
    ensure_ambient_runtime_state,
    get_pending_ambient_updates,
    is_player_visible_update,
    normalize_ambient_state,
    score_ambient_salience,
)
from app.rpg.items.inventory_state import (
    add_inventory_items,
    equip_inventory_item,
    get_inventory_item_for_drop,
    remove_inventory_item,
    unequip_inventory_slot,
)
from app.rpg.items.item_effects import apply_item_use
from app.rpg.items.world_items import (
    drop_world_item,
    ensure_world_item_state,
    list_scene_items,
    pickup_world_item,
)
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.ai.action_intelligence import get_action_advisory, merge_action_advisory
from app.rpg.memory.actor_memory_state import ensure_actor_memory_state
from app.rpg.memory.dialogue_context import (
    build_dialogue_memory_context,
    build_llm_memory_prompt_block,
)
from app.rpg.memory.memory_state import ensure_memory_state
from app.rpg.memory.world_memory_state import ensure_world_memory_state
from app.rpg.player import ensure_player_party, ensure_player_state
from app.rpg.player.player_progression_state import (
    award_player_xp,
    award_skill_xp,
    ensure_player_progression_state,
    resolve_level_ups,
    resolve_skill_level_ups,
)
from app.rpg.player.player_xp_rules import (
    compute_action_player_xp,
    compute_action_skill_xp,
    compute_stat_influence_bonus,
)
from app.rpg.presentation import (
    build_runtime_presentation_payload,
    build_scene_presentation_payload,
)
from app.rpg.presentation.memory_inspector import build_memory_ui_summary
from app.rpg.presentation.personality_state import ensure_personality_state
from app.rpg.presentation.speaker_cards import build_nearby_npc_cards
from app.rpg.presentation.visual_state import ensure_visual_state
from app.rpg.session.service import load_session as load_canonical_session
from app.rpg.session.service import save_session as save_canonical_session

_SCHEMA_VERSION = 4
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


def _get_player_location_id(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> str:
    player_state = _safe_dict(simulation_state.get("player_state"))
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    return (
        _safe_str(player_state.get("location_id")).strip()
        or _safe_str(current_scene.get("location_id")).strip()
        or _safe_str(current_scene.get("scene_id")).strip()
    )


def _extract_equipment(player_state: Dict[str, Any]) -> Dict[str, Any]:
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    return _safe_dict(inventory_state.get("equipment"))


def select_primary_action(simulation_state: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    return candidates[0] if candidates else {"action_type": "investigate"}


def _structured_action_prompt(action: Dict[str, Any]) -> str:
    action = _safe_dict(action)
    npc_name = _safe_str(action.get("npc_name")).strip()
    npc_id = _safe_str(action.get("npc_id") or action.get("target_id")).strip()
    label = npc_name or npc_id or "them"
    action_type = _safe_str(action.get("action_type")).strip()
    legacy_action = _safe_str(action.get("action")).strip().lower()

    if legacy_action == "talk" or action_type == "persuade":
        return f"Talk to {label}"
    if legacy_action == "threaten" or action_type == "intimidate":
        return f"Threaten {label}"
    if label and action_type:
        return f"{action_type.replace('_', ' ').title()} {label}"
    if action_type:
        return action_type.replace("_", " ").title()
    return ""


def _normalize_structured_action(action: Any, player_input: str = "") -> Dict[str, Any]:
    normalized = _safe_dict(action)
    if not normalized:
        raw_input = _safe_str(player_input).strip()
        if raw_input.startswith("{") and raw_input.endswith("}"):
            try:
                normalized = _safe_dict(json.loads(raw_input))
            except Exception:
                normalized = {}

    if not normalized:
        return {}

    if normalized.get("action_type"):
        action_type = _safe_str(normalized.get("action_type")).strip().lower()
        if action_type == "talk":
            normalized["action_type"] = "persuade"
        elif action_type == "threaten":
            normalized["action_type"] = "intimidate"
        normalized.setdefault(
            "target_id",
            _safe_str(normalized.get("target_id") or normalized.get("npc_id")).strip(),
        )
        return normalized

    legacy_type = _safe_str(normalized.get("type")).strip().lower()
    legacy_action = _safe_str(normalized.get("action")).strip().lower()
    npc_id = _safe_str(normalized.get("npc_id")).strip()
    npc_name = _safe_str(normalized.get("npc_name")).strip()

    if legacy_type == "npc_action":
        if legacy_action == "talk":
            return {
                "action_type": "persuade",
                "npc_id": npc_id,
                "npc_name": npc_name,
                "target_id": npc_id,
                "interaction": "talk",
                "difficulty": "normal",
            }
        if legacy_action == "threaten":
            return {
                "action_type": "intimidate",
                "npc_id": npc_id,
                "npc_name": npc_name,
                "target_id": npc_id,
                "interaction": "threaten",
                "difficulty": "normal",
            }

    normalized.setdefault("target_id", _safe_str(normalized.get("target_id") or npc_id).strip())
    if normalized.get("type") and not normalized.get("action_type"):
        normalized["action_type"] = _safe_str(normalized.get("type")).strip()
    return normalized


def _ensure_simulation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _copy_dict(simulation_state)
    simulation_state = ensure_player_state(simulation_state)
    simulation_state = ensure_player_party(simulation_state)
    simulation_state = ensure_memory_state(simulation_state)
    simulation_state = ensure_actor_memory_state(simulation_state)
    simulation_state = ensure_world_memory_state(simulation_state)
    simulation_state = ensure_personality_state(simulation_state)
    simulation_state = ensure_visual_state(simulation_state)
    simulation_state = ensure_world_item_state(simulation_state)

    player_state = _safe_dict(simulation_state.get("player_state"))
    player_state = ensure_player_progression_state(player_state)
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state
    return simulation_state


def _pickup_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    instance_id = _safe_str(action.get("instance_id")).strip()
    result = pickup_world_item(simulation_state, instance_id)
    next_state = _safe_dict(result.get("simulation_state"))
    picked_item = _safe_dict(result.get("picked_up_item"))
    if picked_item.get("item_id"):
        player_state = _safe_dict(next_state.get("player_state"))
        inventory_state = _safe_dict(player_state.get("inventory_state"))
        inventory_state = add_inventory_items(inventory_state, [picked_item])
        player_state["inventory_state"] = inventory_state
        next_state["player_state"] = player_state
    return {
        "simulation_state": next_state,
        "result": _safe_dict(result.get("result")),
        "picked_up_item": picked_item,
    }


def _drop_item_action(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    item_id = _safe_str(action.get("item_id")).strip()
    qty = int(action.get("qty", 1) or 1)
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    dropped_item = get_inventory_item_for_drop(inventory_state, item_id)
    inventory_state = remove_inventory_item(inventory_state, item_id, qty=qty)
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state

    location_id = _get_player_location_id(simulation_state, runtime_state)
    drop_payload = dropped_item if dropped_item else {"item_id": item_id, "qty": qty}
    result = drop_world_item(simulation_state, drop_payload, location_id, qty=qty)
    next_state = _safe_dict(result.get("simulation_state"))
    return {
        "simulation_state": next_state,
        "result": _safe_dict(result.get("result")),
    }


def _equip_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    item_id = _safe_str(action.get("item_id")).strip()
    slot = _safe_str(action.get("slot")).strip()
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    inventory_state = equip_inventory_item(inventory_state, item_id, slot)
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state
    return {
        "simulation_state": simulation_state,
        "result": {
            "ok": True,
            "action_type": "equip_item",
            "item_id": item_id,
            "slot": slot or _safe_str(_safe_dict(_extract_equipment(player_state)).get("main_hand")),
            "equipment": _safe_dict(inventory_state.get("equipment")),
        },
    }


def _unequip_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    slot = _safe_str(action.get("slot")).strip()
    player_state = _safe_dict(simulation_state.get("player_state"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    inventory_state = unequip_inventory_slot(inventory_state, slot)
    player_state["inventory_state"] = inventory_state
    simulation_state["player_state"] = player_state
    return {
        "simulation_state": simulation_state,
        "result": {
            "ok": True,
            "action_type": "unequip_item",
            "slot": slot,
            "equipment": _safe_dict(inventory_state.get("equipment")),
        },
    }


def _use_item_action(
    simulation_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    item_id = _safe_str(action.get("item_id")).strip()
    result = apply_item_use(simulation_state, item_id)
    return {
        "simulation_state": _safe_dict(result.get("simulation_state")),
        "result": _safe_dict(result.get("result")),
    }


def _apply_authoritative_action(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    action_type = _safe_str(action.get("action_type")).strip()

    if action_type == "pickup_item":
        return _pickup_item_action(simulation_state, action)
    if action_type == "drop_item":
        return _drop_item_action(simulation_state, runtime_state, action)
    if action_type == "equip_item":
        return _equip_item_action(simulation_state, action)
    if action_type == "unequip_item":
        return _unequip_item_action(simulation_state, action)
    if action_type == "use_item":
        return _use_item_action(simulation_state, action)

    resolved = resolve_player_action(simulation_state, action)
    next_state = _safe_dict(resolved.get("simulation_state")) or simulation_state
    return {
        "simulation_state": next_state,
        "result": _safe_dict(resolved.get("result")),
    }


def _award_progression(
    simulation_state: Dict[str, Any],
    resolved_result: Dict[str, Any],
) -> Dict[str, Any]:
    player_state = _safe_dict(simulation_state.get("player_state"))
    explicit_player_xp = int(_safe_dict(resolved_result.get("xp_result")).get("player_xp", 0) or 0)
    computed_player_xp = int(compute_action_player_xp(resolved_result) or 0)
    action_xp = max(0, explicit_player_xp + computed_player_xp)
    stat_bonus = int(compute_stat_influence_bonus(player_state, resolved_result) or 0) if action_xp > 0 else 0
    total_player_xp = max(0, action_xp + stat_bonus)
    explicit_awards = _safe_dict(_safe_dict(resolved_result.get("skill_xp_result")).get("awards"))
    computed_skill_awards = {}

    if not explicit_awards:
        computed_skill_awards = compute_action_skill_xp(resolved_result)

    skill_xp_awards = dict(explicit_awards)
    for skill_id, amount in computed_skill_awards.items():
        skill_xp_awards[skill_id] = int(skill_xp_awards.get(skill_id, 0) or 0) + int(amount or 0)

    for skill_id, amount in skill_xp_awards.items():
        if int(amount or 0) > 0:
            player_state = award_skill_xp(player_state, skill_id, int(amount), source=_safe_str(resolved_result.get("action_type")))

    player_state = resolve_level_ups(player_state)
    level_ups = list(player_state.pop("_level_ups", []) or [])
    player_state = resolve_skill_level_ups(player_state)
    skill_level_ups = list(player_state.pop("_skill_level_ups", []) or [])

    simulation_state["player_state"] = player_state
    return {
        "simulation_state": simulation_state,
        "xp_result": {
            "player_xp": total_player_xp,
            "base_player_xp": action_xp,
            "explicit_player_xp": explicit_player_xp,
            "computed_player_xp": computed_player_xp,
            "stat_bonus": stat_bonus,
        },
        "skill_xp_result": {
            "awards": skill_xp_awards,
        },
        "level_up": level_ups,
        "skill_level_ups": skill_level_ups,
    }


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
            "settings": {
                "response_length": "short",
            },
            # Living-world ambient state (Phase 0.2)
            "ambient_queue": [],
            "ambient_seq": 0,
            "last_idle_tick_at": "",
            "last_player_turn_at": "",
            "idle_streak": 0,
            "ambient_cooldowns": {},
            "recent_ambient_ids": [],
            "pending_interrupt": None,
            "subscription_state": {"last_polled_seq": 0},
            "ambient_metrics": {"emitted": 0, "suppressed": 0, "coalesced": 0},
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
    player_state = _safe_dict(simulation_state.get("player_state"))

    current_scene = _safe_dict(runtime_state.get("current_scene"))
    narration = _safe_str(turn_result.get("narration")) or opening

    nearby_npcs = build_nearby_npc_cards(simulation_state, current_scene)

    inventory_state = _safe_dict(player_state.get("inventory_state"))
    equipment = _safe_dict(inventory_state.get("equipment"))

    return {
        "success": True,
        "session_id": _safe_str(manifest.get("id")),
        "title": _safe_str(manifest.get("title")),
        "opening": opening,
        "narration": narration,
        "player": {
            "stats": _safe_dict(player_state.get("stats")),
            "skills": _safe_dict(player_state.get("skills")),
            "level": int(player_state.get("level", 1) or 1),
            "xp": int(player_state.get("xp", 0) or 0),
            "xp_to_next": int(player_state.get("xp_to_next", 100) or 100),
            "inventory_state": inventory_state,
            "equipment": equipment,
            "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids")),
            "available_checks": _safe_list(player_state.get("available_checks")),
        },
        "nearby_npcs": nearby_npcs,
        "known_npcs": npcs,
        "scene": {
            "scene_id": _safe_str(current_scene.get("scene_id")),
            "items": _safe_list(current_scene.get("items")),
            "available_checks": _safe_list(current_scene.get("available_checks")),
            "present_npc_ids": _safe_list(current_scene.get("present_npc_ids")),
        },
        "memory_summary": build_memory_ui_summary(simulation_state),
        "combat_result": _safe_dict(turn_result.get("combat_result")),
        "xp_result": _safe_dict(turn_result.get("xp_result")),
        "skill_xp_result": _safe_dict(turn_result.get("skill_xp_result")),
        "level_up": _safe_list(turn_result.get("level_up")),
        "skill_level_ups": _safe_list(turn_result.get("skill_level_ups")),
        "presentation": build_runtime_presentation_payload(simulation_state),
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


def derive_action_candidates(simulation_state, player_input):
    candidates = []
    text = str(player_input.get("text", "") if isinstance(player_input, dict) else player_input).lower()

    # Passive observation: no XP path
    if any(w in text for w in ["look around", "look about", "observe", "glance", "scan", "take in"]):
        candidates.append({"action_type": "observe", "priority": 4})

    # Real investigation: deliberate scrutiny
    if any(w in text for w in ["investigate", "search", "examine", "inspect", "analyze"]):
        candidates.append({"action_type": "investigate", "priority": 6})

    # Unarmed combat
    if any(w in text for w in ["punch", "kick", "headbutt", "slam"]):
        candidates.append({"action_type": "attack_unarmed", "priority": 10})

    # Armed / generic combat
    if any(w in text for w in ["attack", "hit", "strike", "fight", "slash", "stab"]):
        candidates.append({"action_type": "attack_melee", "priority": 9})

    if any(w in text for w in ["shoot", "fire", "aim"]):
        candidates.append({"action_type": "attack_ranged", "priority": 10})

    # Defense
    if any(w in text for w in ["block", "defend", "shield"]):
        candidates.append({"action_type": "block", "priority": 8})
    if any(w in text for w in ["dodge", "evade", "roll"]):
        candidates.append({"action_type": "dodge", "priority": 8})
    # Social
    if any(w in text for w in ["persuade", "convince", "talk", "negotiate"]):
        candidates.append({"action_type": "persuade", "priority": 7})
    if any(w in text for w in ["threaten", "intimidate", "scare"]):
        candidates.append({"action_type": "intimidate", "priority": 7})
    # Stealth
    if any(w in text for w in ["sneak", "hide", "stealth"]):
        candidates.append({"action_type": "sneak", "priority": 6})
    if any(w in text for w in ["hack", "crack", "decrypt"]):
        candidates.append({"action_type": "hack", "priority": 6})
    if any(w in text for w in ["cast", "spell", "magic"]):
        candidates.append({"action_type": "cast_spell", "priority": 7})
    # Items
    if any(w in text for w in ["pick up", "pickup", "grab", "take", "loot"]):
        candidates.append({"action_type": "pickup_item", "priority": 5})
    if any(w in text for w in ["equip", "wear", "wield"]):
        candidates.append({"action_type": "equip_item", "priority": 5})
    if any(w in text for w in ["use", "drink", "eat", "consume"]):
        candidates.append({"action_type": "use_item", "priority": 5})

    if not candidates:
        candidates.append({"action_type": "observe", "priority": 1})

    candidates.sort(key=lambda c: c.get("priority", 0), reverse=True)
    return candidates


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
    # Phase 18.3A — extract player state for XP/progression fields
    player_state = _safe_dict(simulation_state.get("player_state"))
    last_turn = _safe_dict(runtime_state.get("last_turn_result"))
    return {
        "success": True,
        "session_id": _safe_str(_safe_dict(session.get("manifest")).get("id")),
        "narration": _safe_str(narration_result.get("narrative") or current_scene.get("summary")),
        "choices": _safe_list(narration_result.get("choices")),
        "npcs": _safe_list(runtime_state.get("npcs")),
        "player": player_state,
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
        # Phase 18.3A — XP and progression in turn response
        "player_level": int(player_state.get("level", 1) or 1),
        "player_xp": int(player_state.get("xp", 0) or 0),
        "player_skills": _safe_dict(player_state.get("skills")),
        "level_up": bool(last_turn.get("level_up")),
        "skill_level_ups": _safe_list(last_turn.get("skill_level_ups")),
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

    player_input = _safe_str(player_input).strip()
    action = _normalize_structured_action(action, player_input)

    if not action:
        candidates = derive_action_candidates(simulation_state, player_input)
        action = select_primary_action(simulation_state, candidates)

    action = _safe_dict(action)
    action_type = _safe_str(action.get("action_type")).strip()

    if not player_input:
        player_input = _structured_action_prompt(action)
    player_input = player_input or action_type.replace("_", " ").strip() or "Wait"

    llm_gateway = build_app_llm_gateway()
    advisory = {}
    runtime_state.setdefault("llm_records", [])
    runtime_state["llm_records_index"] = _safe_dict(runtime_state.get("llm_records_index"))
    mode = _safe_str(runtime_state.get("mode")).strip().lower() or "live"
    current_tick = int(runtime_state.get("tick", 0) or 0)

    if mode == "live":
        advisory = get_action_advisory(
            llm_gateway=llm_gateway,
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
        runtime_state["llm_records"].append(record)
        runtime_state["llm_records_index"][
            f"action_advisory:{current_tick}"
        ] = record
    else:
        key = f"action_advisory:{current_tick}"
        record = _safe_dict(runtime_state.get("llm_records_index")).get(key)
        if not record:
            raise RuntimeError(f"missing_replay_action_advisory_for_tick:{current_tick}")
        advisory = _safe_dict(record.get("output"))
    if advisory:
        action = merge_action_advisory(action, advisory)
        action_type = _safe_str(action.get("action_type")).strip()

    authoritative = _apply_authoritative_action(simulation_state, runtime_state, action)
    after_action_state = _ensure_simulation_state(_safe_dict(authoritative.get("simulation_state")))
    resolved_result = _safe_dict(authoritative.get("result"))
    resolved_result.setdefault("action_type", action_type)

    progression = _award_progression(after_action_state, resolved_result)
    after_progression_state = _ensure_simulation_state(_safe_dict(progression.get("simulation_state")))

    metadata = _safe_dict(setup.get("metadata"))
    metadata["simulation_state"] = after_progression_state
    setup["metadata"] = metadata

    step_result = step_simulation_state(setup)
    next_setup = _safe_dict(step_result.get("next_setup")) or setup
    after_state = _ensure_simulation_state(_safe_dict(step_result.get("after_state")))

    scenes = generate_scenes_from_simulation(after_state)
    current_scene = _safe_dict(scenes[0]) if scenes else _fallback_scene(after_state, player_input)

    player_state = _safe_dict(after_state.get("player_state"))
    current_location_id = _get_player_location_id(after_state, runtime_state)
    current_scene["items"] = list_scene_items(after_state, current_location_id)
    current_scene["nearby_npcs"] = build_nearby_npc_cards(after_state, current_scene)

    narration_context = {
        "simulation_state": after_state,
        "player_input": player_input,
        "resolved_result": resolved_result,
        "xp_result": _safe_dict(progression.get("xp_result")),
        "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
        "level_up": _safe_list(progression.get("level_up")),
        "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
        "settings": runtime_state.get("settings", {}),
    }

    llm_gateway = build_app_llm_gateway()
    gateway_available = bool(llm_gateway)
    narration_result = narrate_scene(
        current_scene,
        narration_context,
        llm_gateway=llm_gateway,
        tone="dramatic",
    )
    if gateway_available and not narration_result.get("used_llm"):
        logger.error("RPG narration fallback occurred despite gateway availability")
    summary = summarize_simulation_step(step_result)

    runtime_state["tick"] = int(after_state.get("tick", runtime_state.get("tick", 0)) or 0)
    runtime_state["current_scene"] = current_scene
    runtime_state["last_turn_result"] = {
        "player_input": player_input,
        "action": action,
        "resolved_result": resolved_result,
        "combat_result": _safe_dict(resolved_result.get("combat_result")),
        "xp_result": _safe_dict(progression.get("xp_result")),
        "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
        "level_up": _safe_list(progression.get("level_up")),
        "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
        "summary": summary[:8],
        "narration": _safe_str(narration_result.get("narrative")),
    }
    turn_history = _safe_list(runtime_state.get("turn_history"))
    turn_history.append(_copy_dict(runtime_state["last_turn_result"]))
    runtime_state["turn_history"] = turn_history[-_MAX_HISTORY:]

    # Living-world: record player turn timing, reset idle streak
    runtime_state = ensure_ambient_runtime_state(runtime_state)
    runtime_state["last_player_turn_at"] = _utc_now_iso()
    runtime_state["idle_streak"] = 0

    session["setup_payload"] = next_setup
    session["simulation_state"] = after_state
    session["runtime_state"] = runtime_state
    manifest["updated_at"] = _utc_now_iso()
    session["manifest"] = manifest
    session = save_runtime_session(session)

    return {
        "ok": True,
        "session": session,
        "payload": {
            **build_frontend_bootstrap_payload(session),
            "narration": _safe_str(narration_result.get("narrative")),
            "combat_result": _safe_dict(resolved_result.get("combat_result")),
            "xp_result": _safe_dict(progression.get("xp_result")),
            "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
            "level_up": _safe_list(progression.get("level_up")),
            "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
            "action_metadata": _safe_dict(action.get("metadata")),
            "structured_narration": _safe_dict(narration_result.get("structured_narration")),
            "speaker_turns": _safe_list(narration_result.get("speaker_turns")),
            "narration": _safe_str(narration_result.get("narrative")),
            "used_app_llm": bool(narration_result.get("used_llm")),
            "gateway_available": gateway_available,
            "raw_llm_narrative": _safe_str(narration_result.get("raw_llm_narrative")),
            "response_length": _safe_str(runtime_state.get("settings", {}).get("response_length", "short")),
            "presentation": build_runtime_presentation_payload(after_state),
        },
    }


# ── Living world: idle tick engine (Phase 1) ──────────────────────────────


def _advance_simulation_for_idle(session: Dict[str, Any], *, reason: str = "heartbeat") -> Dict[str, Any]:
    """Step simulation forward without player input.

    Uses existing step_simulation_state() but does not require player action.
    Preserves canonical tick order and records metadata.
    """
    setup = apply_adventure_defaults(_copy_dict(session.get("setup_payload")))
    simulation_state = _ensure_simulation_state(_safe_dict(session.get("simulation_state")))

    metadata = _safe_dict(setup.get("metadata"))
    metadata["simulation_state"] = simulation_state
    setup["metadata"] = metadata

    step_result = step_simulation_state(setup)
    after_state = _ensure_simulation_state(_safe_dict(step_result.get("after_state")))
    next_setup = _safe_dict(step_result.get("next_setup")) or setup

    return {
        "ok": True,
        "before_state": _safe_dict(step_result.get("before_state")),
        "after_state": after_state,
        "next_setup": next_setup,
        "step_result": step_result,
        "reason": reason,
    }


def apply_idle_tick(session_id: str, *, reason: str = "heartbeat") -> Dict[str, Any]:
    """Advance the world by one idle tick without player action.

    Loads canonical session, advances simulation, builds ambient updates,
    enqueues them, persists session, and returns structured result.
    """
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    session = _copy_dict(session)
    runtime_state = ensure_ambient_runtime_state(_copy_dict(session.get("runtime_state")))

    # Advance simulation
    advance_result = _advance_simulation_for_idle(session, reason=reason)
    if not advance_result.get("ok"):
        return {"ok": False, "error": "idle_advance_failed"}

    before_state = _safe_dict(advance_result.get("before_state"))
    after_state = _safe_dict(advance_result.get("after_state"))
    next_setup = _safe_dict(advance_result.get("next_setup"))

    # Build ambient context
    context = {
        "player_location": _get_player_location_id(after_state, runtime_state),
        "nearby_npc_ids": _safe_list(_safe_dict(after_state.get("player_state")).get("nearby_npc_ids")),
        "recent_ambient_ids": _safe_list(runtime_state.get("recent_ambient_ids")),
    }

    # Extract, filter, score, coalesce
    raw_updates = build_ambient_updates(before_state, after_state, runtime_state)
    visible = [u for u in raw_updates if is_player_visible_update(u, session)]
    for u in visible:
        u["priority"] = score_ambient_salience(u, context)
    coalesced = coalesce_ambient_updates(visible, runtime_state)

    # Enqueue
    runtime_state = enqueue_ambient_updates(runtime_state, coalesced)

    # Idle bookkeeping
    runtime_state["idle_streak"] = int(runtime_state.get("idle_streak", 0) or 0) + 1
    runtime_state["last_idle_tick_at"] = _utc_now_iso()
    runtime_state["tick"] = int(after_state.get("tick", runtime_state.get("tick", 0)) or 0)
    runtime_state = normalize_ambient_state(runtime_state)

    # Persist
    session["simulation_state"] = after_state
    session["setup_payload"] = next_setup
    session["runtime_state"] = runtime_state
    manifest = _safe_dict(session.get("manifest"))
    manifest["updated_at"] = _utc_now_iso()
    session["manifest"] = manifest
    session = save_runtime_session(session)

    return {
        "ok": True,
        "session": session,
        "updates": coalesced,
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "idle_streak": int(runtime_state.get("idle_streak", 0) or 0),
    }


def apply_idle_ticks(session_id: str, count: int, *, reason: str = "heartbeat") -> Dict[str, Any]:
    """Apply multiple idle ticks, clamped to _MAX_IDLE_TICKS_PER_REQUEST.

    Coalesces results across ticks. Persists once at the end.
    """
    count = max(1, min(int(count), _MAX_IDLE_TICKS_PER_REQUEST))
    all_updates: List[Dict[str, Any]] = []
    last_result: Dict[str, Any] = {}

    ticks_applied = 0
    for i in range(count):
        result = apply_idle_tick(session_id, reason=reason)
        if not result.get("ok"):
            if i == 0:
                return result
            break
        ticks_applied += 1
        last_result = result
        all_updates.extend(_safe_list(result.get("updates")))

    return {
        "ok": True,
        "session": _safe_dict(last_result.get("session")),
        "updates": all_updates,
        "latest_seq": int(last_result.get("latest_seq", 0) or 0),
        "ticks_applied": ticks_applied,
    }