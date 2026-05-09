from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


PASSIVE_MICRO_ACTION_TERMS = (
    "listen",
    "watch",
    "observe",
    "wait",
    "nod",
    "maintain eye contact",
    "eye contact",
    "lean slightly",
    "lean in",
    "lower your voice",
    "ask for elaboration",
    "tell me more",
    "what else",
    "anything else",
)


PROGRESS_VERBS = (
    "report",
    "accept",
    "complete",
    "travel",
    "leave",
    "follow",
    "inspect",
    "search",
    "confront",
    "buy",
    "rent",
    "pay",
    "ask specifically",
    "ask directly",
)


VAGUE_OBJECTIVE_PATTERNS = (
    "current objective",
    "grounded way to make progress",
    "make progress on",
    "focus on the objective",
    "what they know",
    "anything that can help",
    "next concrete lead",
    "one concrete question",
)


def action_is_vague_objective(action: str) -> bool:
    lower = _safe_str(action).lower()
    return any(pattern in lower for pattern in VAGUE_OBJECTIVE_PATTERNS)


def concrete_action_for_objective_text(objective_text: str, *, target_hint: str = "Bran") -> str:
    text = _safe_str(objective_text).lower()
    target = _safe_str(target_hint).strip() or "Bran"
    if "find" in text and "witness" in text:
        return f"I ask {target} specifically where the witness was last seen, then inspect the tavern exit and street for the witness trail."
    if "report" in text and ("bran" in text or "findings" in text or "witness" in text):
        return "I report the witness findings to Bran clearly and ask what danger on the road this points toward."
    if "bandit" in text or "road" in text or "trail" in text:
        return "I leave the tavern and follow the bandit road trail, watching for tracks, ambush signs, or the next witness clue."
    return f"I ask {target} one specific question tied to the active quest, then take the next physical action the answer points toward."


def _recent_actions(transcript: List[Dict[str, Any]], *, limit: int = 12) -> List[str]:
    out: List[str] = []
    for row in _safe_list(transcript)[-max(1, int(limit or 12)):]:
        row = _safe_dict(row)
        action = _safe_str(row.get("player_action")).strip()
        if action:
            out.append(action)
    return out


def _active_objectives(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        _safe_dict(row)
        for row in _safe_list(_safe_dict(context).get("active_objectives"))
        if isinstance(row, dict)
    ]


def _suggested_actions(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        _safe_dict(row)
        for row in _safe_list(_safe_dict(context).get("suggested_actions"))
        if isinstance(row, dict)
    ]


