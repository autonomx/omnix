from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


DEFAULT_STRATEGY_PROFILE = "balanced_story_player"


STRATEGY_PROFILES: Dict[str, Dict[str, Any]] = {
    "balanced_story_player": {
        "profile_id": "balanced_story_player",
        "description": "Balance objective pursuit, NPC interaction, exploration, and cautious escalation.",
        "category_weights": {
            "objective": 90,
            "social": 75,
            "exploration": 70,
            "story_arc": 68,
            "quest_log": 55,
            "travel": 50,
            "service": 45,
            "combat": 40,
        },
        "anti_stall_priority_order": [
            "change_category",
            "ask_different_npc",
            "explore_location",
            "inspect_clues",
            "travel_or_leave",
            "review_quest_log",
        ],
    },
    "objective_rusher": {
        "profile_id": "objective_rusher",
        "description": "Prefer direct objective progress, asking NPCs or investigating only when it helps the current objective.",
        "category_weights": {
            "objective": 100,
            "social": 72,
            "story_arc": 70,
            "exploration": 58,
            "quest_log": 55,
            "travel": 45,
            "service": 35,
            "combat": 35,
        },
        "anti_stall_priority_order": [
            "try_new_objective_angle",
            "ask_specific_witness_question",
            "inspect_clues",
            "change_category",
            "travel_or_leave",
        ],
    },
    "explorer": {
        "profile_id": "explorer",
        "description": "Prefer observing, inspecting, moving through the world, and uncovering grounded leads.",
        "category_weights": {
            "exploration": 100,
            "travel": 80,
            "story_arc": 72,
            "social": 65,
            "objective": 62,
            "quest_log": 45,
            "service": 35,
            "combat": 30,
        },
        "anti_stall_priority_order": [
            "explore_location",
            "inspect_clues",
            "travel_or_leave",
            "change_category",
            "ask_different_npc",
        ],
    },
    "social_investigator": {
        "profile_id": "social_investigator",
        "description": "Prefer talking to NPCs, asking follow-up questions, comparing rumors, and building social context.",
        "category_weights": {
            "social": 100,
            "objective": 78,
            "story_arc": 72,
            "exploration": 62,
            "quest_log": 50,
            "service": 45,
            "travel": 40,
            "combat": 25,
        },
        "anti_stall_priority_order": [
            "ask_different_npc",
            "ask_more_specific_question",
            "change_category",
            "explore_location",
            "review_quest_log",
        ],
    },
    "chaos_monkey_safe": {
        "profile_id": "chaos_monkey_safe",
        "description": "Prefer diverse, surprising but still safe and valid actions. Does not decide outcomes or invent rewards.",
        "category_weights": {
            "exploration": 88,
            "social": 85,
            "objective": 80,
            "story_arc": 78,
            "travel": 70,
            "service": 55,
            "quest_log": 50,
            "combat": 35,
        },
        "anti_stall_priority_order": [
            "change_category",
            "try_unusual_safe_action",
            "travel_or_leave",
            "inspect_clues",
            "ask_different_npc",
        ],
    },
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def get_strategy_profile(profile_id: str) -> Dict[str, Any]:
    profile_id = str(profile_id or DEFAULT_STRATEGY_PROFILE)
    return dict(STRATEGY_PROFILES.get(profile_id) or STRATEGY_PROFILES[DEFAULT_STRATEGY_PROFILE])


def list_strategy_profile_ids() -> List[str]:
    return sorted(STRATEGY_PROFILES.keys())


def normalize_action_text(text: str) -> str:
    return " ".join(str(text or "").lower().strip().split())


def action_diversity_metrics(transcript: List[Dict[str, Any]], *, window: int = 12) -> Dict[str, Any]:
    rows = [
        row
        for row in transcript[-max(1, int(window or 12)) :]
        if isinstance(row, dict)
    ]
    actions = [
        normalize_action_text(row.get("player_action"))
        for row in rows
        if normalize_action_text(row.get("player_action"))
    ]
    categories = []
    for row in rows:
        selected = _safe_dict(row.get("selected_player_action"))
        context = _safe_dict(row.get("player_action_context"))
        source_action_id = _safe_str(selected.get("source_action_id"))
        selected_category = _safe_str(selected.get("category"))
        if selected_category:
            categories.append(selected_category)
            continue
        for suggestion in _safe_list(context.get("suggested_actions")):
            suggestion = _safe_dict(suggestion)
            if source_action_id and suggestion.get("action_id") == source_action_id:
                category = _safe_str(suggestion.get("category"))
                if category:
                    categories.append(category)
                break

    action_counts = Counter(actions)
    category_counts = Counter(categories)
    repeated_actions = {
        action: count
        for action, count in action_counts.items()
        if count > 1
    }
    return {
        "window": int(window or 12),
        "action_count": len(actions),
        "unique_action_count": len(action_counts),
        "action_diversity_rate": (len(action_counts) / len(actions)) if actions else 1.0,
        "repeated_actions": repeated_actions,
        "category_counts": dict(category_counts),
        "unique_category_count": len(category_counts),
        "category_diversity_rate": (len(category_counts) / len(categories)) if categories else 1.0,
        "last_action": actions[-1] if actions else "",
        "last_category": categories[-1] if categories else "",
    }


def build_strategy_guidance(
    *,
    strategy: str,
    progress_quality_metrics: Dict[str, Any] | None = None,
    diversity_metrics: Dict[str, Any] | None = None,
    recent_transcript: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    profile = get_strategy_profile(strategy)
    progress_quality_metrics = _safe_dict(progress_quality_metrics)
    diversity_metrics = _safe_dict(diversity_metrics)
    recent_transcript = recent_transcript or []

    churn_streak = int(progress_quality_metrics.get("churn_only_streak") or 0)
    objective_stall_streak = int(progress_quality_metrics.get("objective_target_no_meaningful_progress_streak") or 0)
    diversity_rate = float(diversity_metrics.get("action_diversity_rate") or 1.0)
    repeated_actions = _safe_dict(diversity_metrics.get("repeated_actions"))

    anti_stall_active = bool(
        churn_streak >= 3
        or objective_stall_streak >= 3
        or diversity_rate < 0.75
        or repeated_actions
    )

    recent_actions = [
        _safe_str(row.get("player_action"))
        for row in recent_transcript[-8:]
        if _safe_str(row.get("player_action"))
    ]

    hints: List[str] = []
    if anti_stall_active:
        hints.append("Do not repeat the same action or same question.")
        hints.append("Choose a different action category than the last repeated pattern when possible.")
        hints.append("If an objective-focused action has not produced meaningful progress, try a new angle: inspect, ask a different NPC, move location, or review clues.")
    else:
        hints.append("Prefer active objectives, but vary your approach when recent turns did not advance the story.")

    return {
        "strategy_profile": profile,
        "anti_stall_active": anti_stall_active,
        "anti_stall_reasons": {
            "churn_only_streak": churn_streak,
            "objective_target_no_meaningful_progress_streak": objective_stall_streak,
            "action_diversity_rate": diversity_rate,
            "repeated_actions": repeated_actions,
        },
        "recent_actions_to_avoid_repeating": recent_actions,
        "hints": hints,
        "anti_stall_priority_order": list(profile.get("anti_stall_priority_order") or []),
    }


def rerank_suggested_actions_for_strategy(
    suggested_actions: List[Dict[str, Any]],
    *,
    strategy: str,
    recent_transcript: List[Dict[str, Any]] | None = None,
    progress_quality_metrics: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    profile = get_strategy_profile(strategy)
    category_weights = _safe_dict(profile.get("category_weights"))
    recent_transcript = recent_transcript or []
    progress_quality_metrics = _safe_dict(progress_quality_metrics)
    recent_actions = [
        normalize_action_text(row.get("player_action"))
        for row in recent_transcript[-8:]
        if normalize_action_text(row.get("player_action"))
    ]
    recent_counts = Counter(recent_actions)
    churn_streak = int(progress_quality_metrics.get("churn_only_streak") or 0)
    objective_stall_streak = int(progress_quality_metrics.get("objective_target_no_meaningful_progress_streak") or 0)
    anti_stall = churn_streak >= 3 or objective_stall_streak >= 3

    ranked = []
    for index, action in enumerate(suggested_actions):
        action = dict(action)
        category = _safe_str(action.get("category"))
        command = normalize_action_text(action.get("command"))
        base_priority = int(action.get("priority") or 0)
        category_weight = int(category_weights.get(category, 50))
        repeat_penalty = recent_counts.get(command, 0) * (40 if anti_stall else 20)
        objective_penalty = 0
        if anti_stall and category == "objective":
            objective_penalty = 12
        diversity_bonus = 10 if anti_stall and category in {"exploration", "social", "travel", "story_arc"} else 0
        strategy_score = base_priority + category_weight + diversity_bonus - repeat_penalty - objective_penalty
        action["strategy_score"] = strategy_score
        action["strategy_profile_id"] = profile["profile_id"]
        action["repeat_penalty"] = repeat_penalty
        action["anti_stall_applied"] = anti_stall
        ranked.append((strategy_score, -index, action))

    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked]