from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, List

from app.rpg.progression.graph_registry import (
    get_progression_graph_by_id,
    get_progression_graph_for_seed,
    get_progression_graphs_for_seed,
)
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm(value: Any) -> str:
    text = _safe_str(value).strip().lower()
    for ch in ["-", "—", "–", "_", ".", ",", ";", ":", "!", "?", "'", '"', "’", "“", "”", "(", ")", "[", "]"]:
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _semantic_aliases(semantic: str) -> List[str]:
    semantic = _safe_str(semantic)
    return {
        "ask": ["ask", "question", "talk", "speak", "who", "what", "where", "whether"],
        "inspect": ["inspect", "examine", "look", "search", "check", "scout", "survey", "scan", "read", "study", "open", "decipher"],
        "scout": ["scout", "inspect", "examine", "look", "search", "check", "survey", "scan"],
        "search": ["search", "inspect", "examine", "look", "check", "scout", "survey", "scan"],
        "scan": ["scan", "scout", "inspect", "look", "search"],
        "read": ["read", "study", "inspect", "examine", "open", "decipher"],
        "study": ["study", "read", "inspect", "examine", "decipher"],
        "open": ["open", "read", "inspect", "examine"],
        "travel": ["travel", "leave", "go", "head", "move", "walk", "set out"],
        "report": ["report", "tell", "explain", "show", "warn"],
        "warn": ["warn", "tell", "alert", "show", "explain"],
        "tell": ["tell", "warn", "explain", "show"],
        "prepare": ["prepare", "ready", "help", "load", "tighten", "pack", "decide", "choose", "plan"],
        "decide": ["decide", "choose", "plan", "prepare", "commit", "follow"],
    }.get(semantic, [semantic])


def _topic_matches(action_norm: str, topics: List[str]) -> bool:
    if not topics:
        return True
    normalized_topics = [_norm(topic) for topic in topics if _safe_str(topic)]
    if not normalized_topics:
        return True
    return any(topic in action_norm for topic in normalized_topics)


def _bag(state: Dict[str, Any], key: str) -> Dict[str, Any]:
    bag = state.setdefault(key, {})
    if not isinstance(bag, dict):
        bag = {}
        state[key] = bag
    return bag


def _stamp_progression_revision(state: Dict[str, Any], *, reason: str, turn_index: int = 0) -> None:
    completed_node_count = len(_safe_dict(state.get("progression_completed_nodes")))
    fact_count = len(_safe_dict(state.get("progression_facts")))
    lead_count = len(_safe_dict(state.get("progression_leads")))
    prior = int(state.get("progression_state_revision") or 0)
    derived = completed_node_count * 10000 + fact_count * 100 + lead_count
    revision = max(prior + 1, derived)
    state["progression_state_revision"] = revision
    state["progression_completed_node_count"] = completed_node_count
    state["progression_fact_count"] = fact_count
    state["progression_lead_count"] = lead_count
    state["progression_authority_summary"] = {
        "revision": revision,
        "completed_node_count": completed_node_count,
        "fact_count": fact_count,
        "lead_count": lead_count,
        "reason": reason,
        "turn_index": turn_index,
    }


def _facts(state: Dict[str, Any]) -> Dict[str, Any]:
    return _bag(state, "progression_facts")


def _leads(state: Dict[str, Any]) -> Dict[str, Any]:
    return _bag(state, "progression_leads")


def _nodes_completed(state: Dict[str, Any]) -> Dict[str, Any]:
    return _bag(state, "progression_completed_nodes")


def _unlocked_npcs(state: Dict[str, Any]) -> Dict[str, Any]:
    return _bag(state, "progression_unlocked_npcs")


def _unlocked_locations(state: Dict[str, Any]) -> Dict[str, Any]:
    return _bag(state, "progression_unlocked_locations")


def _quest_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    qp = state.setdefault("quest_progress", {})
    if not isinstance(qp, dict):
        qp = {}
        state["quest_progress"] = qp
    quests = qp.setdefault("quests", {})
    if not isinstance(quests, dict):
        quests = {}
        qp["quests"] = quests
    return qp


