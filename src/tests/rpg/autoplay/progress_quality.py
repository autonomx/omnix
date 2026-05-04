from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


MEANINGFUL_PROGRESS_CATEGORIES = {
    "milestone_added",
    "milestone_completed",
    "arc_stage_changed",
    "objective_added",
    "objective_completed",
    "quest_log_changed",
    "location_changed",
    "npc_relationship_changed",
    "npc_arc_changed",
    "combat_started",
    "combat_ended",
    "service_completed",
    "story_event_queued",
    "story_event_resolved",
}


WEAK_PROGRESS_CATEGORIES = {
    # A journal entry can be meaningful when paired with arc/objective/story
    # progress, but generic per-turn journal/memory entries must not make a
    # stalled post-objective run look healthy forever.
    "journal_entry_added",
}


CHURN_ONLY_CATEGORIES = {
    "state_changed",
    "memory_changed",
    "presentation_changed",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _objective_ids_from_context(context: Dict[str, Any]) -> List[str]:
    ids = []
    for row in _safe_list(_safe_dict(context).get("active_objectives")):
        row = _safe_dict(row)
        objective_id = _safe_str(row.get("objective_id"))
        if objective_id:
            ids.append(objective_id)
    return ids


def classify_turn_progress_quality(row: Dict[str, Any]) -> Dict[str, Any]:
    progress_delta = _safe_dict(row.get("progress_delta"))
    categories = [
        str(category)
        for category in _safe_list(progress_delta.get("categories"))
        if category
    ]
    strong_meaningful = sorted([c for c in categories if c in MEANINGFUL_PROGRESS_CATEGORIES])
    weak_progress = sorted([c for c in categories if c in WEAK_PROGRESS_CATEGORIES])
    meaningful = list(strong_meaningful)
    if strong_meaningful and weak_progress:
        meaningful.extend(weak_progress)
    churn_only = sorted([c for c in categories if c in CHURN_ONLY_CATEGORIES])
    unknown = sorted(
        [
            c
            for c in categories
            if c not in MEANINGFUL_PROGRESS_CATEGORIES
            and c not in WEAK_PROGRESS_CATEGORIES
            and c not in CHURN_ONLY_CATEGORIES
        ]
    )

    context = _safe_dict(row.get("player_action_context"))
    selected = _safe_dict(row.get("selected_player_action"))
    player_action = _safe_str(row.get("player_action")).strip()
    goal_id = _safe_str(selected.get("goal_id")) or _safe_str(selected.get("objective_id"))
    active_objective_ids = _objective_ids_from_context(context)

    objective_targeted = bool(goal_id) or any(
        objective_id and objective_id in player_action
        for objective_id in active_objective_ids
    )

    if strong_meaningful:
        quality = "meaningful_progress"
    elif weak_progress:
        quality = "weak_progress"
    elif categories and all(c in CHURN_ONLY_CATEGORIES for c in categories):
        quality = "churn_only"
    elif categories:
        quality = "uncategorized_change"
    else:
        quality = "no_change"

    return {
        "quality": quality,
        "meaningful": meaningful,
        "strong_meaningful": strong_meaningful,
        "weak_progress": weak_progress,
        "churn_only": churn_only,
        "unknown": unknown,
        "categories": categories,
        "objective_targeted": objective_targeted,
        "goal_id": goal_id,
        "active_objective_ids": active_objective_ids,
        "player_action": player_action,
    }


def _normalized_action(row: Dict[str, Any]) -> str:
    return " ".join(_safe_str(row.get("player_action")).lower().split())


def repeated_action_streak(transcript: List[Dict[str, Any]]) -> int:
    actions = [_normalized_action(row) for row in transcript if _normalized_action(row)]
    if not actions:
        return 0
    last = actions[-1]
    streak = 0
    for action in reversed(actions):
        if action == last:
            streak += 1
        else:
            break
    return streak


def objective_target_no_meaningful_progress_streak(transcript: List[Dict[str, Any]]) -> int:
    streak = 0
    for row in reversed(transcript):
        quality = _safe_dict(row.get("progress_quality"))
        if quality.get("meaningful"):
            break
        if quality.get("objective_targeted"):
            streak += 1
            continue
        break
    return streak


def churn_only_streak(transcript: List[Dict[str, Any]]) -> int:
    streak = 0
    for row in reversed(transcript):
        quality = _safe_dict(row.get("progress_quality"))
        if quality.get("quality") == "churn_only":
            streak += 1
            continue
        break
    return streak


def compute_progress_quality_metrics(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    quality_counts = Counter()
    meaningful_category_counts = Counter()
    churn_category_counts = Counter()
    weak_category_counts = Counter()
    unknown_category_counts = Counter()
    targeted_objective_turns = 0
    targeted_objective_meaningful_turns = 0

    for row in transcript:
        quality = _safe_dict(row.get("progress_quality"))
        if not quality:
            quality = classify_turn_progress_quality(row)
        quality_counts[str(quality.get("quality") or "unknown")] += 1
        for category in _safe_list(quality.get("meaningful")):
            meaningful_category_counts[str(category)] += 1
        for category in _safe_list(quality.get("churn_only")):
            churn_category_counts[str(category)] += 1
        for category in _safe_list(quality.get("weak_progress")):
            weak_category_counts[str(category)] += 1
        for category in _safe_list(quality.get("unknown")):
            unknown_category_counts[str(category)] += 1
        if quality.get("objective_targeted"):
            targeted_objective_turns += 1
            if quality.get("meaningful"):
                targeted_objective_meaningful_turns += 1

    turn_count = len(transcript)
    meaningful_turns = int(quality_counts.get("meaningful_progress") or 0)
    churn_turns = int(quality_counts.get("churn_only") or 0)
    weak_turns = int(quality_counts.get("weak_progress") or 0)
    no_change_turns = int(quality_counts.get("no_change") or 0)

    return {
        "turn_count": turn_count,
        "quality_counts": dict(quality_counts),
        "meaningful_turns": meaningful_turns,
        "churn_only_turns": churn_turns,
        "weak_progress_turns": weak_turns,
        "no_change_turns": no_change_turns,
        "meaningful_progress_rate": (meaningful_turns / turn_count) if turn_count else 0.0,
        "churn_only_rate": (churn_turns / turn_count) if turn_count else 0.0,
        "weak_progress_rate": (weak_turns / turn_count) if turn_count else 0.0,
        "targeted_objective_turns": targeted_objective_turns,
        "targeted_objective_meaningful_turns": targeted_objective_meaningful_turns,
        "targeted_objective_meaningful_rate": (
            targeted_objective_meaningful_turns / targeted_objective_turns
            if targeted_objective_turns
            else 0.0
        ),
        "meaningful_category_counts": dict(meaningful_category_counts),
        "churn_category_counts": dict(churn_category_counts),
        "weak_category_counts": dict(weak_category_counts),
        "unknown_category_counts": dict(unknown_category_counts),
        "repeated_action_streak": repeated_action_streak(transcript),
        "objective_target_no_meaningful_progress_streak": objective_target_no_meaningful_progress_streak(transcript),
        "churn_only_streak": churn_only_streak(transcript),
    }


def evaluate_progress_quality_health(
    transcript: List[Dict[str, Any]],
    *,
    min_meaningful_progress_rate: float = 0.0,
    max_churn_only_rate: float = 1.0,
    max_churn_only_streak: int = 0,
    max_objective_target_no_progress_streak: int = 0,
) -> Dict[str, Any]:
    metrics = compute_progress_quality_metrics(transcript)
    warnings: List[str] = []

    if (
        min_meaningful_progress_rate > 0
        and float(metrics.get("meaningful_progress_rate") or 0.0) < min_meaningful_progress_rate
    ):
        warnings.append("meaningful_progress_rate_below_threshold")
    if (
        max_churn_only_rate < 1.0
        and float(metrics.get("churn_only_rate") or 0.0) > max_churn_only_rate
    ):
        warnings.append("churn_only_rate_exceeded")
    if (
        max_churn_only_streak > 0
        and int(metrics.get("churn_only_streak") or 0) > max_churn_only_streak
    ):
        warnings.append("churn_only_streak_exceeded")
    if (
        max_objective_target_no_progress_streak > 0
        and int(metrics.get("objective_target_no_meaningful_progress_streak") or 0)
        > max_objective_target_no_progress_streak
    ):
        warnings.append("objective_target_no_progress_streak_exceeded")

    return {
        "ok": not warnings,
        "warnings": warnings,
        "metrics": metrics,
    }


def post_objective_false_progress_warnings(transcript: List[Dict[str, Any]]) -> List[str]:
    """Warn if only weak journal progress happens after all objectives complete."""
    warnings: List[str] = []
    seen_no_active_objectives = False
    weak_after_completion = 0
    meaningful_after_completion = 0

    for row in transcript:
        context = _safe_dict(row.get("player_action_context"))
        active = _safe_list(context.get("active_objectives"))
        quality = _safe_dict(row.get("progress_quality"))
        if not active:
            seen_no_active_objectives = True
            if quality.get("quality") == "weak_progress":
                weak_after_completion += 1
            if quality.get("quality") == "meaningful_progress":
                meaningful_after_completion += 1

    if seen_no_active_objectives and weak_after_completion > 0 and meaningful_after_completion == 0:
        warnings.append("post_objective_weak_progress_only")
    return warnings