from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.campaign_journal.journal import build_player_story_recap
from app.rpg.quest_log.runtime import (
    build_objective_tracker_payload,
    build_quest_log_payload,
)

MAX_SUGGESTED_ACTIONS = 12
MAX_CONTEXT_ITEMS = 12


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _unique_action_id(prefix: str, index: int) -> str:
    return f"{prefix}:{int(index or 0):03d}"


def _append_action(
    actions: List[Dict[str, Any]],
    *,
    action_id: str,
    label: str,
    command: str,
    category: str,
    priority: int = 50,
    reason: str = "",
    objective_id: str = "",
    npc_id: str = "",
    mode: str = "",
    metadata: Dict[str, Any] | None = None,
) -> None:
    label = str(label or "").strip()
    command = str(command or "").strip()
    if not label or not command:
        return
    existing = {row.get("command") for row in actions}
    if command in existing:
        return
    actions.append(
        {
            "action_id": action_id,
            "label": label,
            "command": command,
            "category": category,
            "priority": max(0, min(100, int(priority or 0))),
            "reason": reason,
            "objective_id": objective_id,
            "npc_id": npc_id,
            "mode": mode,
            "metadata": metadata or {},
        }
    )


def _derive_mode(simulation_state: Dict[str, Any]) -> str:
    runtime = _safe_dict(simulation_state.get("runtime"))
    combat_state = _safe_dict(simulation_state.get("combat_state"))
    service_state = _safe_dict(simulation_state.get("service_state"))
    travel_state = _safe_dict(simulation_state.get("travel_state"))

    if combat_state.get("active") or combat_state.get("in_combat"):
        return "combat"
    if service_state.get("active") or service_state.get("pending_service"):
        return "service"
    if travel_state.get("active") or travel_state.get("pending_travel"):
        return "travel"
    return _safe_str(runtime.get("mode")) or "exploration"