def _ensure_quest(state: Dict[str, Any], quest_id: str, title: str) -> Dict[str, Any]:
    quests = _quest_progress(state)["quests"]
    quest = quests.setdefault(
        quest_id,
        {
            "quest_id": quest_id,
            "title": title or quest_id,
            "status": "active",
            "completed": False,
            "objectives": [],
            "source": "scenario_progression_graph",
        },
    )
    quest["status"] = "active" if not quest.get("completed") else "completed"
    quest.setdefault("source", "scenario_progression_graph")
    if quest.get("source") == "scenario_progression_graph" and not quest.get("completed"):
        quest["status"] = "active"
    quest.setdefault("objectives", [])
    return quest


def _infer_active_quest_id(state: Dict[str, Any]) -> str:
    quests = _safe_dict(_quest_progress(state).get("quests"))
    for quest_id, quest in quests.items():
        quest = _safe_dict(quest)
        if not quest.get("completed") and _safe_str(quest.get("status")) == "active":
            return _safe_str(quest_id)
    return ""


def _ensure_objective(
    state: Dict[str, Any],
    objective_id: str,
    *,
    quest_id: str = "",
    summary: str = "",
) -> Dict[str, Any]:
    if not quest_id:
        if objective_id in {"objective:warn_garran", "objective:travel_to_wagon_yard", "objective:choose_safe_route"}:
            quest_id = "quest:warn_wagon"
        elif objective_id in {
            "objective:leave_by_quarry_road",
            "objective:scout_quarry_road",
            "objective:spot_bridge_watchers",
            "objective:choose_ambush_response",
            "objective:protect_wagon",
        }:
            quest_id = "quest:quarry_road_ambush"
        elif objective_id in {"objective:find_witness", "objective:ask_mira", "objective:inspect_side_door"}:
            quest_id = "quest:witness_search"
    quest_id = quest_id or _infer_active_quest_id(state) or "quest:scenario_progression"
    quest = _ensure_quest(
        state,
        quest_id,
        quest_id.replace("quest:", "").replace("_", " ").title(),
    )
    for obj in _safe_list(quest.get("objectives")):
        obj = _safe_dict(obj)
        if obj.get("objective_id") == objective_id:
            return obj
    obj = {
        "objective_id": objective_id,
        "summary": summary or objective_id.replace("objective:", "").replace("_", " "),
        "status": "active",
        "completed": False,
        "source": "scenario_progression_graph",
        "progress_count": 0,
    }
    quest.setdefault("objectives", []).append(obj)
    return obj


def _complete_objective(state: Dict[str, Any], objective_id: str) -> None:
    for quest in _safe_dict(_quest_progress(state).get("quests")).values():
        quest = _safe_dict(quest)
        for obj in _safe_list(quest.get("objectives")):
            obj = _safe_dict(obj)
            if obj.get("objective_id") == objective_id:
                obj["completed"] = True
                obj["status"] = "completed"
                obj["completion_evidence"] = {"source": "scenario_progression_graph"}
        objectives = [_safe_dict(row) for row in _safe_list(quest.get("objectives"))]
        if objectives and all(bool(obj.get("completed")) for obj in objectives):
            quest["completed"] = True
            quest["status"] = "completed"


def _complete_quest(state: Dict[str, Any], quest_id: str) -> None:
    quest = _safe_dict(_safe_dict(_quest_progress(state).get("quests")).get(quest_id))
    if not quest:
        return
    quest["completed"] = True
    quest["status"] = "completed"
    for obj in _safe_list(quest.get("objectives")):
        obj = _safe_dict(obj)
        obj["completed"] = True
        obj["status"] = "completed"


def _requirement_met(state: Dict[str, Any], req: Dict[str, Any]) -> bool:
    req = _safe_dict(req)
    if not req:
        return True
    if "fact" in req:
        return _safe_str(req["fact"]) in _facts(state)
    if "lead" in req:
        return _safe_str(req["lead"]) in _leads(state)
    if "node" in req:
        return _safe_str(req["node"]) in _nodes_completed(state)
    if "npc" in req:
        return _safe_str(req["npc"]) in _unlocked_npcs(state)
    if "location" in req:
        return _safe_str(req["location"]) in _unlocked_locations(state)
    if "quest" in req:
        quest_id = _safe_str(req["quest"])
        quest = _safe_dict(_safe_dict(_quest_progress(state).get("quests")).get(quest_id))
        if not quest:
            return False
        status = _safe_str(req.get("status"))
        if status:
            return _safe_str(quest.get("status")) == status
        return True
    return True


