from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    return " ".join(_safe_str(value).lower().strip().split())


def _semantic(action: str) -> str:
    action = _norm(action)
    if any(word in action for word in ("ask", "question", "talk", "speak")):
        return "ask"
    if any(word in action for word in ("inspect", "examine", "search", "look")):
        return "inspect"
    if any(word in action for word in ("travel", "leave", "go", "move", "head")):
        return "travel"
    if any(word in action for word in ("report", "tell", "warn")):
        return "report_warn"
    if any(word in action for word in ("prepare", "help", "ready")):
        return "prepare"
    return "other"


def evaluate_behavioral_autoplay(
    transcript: List[Dict[str, Any]],
    latest_state: Dict[str, Any],
    *,
    requested_turns: int,
) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in _safe_list(transcript)]
    actions = [_safe_str(row.get("player_action")) for row in rows]
    normalized = [_norm(action) for action in actions if action]

    exact_counts: Dict[str, int] = {}
    max_exact_streak = 0
    current = ""
    streak = 0
    for action in normalized:
        exact_counts[action] = exact_counts.get(action, 0) + 1
        if action == current:
            streak += 1
        else:
            current = action
            streak = 1
        max_exact_streak = max(max_exact_streak, streak)

    semantics = [_semantic(action) for action in actions]
    semantic_diversity = len(set(semantics))

    progression_logs = _safe_list(_safe_dict(latest_state).get("scenario_progression_log"))
    progression_changed = [row for row in progression_logs if _safe_dict(row).get("changed")]
    completed_nodes = _safe_dict(latest_state.get("progression_completed_nodes"))
    matched_node_events: List[tuple] = []
    for row in progression_changed:
        row = _safe_dict(row)
        turn_index = int(row.get("turn_index") or 0)
        for node_id in _safe_list(row.get("matched_node_ids")):
            if _safe_str(node_id):
                matched_node_events.append((turn_index, _safe_str(node_id)))
        for node in _safe_list(row.get("matched_nodes")):
            node_id = _safe_str(_safe_dict(node).get("node_id"))
            if node_id:
                matched_node_events.append((turn_index, node_id))
    matched_node_events = sorted(set(matched_node_events))
    matched_node_counts: Dict[str, int] = {}
    for _turn_index, node_id in matched_node_events:
        matched_node_counts[node_id] = matched_node_counts.get(node_id, 0) + 1
    repeated_node_ids = [
        node_id for node_id, count in matched_node_counts.items()
        if count > 1
    ]

    qp = _safe_dict(_safe_dict(latest_state).get("quest_progress"))
    quests = _safe_dict(qp.get("quests"))
    graph_quest_state = _safe_dict(latest_state.get("scenario_progression_quest_state"))
    arc_summary = _safe_dict(latest_state.get("scenario_progression_arc_summary"))
    arc_complete = bool(arc_summary.get("arc_complete"))
    if graph_quest_state:
        merged_quests = dict(quests)
        merged_quests.update(graph_quest_state)
        quests = merged_quests
    completed_quests = [
        quest_id
        for quest_id, quest in quests.items()
        if _safe_dict(quest).get("completed") or _safe_str(_safe_dict(quest).get("status")) == "completed"
    ]
    active_quests = [
        quest_id
        for quest_id, quest in quests.items()
        if not _safe_dict(quest).get("completed") and _safe_str(_safe_dict(quest).get("status")) == "active"
    ]

    location_history = _safe_list(_safe_dict(latest_state).get("location_history"))
    unlocked_npcs = _safe_dict(latest_state.get("progression_unlocked_npcs"))
    unlocked_locations = _safe_dict(latest_state.get("progression_unlocked_locations"))
    facts = _safe_dict(latest_state.get("progression_facts"))
    sidecar_counts = [
        int(_safe_dict(row).get("progression_sidecar_completed_node_count") or 0)
        for row in rows
        if "progression_sidecar_completed_node_count" in _safe_dict(row)
    ]
    sidecar_fields_present = len(sidecar_counts) == len(rows) if rows else False
    sidecar_decreased = any(
        later < earlier
        for earlier, later in zip(sidecar_counts, sidecar_counts[1:])
    )
    graph_empty_with_active_objective_rows = [
        i + 1
        for i, row in enumerate(rows)
        if bool(_safe_dict(row).get("scenario_progression_actions_empty_with_active_objectives"))
    ]
    graph_actions_empty_with_active_graph_quest_ok = arc_complete or not graph_empty_with_active_objective_rows

    active_graph_quests = [
        _safe_dict(quest)
        for quest in graph_quest_state.values()
        if not bool(_safe_dict(quest).get("completed"))
        and _safe_str(_safe_dict(quest).get("status")) != "completed"
    ]
    active_graph_quest_has_objectives_ok = True
    for quest in active_graph_quests:
        objectives = _safe_list(quest.get("objectives"))
        active_objectives = [
            obj for obj in objectives
            if not bool(_safe_dict(obj).get("completed"))
            and _safe_str(_safe_dict(obj).get("status")) != "completed"
        ]
        if not active_objectives and not arc_complete:
            active_graph_quest_has_objectives_ok = False
            break

    same_action_too_much = bool(exact_counts and max(exact_counts.values()) > max(3, requested_turns // 4))
    exact_streak_bad = max_exact_streak > 3
    no_progression = len(progression_changed) < 3 if requested_turns >= 10 else False
    unique_node_count = len(completed_nodes) or len({node_id for _turn, node_id in matched_node_events})
    low_unique_nodes = unique_node_count < 3 if requested_turns >= 10 else False
    repeated_graph_node = bool(repeated_node_ids)
    no_quest_transition = not completed_quests if requested_turns >= 10 else False
    no_second_stage = len(quests) < 2 if requested_turns >= 15 else False
    no_location_change = len(location_history) < 1 and len(unlocked_locations) < 2 if requested_turns >= 15 else False
    low_semantic_diversity = semantic_diversity < 3 if requested_turns >= 10 else False

    gates = {
        "exact_action_streak_ok": not exact_streak_bad,
        "same_action_volume_ok": not same_action_too_much,
        "scenario_progression_changed_ok": not no_progression,
        "unique_progression_nodes_ok": not low_unique_nodes,
        "no_repeated_nonrepeatable_node_ok": not repeated_graph_node,
        "progression_sidecar_monotonic_ok": not sidecar_decreased,
        "progression_sidecar_fields_present_ok": sidecar_fields_present,
        "graph_actions_empty_with_active_graph_quest_ok": graph_actions_empty_with_active_graph_quest_ok,
        "active_graph_quest_has_objectives_ok": active_graph_quest_has_objectives_ok,
        "quest_transition_ok": not no_quest_transition,
        "second_stage_quest_ok": not no_second_stage,
        "location_progress_ok": not no_location_change,
        "semantic_diversity_ok": not low_semantic_diversity,
    }
    failed = [name for name, ok in gates.items() if not ok]
    return {
        "ok": not failed,
        "gates": gates,
        "failed_gates": failed,
        "metrics": {
            "turn_count": len(rows),
            "unique_action_count": len(set(normalized)),
            "max_exact_streak": max_exact_streak,
            "max_exact_action_count": max(exact_counts.values()) if exact_counts else 0,
            "semantic_diversity": semantic_diversity,
            "progression_changed_count": len(progression_changed),
            "unique_progression_node_count": unique_node_count,
            "matched_node_counts": matched_node_counts,
            "repeated_node_ids": repeated_node_ids,
            "graph_empty_with_active_objective_rows": graph_empty_with_active_objective_rows,
            "quest_count": len(quests),
            "completed_quest_count": len(completed_quests),
            "active_quest_count": len(active_quests),
            "active_graph_quest_count": len(active_graph_quests),
            "active_graph_quest_has_objectives": active_graph_quest_has_objectives_ok,
            "scenario_arc_complete": arc_complete,
            "unlocked_npc_count": len(unlocked_npcs),
            "unlocked_location_count": len(unlocked_locations),
            "fact_count": len(facts),
            "location_history_count": len(location_history),
            "progression_sidecar_counts": sidecar_counts,
            "progression_sidecar_fields_present": sidecar_fields_present,
            "progression_sidecar_max_count": max(sidecar_counts) if sidecar_counts else 0,
        },
    }