def _nearby_npcs(context: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for row in _safe_list(_safe_dict(context).get("nearby_npcs")):
        row = _safe_dict(row)
        name = _safe_str(row.get("name") or row.get("npc_id")).strip()
        if name and name not in names:
            names.append(name)
    return names


def _passive_micro_action_rate(actions: List[str]) -> float:
    if not actions:
        return 0.0
    passive = 0
    for action in actions:
        lower = action.lower()
        if any(term in lower for term in PASSIVE_MICRO_ACTION_TERMS):
            passive += 1
    return passive / len(actions)


def _target_counts(transcript: List[Dict[str, Any]], *, limit: int = 20) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for row in _safe_list(transcript)[-max(1, int(limit or 20)):]:
        row = _safe_dict(row)
        pair = _safe_dict(row.get("canonical_semantic_pair"))
        target = _safe_str(pair.get("target"))
        if not target:
            action = _safe_str(row.get("player_action")).lower()
            for name in ("bran", "local patron", "cloaked traveler", "mira", "patron", "traveler"):
                if name in action:
                    target = name.title()
                    break
        if target:
            counts[target] += 1
    return dict(counts)


def build_goal_pressure_context(
    *,
    transcript: List[Dict[str, Any]],
    player_action_context: Dict[str, Any],
    progress_quality_metrics: Dict[str, Any],
    turn_index: int,
    no_change_streak_threshold: int = 8,
    passive_rate_threshold: float = 0.45,
) -> Dict[str, Any]:
    """Build deterministic director pressure for the player-agent.

    This is advisory only. It does not mutate authoritative simulation state.
    """
    progress = _safe_dict(progress_quality_metrics)
    recent = _recent_actions(transcript, limit=12)
    no_change_turns = int(progress.get("no_change_turns") or 0)
    turn_count = int(progress.get("turn_count") or len(transcript) or 0)
    meaningful_rate = float(progress.get("meaningful_progress_rate") or 0.0)
    passive_rate = _passive_micro_action_rate(recent)
    active_objectives = _active_objectives(player_action_context)
    suggested = _suggested_actions(player_action_context)
    completed_count = int(_safe_dict(player_action_context).get("quest_log_summary", {}).get("completed_count") or 0)
    active_count = int(_safe_dict(player_action_context).get("quest_log_summary", {}).get("active_count") or len(active_objectives))

    active = bool(
        turn_count >= 8
        and (
            meaningful_rate < 0.15
            or no_change_turns >= int(no_change_streak_threshold or 8)
            or passive_rate >= float(passive_rate_threshold or 0.45)
            or (turn_index >= 25 and active_count == 0)
        )
    )

    directives: List[str] = []
    if active:
        directives.extend(
            [
                "Do not spend the next turn in passive conversation, listening, nodding, watching, or asking for vague elaboration.",
                "Pick a concrete action that can change quest state, location, service state, or story arc state.",
                "Prefer: report objective progress, accept a lead, travel to the next place, inspect a physical clue, or ask a named NPC a specific objective question.",
            ]
        )
        if active_objectives:
            objective_text = _safe_str(active_objectives[0].get("objective_text") or active_objectives[0].get("title"))
            if objective_text:
                directives.append(f"Current objective to push: {objective_text}")
        else:
            directives.append("No active objective is visible: seek a new quest hook or travel toward the strongest known lead.")

    # Candidate deterministic actions for repair/fallback, ordered by preferred progress pressure.
    candidates: List[Dict[str, Any]] = []
    for action in suggested:
        category = _safe_str(action.get("category"))
        command = _safe_str(action.get("command"))
        lower = command.lower()
        score = int(action.get("strategy_score") or action.get("priority") or 0)
        if category in {"objective", "quest_log", "story_arc", "travel"}:
            score += 80
        if any(term in lower for term in PROGRESS_VERBS):
            score += 45
        if any(term in lower for term in PASSIVE_MICRO_ACTION_TERMS):
            score -= 80
        if command:
            row = dict(action)
            row["goal_pressure_score"] = score
            candidates.append(row)

    if not candidates:
        npcs = _nearby_npcs(player_action_context)
        target = npcs[0] if npcs else "the most relevant NPC"
        candidates.append(
            {
                "action_id": "goal_pressure:ask_specific_objective",
                "label": "Ask a specific objective question",
                "command": f"I ask {target} one specific question that can move the current quest forward, then prepare to act on the answer.",
                "category": "objective",
                "priority": 100,
                "goal_pressure_score": 100,
                "reason": "Goal-pressure fallback when no strong suggested action exists.",
            }
        )

    candidates.sort(key=lambda row: int(_safe_dict(row).get("goal_pressure_score") or 0), reverse=True)

    return {
        "active": active,
        "turn_index": int(turn_index or 0),
        "meaningful_progress_rate": meaningful_rate,
        "no_change_turns": no_change_turns,
        "passive_micro_action_rate": passive_rate,
        "recent_actions": recent[-8:],
        "target_counts": _target_counts(transcript, limit=20),
        "active_objective_count": active_count,
        "active_objectives": active_objectives[:5],
        "completed_objective_count": completed_count,
        "directives": directives,
        "candidate_actions": candidates[:6],
    }


def format_goal_pressure_prompt(context: Dict[str, Any]) -> str:
    context = _safe_dict(context)
    if not context.get("active"):
        return ""
    directives = [
        f"- {text}"
        for text in _safe_list(context.get("directives"))
        if _safe_str(text)
    ]
    candidates = [
        f"- {_safe_str(row.get('command'))}"
        for row in _safe_list(context.get("candidate_actions"))
        if _safe_str(_safe_dict(row).get("command"))
    ]
    return (
        "\n\nGOAL-PRESSURE DIRECTIVE:\n"
        f"Strict progress is low: meaningful_progress_rate={context.get('meaningful_progress_rate')}, "
        f"no_change_turns={context.get('no_change_turns')}, "
        f"passive_micro_action_rate={context.get('passive_micro_action_rate')}.\n"
        "Your next action should advance or complete quest/story progress, not continue micro-conversation.\n"
        + "\n".join(directives[:8])
        + "\nPreferred concrete actions:\n"
        + "\n".join(candidates[:6])
        + "\n"
    )


def action_violates_goal_pressure(action: str, context: Dict[str, Any]) -> bool:
    if not _safe_dict(context).get("active"):
        return False
    lower = _safe_str(action).lower()
    if not lower:
        return True
    has_progress_verb = any(term in lower for term in PROGRESS_VERBS)
    is_passive = any(term in lower for term in PASSIVE_MICRO_ACTION_TERMS)
    if action_is_vague_objective(lower):
        return True
    # Passive actions are allowed only when they also include concrete progress verbs.
    return bool(is_passive and not has_progress_verb)


def deterministic_goal_pressure_action(context: Dict[str, Any]) -> str:
    active_objectives = _safe_list(_safe_dict(context).get("active_objectives"))
    nearby_targets = list(_safe_dict(context).get("target_counts") or {})
    target_hint = nearby_targets[0] if nearby_targets else "Bran"
    for objective in active_objectives:
        objective = _safe_dict(objective)
        objective_text = _safe_str(
            objective.get("objective_text")
            or objective.get("summary")
            or objective.get("title")
        )
        if objective_text:
            return concrete_action_for_objective_text(objective_text, target_hint=target_hint)
    for row in _safe_list(_safe_dict(context).get("candidate_actions")):
        command = _safe_str(_safe_dict(row).get("command")).strip()
        if command and not action_is_vague_objective(command):
            return command
    return "I leave the tavern and follow the strongest witness or road lead, searching for concrete clues that can advance the quest."