def _node_available(state: Dict[str, Any], node: ProgressionNode) -> bool:
    if not node.repeatable and node.node_id in _nodes_completed(state):
        return False
    return all(_requirement_met(state, req) for req in node.requires)


def _node_block_reasons(state: Dict[str, Any], node: ProgressionNode) -> List[str]:
    reasons: List[str] = []
    if not node.repeatable and node.node_id in _nodes_completed(state):
        reasons.append("completed")
    for req in node.requires:
        if not _requirement_met(state, req):
            reasons.append(f"missing:{req}")
    return reasons


def _completed_graph_ids(state: Dict[str, Any]) -> List[str]:
    return [
        _safe_str(value)
        for value in _safe_list(_safe_dict(state).get("scenario_progression_completed_graph_ids"))
        if _safe_str(value)
    ]


def _set_completed_graph_ids(state: Dict[str, Any], graph_ids: List[str]) -> None:
    ordered: List[str] = []
    seen = set()
    for graph_id in graph_ids:
        graph_id = _safe_str(graph_id)
        if graph_id and graph_id not in seen:
            ordered.append(graph_id)
            seen.add(graph_id)
    state["scenario_progression_completed_graph_ids"] = ordered


def _quest_is_completed(state: Dict[str, Any], quest_id: str) -> bool:
    quest = _safe_dict(_safe_dict(_quest_progress(state).get("quests")).get(_safe_str(quest_id)))
    return bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed"


def _graph_is_complete(state: Dict[str, Any], graph: ScenarioProgressionGraph) -> bool:
    if not graph or not _safe_list(getattr(graph, "nodes", [])):
        return False
    completed_nodes = _nodes_completed(state)
    return all(_safe_str(node.node_id) in completed_nodes for node in graph.nodes)


def _graph_is_eligible(state: Dict[str, Any], graph: ScenarioProgressionGraph) -> bool:
    if not graph:
        return False

    completed_graph_ids = set(_completed_graph_ids(state))
    repeatable = bool(getattr(graph, "repeatable", False))
    if graph.graph_id in completed_graph_ids and not repeatable:
        return False

    for required_graph_id in _safe_list(getattr(graph, "starts_after_graph_ids", [])):
        if _safe_str(required_graph_id) not in completed_graph_ids:
            return False

    for required_quest_id in _safe_list(getattr(graph, "starts_after_quest_ids", [])):
        if not _quest_is_completed(state, _safe_str(required_quest_id)):
            return False

    return True


def _mark_graph_complete_if_needed(
    state: Dict[str, Any],
    graph: ScenarioProgressionGraph,
) -> None:
    if not graph or not _graph_is_complete(state, graph):
        return
    completed = _completed_graph_ids(state)
    if graph.graph_id not in completed:
        completed.append(graph.graph_id)
        _set_completed_graph_ids(state, completed)
    state["scenario_progression_last_completed_graph_id"] = graph.graph_id


def _select_active_graph(
    state: Dict[str, Any],
    *,
    scenario_seed: str,
) -> ScenarioProgressionGraph | None:
    graphs = get_progression_graphs_for_seed(scenario_seed)
    if not graphs:
        return None

    current_id = _safe_str(_safe_dict(state).get("scenario_progression_active_graph_id"))
    current = get_progression_graph_by_id(scenario_seed, current_id) if current_id else None
    if current and not _graph_is_complete(state, current):
        return current

    eligible = [graph for graph in graphs if _graph_is_eligible(state, graph)]
    if eligible:
        eligible.sort(key=lambda graph: (-int(getattr(graph, "priority", 100)), graph.graph_id))
        return eligible[0]

    # First graph fallback only before anything has started.
    first = graphs[0]
    if not _completed_graph_ids(state) and not _graph_is_complete(state, first):
        return first

    return None