def _derive_location(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    scene = _safe_dict(simulation_state.get("scene"))
    location = _safe_dict(simulation_state.get("location"))
    world = _safe_dict(simulation_state.get("world_state"))
    current_location = (
        _safe_str(scene.get("location"))
        or _safe_str(location.get("name"))
        or _safe_str(world.get("current_location"))
        or _safe_str(simulation_state.get("current_location"))
        or "current location"
    )
    scene_id = (
        _safe_str(scene.get("scene_id"))
        or _safe_str(location.get("location_id"))
        or _safe_str(simulation_state.get("scene_id"))
        or ""
    )
    return {
        "scene_id": scene_id,
        "location": current_location,
        "description": _safe_str(scene.get("description")) or _safe_str(location.get("description")),
    }


def _visible_npcs(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    scene = _safe_dict(simulation_state.get("scene"))
    npcs = []
    raw_scene_npcs = scene.get("nearby_npcs") or scene.get("npcs") or []
    for item in _safe_list(raw_scene_npcs):
        if isinstance(item, str):
            npcs.append({"npc_id": item, "name": item, "role": ""})
        elif isinstance(item, dict):
            npc_id = _safe_str(item.get("npc_id")) or _safe_str(item.get("id")) or _safe_str(item.get("name"))
            name = _safe_str(item.get("name")) or npc_id
            if npc_id or name:
                npcs.append(
                    {
                        "npc_id": npc_id,
                        "name": name,
                        "role": _safe_str(item.get("role")),
                        "relationship": _safe_str(item.get("relationship")),
                    }
                )

    # Fallback for older tests/fixtures that keep visible NPCs in session/runtime state.
    runtime = _safe_dict(simulation_state.get("runtime"))
    for item in _safe_list(runtime.get("nearby_npcs")):
        if isinstance(item, str):
            npcs.append({"npc_id": item, "name": item, "role": ""})
        elif isinstance(item, dict):
            npc_id = _safe_str(item.get("npc_id")) or _safe_str(item.get("id")) or _safe_str(item.get("name"))
            name = _safe_str(item.get("name")) or npc_id
            if npc_id or name:
                npcs.append({"npc_id": npc_id, "name": name, "role": _safe_str(item.get("role"))})

    seen = set()
    out = []
    for row in npcs:
        key = row.get("npc_id") or row.get("name")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= MAX_CONTEXT_ITEMS:
            break
    return out


def _active_objectives(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    tracker = build_objective_tracker_payload(simulation_state, limit=8)
    return [
        dict(row)
        for row in _safe_list(tracker.get("objectives"))
        if isinstance(row, dict)
    ][:8]


def _known_lore_rows(recap: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _safe_list(recap.get("known_lore")):
        if not isinstance(row, dict):
            continue
        truth_status = _safe_str(row.get("truth_status"))
        if truth_status == "secret" and not row.get("revealed_to_player"):
            continue
        rows.append(
            {
                "lore_id": _safe_str(row.get("lore_id")),
                "title": _safe_str(row.get("title")),
                "truth_status": truth_status or "unknown",
                "summary": _safe_str(row.get("summary")),
            }
        )
        if len(rows) >= MAX_CONTEXT_ITEMS:
            break
    return rows


def _active_arc_rows(recap: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _safe_list(recap.get("active_arcs")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "arc_id": _safe_str(row.get("arc_id")),
                "title": _safe_str(row.get("title")),
                "stage": _safe_str(row.get("stage")),
                "pressure": int(row.get("pressure") or 0),
            }
        )
        if len(rows) >= MAX_CONTEXT_ITEMS:
            break
    return rows


def _objective_actions(objectives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for index, objective in enumerate(objectives[:5]):
        objective_id = _safe_str(objective.get("objective_id"))
        text = _safe_str(objective.get("objective_text")) or _safe_str(objective.get("title"))
        title = _safe_str(objective.get("title")) or text
        if not text:
            continue
        _append_action(
            actions,
            action_id=_unique_action_id("objective", index),
            label=f"Pursue objective: {title}",
            command=f"I focus on the objective: {text}",
            category="objective",
            priority=95 - index,
            reason="Active objective from quest log.",
            objective_id=objective_id,
        )
    return actions


def _npc_actions(npcs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for index, npc in enumerate(npcs[:5]):
        name = _safe_str(npc.get("name")) or _safe_str(npc.get("npc_id"))
        npc_id = _safe_str(npc.get("npc_id")) or name
        if not name:
            continue
        _append_action(
            actions,
            action_id=_unique_action_id("npc_talk", index),
            label=f"Talk to {name}",
            command=f"I talk to {name} and ask what they know.",
            category="social",
            priority=72 - index,
            reason="Nearby NPC is available for conversation.",
            npc_id=npc_id,
        )
        _append_action(
            actions,
            action_id=_unique_action_id("npc_ask_objective", index),
            label=f"Ask {name} about current objectives",
            command=f"I ask {name} if they know anything that can help with my current objective.",
            category="social",
            priority=65 - index,
            reason="NPC may provide grounded context or rumors.",
            npc_id=npc_id,
        )
    return actions


def _mode_actions(mode: str, location: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    place = _safe_str(location.get("location")) or "the area"

    if mode == "combat":
        _append_action(
            actions,
            action_id="mode:combat_attack",
            label="Make a cautious attack",
            command="I make a cautious attack against the nearest hostile enemy.",
            category="combat",
            priority=90,
            reason="Combat is active.",
            mode=mode,
        )
        _append_action(
            actions,
            action_id="mode:combat_defend",
            label="Defend and assess enemies",
            command="I defend myself and look for the safest tactical opening.",
            category="combat",
            priority=85,
            reason="Combat is active.",
            mode=mode,
        )
        return actions

    if mode == "service":
        _append_action(
            actions,
            action_id="mode:service_confirm",
            label="Confirm available service",
            command="I ask what services are available and what they cost.",
            category="service",
            priority=80,
            reason="Service interaction appears available.",
            mode=mode,
        )
        return actions

    if mode == "travel":
        _append_action(
            actions,
            action_id="mode:travel_continue",
            label="Continue travel carefully",
            command="I continue traveling carefully while watching for danger.",
            category="travel",
            priority=80,
            reason="Travel appears active.",
            mode=mode,
        )
        return actions

    _append_action(
        actions,
        action_id="mode:observe",
        label=f"Observe {place}",
        command=f"I carefully observe {place} for useful details, exits, people, and threats.",
        category="exploration",
        priority=60,
        reason="General exploration fallback.",
        mode=mode,
    )
    _append_action(
        actions,
        action_id="mode:listen",
        label="Listen for rumors or trouble",
        command="I listen for rumors, signs of danger, or anything connected to my current objectives.",
        category="exploration",
        priority=55,
        reason="General story discovery fallback.",
        mode=mode,
    )
    _append_action(
        actions,
        action_id="mode:quest_log",
        label="Review quest log",
        command="I review my quest log and decide what objective to pursue next.",
        category="quest_log",
        priority=50,
        reason="Quest log can guide next action.",
        mode=mode,
    )
    return actions


def _arc_actions(arcs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for index, arc in enumerate(arcs[:4]):
        title = _safe_str(arc.get("title")) or _safe_str(arc.get("arc_id"))
        stage = _safe_str(arc.get("stage"))
        if not title:
            continue
        _append_action(
            actions,
            action_id=_unique_action_id("arc", index),
            label=f"Investigate story arc: {title}",
            command=f"I look for a grounded way to make progress on {title}.",
            category="story_arc",
            priority=62 - index,
            reason=f"Active story arc stage: {stage}",
            metadata={"arc_id": arc.get("arc_id"), "stage": stage},
        )
    return actions


def build_suggested_actions(
    simulation_state: Dict[str, Any],
    *,
    limit: int = MAX_SUGGESTED_ACTIONS,
    turn_index: int = 0,
) -> List[Dict[str, Any]]:
    limit = max(0, min(MAX_SUGGESTED_ACTIONS, int(limit or MAX_SUGGESTED_ACTIONS)))
    recap = build_player_story_recap(simulation_state, turn_index=turn_index, max_items=MAX_CONTEXT_ITEMS)
    objectives = _active_objectives(simulation_state)
    npcs = _visible_npcs(simulation_state)
    location = _derive_location(simulation_state)
    mode = _derive_mode(simulation_state)
    arcs = _active_arc_rows(recap)

    actions: List[Dict[str, Any]] = []
    for row in _objective_actions(objectives):
        actions.append(row)
    for row in _npc_actions(npcs):
        actions.append(row)
    for row in _arc_actions(arcs):
        actions.append(row)
    for row in _mode_actions(mode, location):
        actions.append(row)

    actions.sort(
        key=lambda row: (
            -int(row.get("priority") or 0),
            str(row.get("category") or ""),
            str(row.get("action_id") or ""),
        )
    )
    return actions[:limit]


def build_player_action_context(
    simulation_state: Dict[str, Any],
    *,
    turn_index: int = 0,
    limit: int = MAX_SUGGESTED_ACTIONS,
) -> Dict[str, Any]:
    limit = max(0, min(MAX_SUGGESTED_ACTIONS, int(limit or MAX_SUGGESTED_ACTIONS)))
    recap = build_player_story_recap(simulation_state, turn_index=turn_index, max_items=MAX_CONTEXT_ITEMS)
    quest_log = build_quest_log_payload(simulation_state, limit=MAX_CONTEXT_ITEMS)
    tracker = build_objective_tracker_payload(simulation_state, limit=8)
    location = _derive_location(simulation_state)
    mode = _derive_mode(simulation_state)
    npcs = _visible_npcs(simulation_state)
    suggested_actions = build_suggested_actions(
        simulation_state,
        limit=limit,
        turn_index=turn_index,
    )

    return {
        "ok": True,
        "format_version": "player_action_context_v1",
        "turn_index": int(turn_index or 0),
        "mode": mode,
        "location": location,
        "nearby_npcs": npcs,
        "active_objectives": list(tracker.get("objectives") or [])[:8],
        "quest_log_summary": {
            "active_count": len(quest_log.get("active_objectives") or []),
            "completed_count": len(quest_log.get("completed_objectives") or []),
            "pinned_objective_ids": list(quest_log.get("pinned_objective_ids") or []),
        },
        "known_lore": _known_lore_rows(recap),
        "active_arcs": _active_arc_rows(recap),
        "suggested_actions": suggested_actions,
        "restrictions": [
            "Choose an action; do not decide the outcome.",
            "Do not invent rewards, XP, gold, loot, deaths, or quest completion.",
            "Do not reveal hidden or secret lore.",
            "The simulation resolves success, failure, costs, and consequences.",
        ],
        "player_agent_schema": {
            "format_version": "rpg_player_action_v1",
            "intent": "short intent",
            "action": "single player-facing action command",
            "reason": "why this action was chosen",
            "risk": "low|medium|high",
            "goal_id": "optional objective_id",
        },
        "bounded": {
            "suggested_action_limit": limit,
            "max_context_items": MAX_CONTEXT_ITEMS,
            "max_suggested_actions": MAX_SUGGESTED_ACTIONS,
        },
    }