def _refresh_active_graph(
    state: Dict[str, Any],
    *,
    scenario_seed: str,
) -> ScenarioProgressionGraph | None:
    graphs = get_progression_graphs_for_seed(scenario_seed)
    if not graphs:
        state["scenario_progression_waiting_for_next_graph_pack"] = True
        return None

    for graph in graphs:
        _mark_graph_complete_if_needed(state, graph)

    active = _select_active_graph(state, scenario_seed=scenario_seed)
    if active:
        state["scenario_progression_active_graph_id"] = active.graph_id
        state["scenario_progression_active_graph_title"] = getattr(active, "title", active.graph_id)
        state["scenario_progression_waiting_for_next_graph_pack"] = False
        return active

    state["scenario_progression_active_graph_id"] = ""
    state["scenario_progression_active_graph_title"] = ""
    state["scenario_progression_waiting_for_next_graph_pack"] = True
    return None


def get_active_progression_actions(
    runtime_state: Dict[str, Any],
    *,
    scenario_seed: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    state = _safe_dict(runtime_state)
    graph = _refresh_active_graph(state, scenario_seed=scenario_seed)
    if not graph:
        return _arc_complete_idle_action(state, scenario_seed=scenario_seed)
    state = _safe_dict(runtime_state)
    out: List[Dict[str, Any]] = []
    debug_nodes: List[Dict[str, Any]] = []
    for node in graph.nodes:
        block_reasons = _node_block_reasons(state, node)
        debug_nodes.append(
            {
                "node_id": node.node_id,
                "available": not block_reasons,
                "block_reasons": block_reasons,
            }
        )
        if block_reasons:
            continue
        for action in node.suggested_actions:
            row = asdict(action)
            row["node_id"] = node.node_id
            row["node_title"] = node.title
            row["graph_id"] = graph.graph_id
            row["source"] = "scenario_progression_graph"
            row["priority"] = max(int(row.get("priority") or 0), int(node.priority or 0))
            out.append(row)
    out.sort(key=lambda row: (-int(row.get("priority") or 0), _safe_str(row.get("node_id"))))
    if not out:
        out = synthesize_progression_actions_from_objectives(state, limit=limit)
    if not out:
        out = _arc_complete_idle_actions(state, scenario_seed=scenario_seed)
    state["scenario_progression_action_debug"] = {
        "graph_id": graph.graph_id,
        "active_graph_id": graph.graph_id,
        "active_graph_title": getattr(graph, "title", graph.graph_id),
        "completed_graph_ids": _completed_graph_ids(state),
        "waiting_for_next_graph_pack": bool(state.get("scenario_progression_waiting_for_next_graph_pack")),
        "available_action_count": len(out),
        "progression_state_revision": int(state.get("progression_state_revision") or 0),
        "completed_node_count": len(_nodes_completed(state)),
        "synthesized_from_objectives": bool(
            out and _safe_str(_safe_dict(out[0]).get("source")) == "scenario_progression_objective_synthesis"
        ),
        "active_graph_objective_count": len(_active_graph_objectives(state)),
        "nodes": debug_nodes[-30:],
    }
    return out[:limit]


def _progression_log_marker(row: Dict[str, Any]) -> tuple:
    row = _safe_dict(row)
    node_ids = tuple(_safe_str(node_id) for node_id in _safe_list(row.get("matched_node_ids")))
    if not node_ids:
        node_ids = tuple(
            _safe_str(_safe_dict(node).get("node_id"))
            for node in _safe_list(row.get("matched_nodes"))
        )
    return (
        _safe_str(row.get("graph_id")),
        int(row.get("turn_index") or 0),
        node_ids,
    )


def _append_progression_log(state: Dict[str, Any], summary: Dict[str, Any]) -> None:
    log = state.setdefault("scenario_progression_log", [])
    if not isinstance(log, list):
        log = []
        state["scenario_progression_log"] = log
    marker = _progression_log_marker(summary)
    existing_markers = {_progression_log_marker(_safe_dict(row)) for row in log}
    if marker not in existing_markers:
        log.append(summary)
    del log[:-100]


def _action_matches_pattern(action: str, pattern: Dict[str, Any]) -> bool:
    pattern = _safe_dict(pattern)
    action_norm = _norm(action)
    semantic = _safe_str(pattern.get("semantic"))
    if semantic:
        if not any(alias in action_norm for alias in _semantic_aliases(semantic)):
            return False
    topics = [_safe_str(topic) for topic in _safe_list(pattern.get("topics_any")) if _safe_str(topic)]
    if not _topic_matches(action_norm, topics):
        return False
    target_id = _safe_str(pattern.get("target_id"))
    if target_id:
        target_label = target_id.split(":")[-1].replace("_", " ")
        target_aliases = {
            "bran": ["bran", "innkeeper", "barkeep", "tavern keeper"],
            "mira": ["mira", "server", "barmaid", "woman"],
            "local patron": ["local patron", "patron", "man by the hearth", "nearby patron"],
            "garran": ["garran", "wagoner", "merchant", "driver"],
            "side door latch": ["side door", "latch", "threshold"],
            "garran wagon yard": ["wagon yard", "garran", "yard"],
            "quarry road": ["quarry road", "safer route", "alternate route"],
            "rock shelf": ["rock shelf", "rocks", "shelf", "quarry"],
            "wagon": ["wagon", "cart", "supply wagon"],
            "wax sealed order": ["wax-sealed order", "wax sealed order", "sealed order", "order", "document", "letter"],
            "bandit satchel": ["satchel", "bandit satchel", "bag", "pouch"],
            "smuggler cache": ["cache", "smuggler cache", "hidden cache", "crates"],
            "old mill ruins": ["old mill", "mill ruins", "old mill ruins", "mill"],
        }
        aliases = target_aliases.get(target_label, [target_label])
        if target_label and not any(alias in action_norm for alias in aliases):
            return False
    return True


def _active_graph_objectives(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    quests = _safe_dict(_quest_progress(state).get("quests"))
    for quest_id, quest in quests.items():
        quest = _safe_dict(quest)
        if _safe_str(quest.get("source")) != "scenario_progression_graph":
            continue
        if bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed":
            continue
        for objective in _safe_list(quest.get("objectives")):
            objective = _safe_dict(objective)
            if bool(objective.get("completed")) or _safe_str(objective.get("status")) == "completed":
                continue
            out.append(
                {
                    "quest_id": _safe_str(quest_id),
                    "quest_title": _safe_str(quest.get("title")),
                    "objective_id": _safe_str(objective.get("objective_id")),
                    "summary": _safe_str(objective.get("summary") or objective.get("title")),
                }
            )
    return out


def _synthesize_action_for_graph_objective(objective: Dict[str, Any]) -> Dict[str, Any]:
    objective = _safe_dict(objective)
    objective_id = _safe_str(objective.get("objective_id"))
    summary = _safe_str(objective.get("summary"))
    command_by_id = {
        "objective:leave_by_quarry_road": "I leave Garran's wagon yard with the wagon and take the quarry road.",
        "objective:scout_quarry_road": "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        "objective:spot_bridge_watchers": "I scan the rock shelf for watchers or scouts watching the quarry road.",
        "objective:choose_ambush_response": "I tell Garran we should slow the wagon and lure the watchers into revealing the ambush.",
        "objective:protect_wagon": "I help Garran protect the wagon while drawing the ambushers out of hiding.",
    }
    command = command_by_id.get(objective_id) or f"I work on the objective: {summary}."
    return {
        "action_id": f"synth:{objective_id}",
        "node_id": "",
        "command": command,
        "title": summary or objective_id,
        "priority": 60,
        "source": "scenario_progression_objective_synthesis",
        "objective_id": objective_id,
        "quest_id": _safe_str(objective.get("quest_id")),
    }


def build_scenario_progression_arc_summary(
    state: Dict[str, Any],
    *,
    scenario_seed: str,
) -> Dict[str, Any]:
    graphs = get_progression_graphs_for_seed(scenario_seed)
    active_graph = _refresh_active_graph(state, scenario_seed=scenario_seed)
    graph = active_graph or (graphs[0] if graphs else None)
    state = _safe_dict(state)
    completed_nodes = _safe_dict(state.get("progression_completed_nodes"))
    completed_node_ids = sorted(completed_nodes.keys())
    expected_node_ids = [node.node_id for node in graph.nodes] if graph else []
    all_expected_node_ids = [
        node.node_id
        for candidate_graph in graphs
        for node in candidate_graph.nodes
    ]
    completed_graph_ids = _completed_graph_ids(state)
    graph_ids = [graph.graph_id for graph in graphs]
    campaign_graphs_complete = bool(
        graph_ids and all(graph_id in set(completed_graph_ids) for graph_id in graph_ids)
    )

    qp = _safe_dict(state.get("quest_progress"))
    quests = _safe_dict(qp.get("quests"))
    graph_quests = {
        quest_id: _safe_dict(quest)
        for quest_id, quest in quests.items()
        if _safe_str(_safe_dict(quest).get("source")) == "scenario_progression_graph"
        or quest_id in {
            "quest:witness_search",
            "quest:warn_wagon",
            "quest:quarry_road_ambush",
        }
    }
    completed_graph_quests = {
        quest_id: quest
        for quest_id, quest in graph_quests.items()
        if bool(quest.get("completed")) or _safe_str(quest.get("status")) == "completed"
    }
    active_graph_quests = {
        quest_id: quest
        for quest_id, quest in graph_quests.items()
        if not bool(quest.get("completed")) and _safe_str(quest.get("status")) == "active"
    }

    active_graph_objectives: List[Dict[str, Any]] = []
    for quest_id, quest in active_graph_quests.items():
        for objective in _safe_list(quest.get("objectives")):
            objective = _safe_dict(objective)
            if not bool(objective.get("completed")) and _safe_str(objective.get("status")) != "completed":
                active_graph_objectives.append(
                    {
                        "quest_id": quest_id,
                        "objective_id": _safe_str(objective.get("objective_id")),
                        "summary": _safe_str(objective.get("summary")),
                    }
                )

    remaining_node_ids = [
        node_id for node_id in expected_node_ids
        if node_id not in completed_nodes
    ]
    expected_node_count = len(expected_node_ids)
    completed_node_count = len(completed_node_ids)
    completed_node_count_for_active = len([node_id for node_id in expected_node_ids if node_id in completed_nodes])
    active_graph_complete = bool(
        expected_node_count > 0
        and completed_node_count_for_active >= expected_node_count
        and graph_quests
        and not active_graph_quests
        and not active_graph_objectives
    )
    arc_complete = active_graph_complete

    return {
        "ok": True,
        "graph_id": graph.graph_id if graph else "",
        "active_graph_id": graph.graph_id if graph else "",
        "active_graph_title": getattr(graph, "title", "") if graph else "",
        "graph_ids": graph_ids,
        "graph_count": len(graphs),
        "completed_graph_ids": completed_graph_ids,
        "completed_graph_count": len(completed_graph_ids),
        "scenario_seed": scenario_seed,
        "expected_node_count": expected_node_count,
        "all_expected_node_count": len(all_expected_node_ids),
        "completed_node_count": completed_node_count,
        "completed_node_ids": completed_node_ids,
        "remaining_node_ids": remaining_node_ids,
        "graph_quest_count": len(graph_quests),
        "completed_graph_quest_count": len(completed_graph_quests),
        "active_graph_quest_count": len(active_graph_quests),
        "active_graph_objective_count": len(active_graph_objectives),
        "active_graph_objectives": active_graph_objectives,
        "arc_complete": arc_complete,
        "campaign_graphs_complete": campaign_graphs_complete,
        "waiting_for_next_graph_pack": bool(state.get("scenario_progression_waiting_for_next_graph_pack")),
        "recommended_next_arc_bridge_action": (
            "I ask Garran what threat or lead we should follow next now that the wagon is safe."
            if arc_complete
            else ""
        ),
    }


def _arc_complete_idle_actions(state: Dict[str, Any], *, scenario_seed: str) -> List[Dict[str, Any]]:
    if _select_active_graph(state, scenario_seed=scenario_seed):
        return []

    arc = build_scenario_progression_arc_summary(state, scenario_seed=scenario_seed)
    if not arc.get("campaign_graphs_complete") and not arc.get("waiting_for_next_graph_pack"):
        return []
    return [
        {
            "action_id": "arc_complete_regroup",
            "node_id": "",
            "command": "I regroup with Garran and review what we learned from the ambush before choosing the next lead.",
            "semantic": "recap",
            "target_type": "npc",
            "target_id": "npc:garran",
            "priority": 40,
            "source": "scenario_progression_arc_complete_idle",
        },
        {
            "action_id": "arc_complete_ask_next_lead",
            "node_id": "",
            "command": "I ask Garran what threat or lead we should follow next now that the wagon is safe.",
            "semantic": "ask",
            "target_type": "npc",
            "target_id": "npc:garran",
            "priority": 39,
            "source": "scenario_progression_arc_complete_bridge",
        },
    ]


def synthesize_progression_actions_from_objectives(
    state: Dict[str, Any],
    *,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    objectives = _active_graph_objectives(state)
    actions = [_synthesize_action_for_graph_objective(obj) for obj in objectives]
    return actions[:limit]


def _node_quest_hint(state: Dict[str, Any], node: ProgressionNode) -> str:
    for effect in node.effects:
        quest_id = _safe_str(_safe_dict(effect).get("start_quest"))
        if quest_id:
            return quest_id
    return _infer_active_quest_id(state)


def _apply_effect(
    state: Dict[str, Any],
    effect: Dict[str, Any],
    *,
    quest_hint: str = "",
) -> Dict[str, Any]:
    effect = _safe_dict(effect)
    applied: Dict[str, Any] = {"effect": effect, "changed": False}

    if "unlock_fact" in effect:
        fact_id = _safe_str(effect["unlock_fact"])
        _facts(state)[fact_id] = {
            "fact_id": fact_id,
            "text": _safe_str(effect.get("text")),
            "source": "scenario_progression_graph",
        }
        applied["changed"] = True
    if "unlock_lead" in effect:
        lead_id = _safe_str(effect["unlock_lead"])
        _leads(state)[lead_id] = {
            "lead_id": lead_id,
            "text": _safe_str(effect.get("text")),
            "source": "scenario_progression_graph",
        }
        applied["changed"] = True
    if "unlock_npc" in effect:
        npc_id = _safe_str(effect["unlock_npc"])
        _unlocked_npcs(state)[npc_id] = {
            "npc_id": npc_id,
            "name": _safe_str(effect.get("name") or npc_id),
            "source": "scenario_progression_graph",
        }
        applied["changed"] = True
    if "unlock_location" in effect:
        location_id = _safe_str(effect["unlock_location"])
        _unlocked_locations(state)[location_id] = {
            "location_id": location_id,
            "name": _safe_str(effect.get("name") or location_id),
            "source": "scenario_progression_graph",
        }
        applied["changed"] = True
    if "start_quest" in effect:
        _ensure_quest(state, _safe_str(effect["start_quest"]), _safe_str(effect.get("title")))
        applied["changed"] = True
    if "unlock_objective" in effect:
        _ensure_objective(
            state,
            _safe_str(effect["unlock_objective"]),
            quest_id=quest_hint,
            summary=_safe_str(effect.get("summary")),
        )
        applied["changed"] = True
    if "advance_objective" in effect:
        obj = _ensure_objective(
            state,
            _safe_str(effect["advance_objective"]),
            quest_id=quest_hint,
        )
        obj["progress_count"] = int(obj.get("progress_count") or 0) + int(effect.get("amount") or 1)
        obj["status"] = "active"
        applied["changed"] = True
    if "complete_objective" in effect:
        _complete_objective(state, _safe_str(effect["complete_objective"]))
        applied["changed"] = True
    if "complete_quest" in effect:
        _complete_quest(state, _safe_str(effect["complete_quest"]))
        applied["changed"] = True
    if "set_location" in effect:
        location_id = _safe_str(effect["set_location"])
        state["current_location"] = location_id
        state["current_location_name"] = _safe_str(effect.get("name") or location_id)
        history = state.setdefault("location_history", [])
        if isinstance(history, list):
            history.append(
                {
                    "location_id": location_id,
                    "name": state["current_location_name"],
                    "source": "scenario_progression_graph",
                }
            )
            del history[:-50]
        _unlocked_locations(state)[location_id] = {
            "location_id": location_id,
            "name": state["current_location_name"],
            "source": "scenario_progression_graph",
        }
        applied["changed"] = True
    return applied


def apply_progression_for_action(
    runtime_state: Dict[str, Any],
    *,
    scenario_seed: str,
    player_action: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    start = time.perf_counter()
    state = _safe_dict(runtime_state)
    graph = _refresh_active_graph(state, scenario_seed=scenario_seed)
    if not graph:
        return {
            "ok": True,
            "changed": False,
            "state": state,
            "summary": {"reason": "no_graph"},
        }

    matched_nodes: List[Dict[str, Any]] = []
    applied_effects: List[Dict[str, Any]] = []
    for node in graph.nodes:
        if not node.repeatable and node.node_id in _nodes_completed(state):
            continue
        if not _node_available(state, node):
            continue
        if not any(_action_matches_pattern(player_action, pattern) for pattern in node.action_patterns):
            continue
        if not node.repeatable and node.node_id in _nodes_completed(state):
            continue
        _nodes_completed(state)[node.node_id] = {
            "node_id": node.node_id,
            "title": node.title,
            "turn": turn_index,
            "player_action": player_action,
        }
        matched_nodes.append({"node_id": node.node_id, "title": node.title})
        quest_hint = _node_quest_hint(state, node)
        for effect in node.effects:
            applied = _apply_effect(state, effect, quest_hint=quest_hint)
            if applied.get("changed"):
                applied_effects.append(applied)
        if not node.repeatable:
            break

    if any(node["node_id"] == "prepare_quarry_road" for node in matched_nodes):
        leads = _safe_dict(state.get("progression_leads"))
        quests = _safe_dict(_quest_progress(state).get("quests"))
        if "lead:leave_by_quarry_road" not in leads:
            raise RuntimeError("prepare_quarry_road_failed_to_unlock_leave_by_quarry_road")
        quarry_quest = _safe_dict(quests.get("quest:quarry_road_ambush"))
        if not quarry_quest or _safe_str(quarry_quest.get("status")) != "active":
            raise RuntimeError("prepare_quarry_road_failed_to_start_quarry_road_ambush")

    _mark_graph_complete_if_needed(state, graph)
    graph_after = _refresh_active_graph(state, scenario_seed=scenario_seed)

    elapsed_ms = int(round((time.perf_counter() - start) * 1000))
    if matched_nodes or applied_effects:
        _stamp_progression_revision(
            state,
            reason="apply_progression_for_action",
            turn_index=turn_index,
        )
    next_actions = get_active_progression_actions(
        state,
        scenario_seed=scenario_seed,
        limit=8,
    )
    graph_quest_ids = [
        quest_id for quest_id, quest in _safe_dict(_quest_progress(state).get("quests")).items()
        if _safe_str(_safe_dict(quest).get("source")) == "scenario_progression_graph"
    ]
    summary = {
        "ok": True,
        "changed": bool(matched_nodes or applied_effects),
        "graph_id": graph.graph_id,
        "active_graph_id": _safe_str(state.get("scenario_progression_active_graph_id")),
        "completed_graph_ids": _completed_graph_ids(state),
        "waiting_for_next_graph_pack": bool(state.get("scenario_progression_waiting_for_next_graph_pack")),
        "next_active_graph_id": _safe_str(getattr(graph_after, "graph_id", "")),
        "turn_index": turn_index,
        "progression_state_revision": int(state.get("progression_state_revision") or 0),
        "completed_node_count": len(_nodes_completed(state)),
        "fact_count": len(_facts(state)),
        "lead_count": len(_leads(state)),
        "matched_nodes": matched_nodes,
        "matched_node_ids": [_safe_str(row.get("node_id")) for row in matched_nodes],
        "applied_effect_count": len(applied_effects),
        "applied_effects": applied_effects[-20:],
        "next_action_ids": [_safe_str(row.get("action_id")) for row in next_actions],
        "graph_quest_ids": sorted(graph_quest_ids),
        "active_graph_objective_count": len(_active_graph_objectives(state)),
        "elapsed_ms": elapsed_ms,
    }
    if summary["changed"]:
        state["scenario_progression_quest_ids"] = sorted(graph_quest_ids)
        state["scenario_progression_quest_state"] = {
            quest_id: _safe_dict(_safe_dict(_quest_progress(state).get("quests")).get(quest_id))
            for quest_id in graph_quest_ids
        }
        _append_progression_log(state, summary)
        state["scenario_progression_summary"] = summary
        state["scenario_progression_current_turn_summary"] = summary
    else:
        state["scenario_progression_last_no_match"] = summary
        state["scenario_progression_current_turn_summary"] = summary
    return {"ok": True, "changed": bool(matched_nodes or applied_effects), "state": state, "summary": summary}