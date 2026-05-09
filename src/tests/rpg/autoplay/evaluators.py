from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from tests.rpg.autoplay.progress import no_progress_streak
from tests.rpg.autoplay.progress_quality import compute_progress_quality_metrics
from tests.rpg.autoplay.strategy_profiles import action_diversity_metrics


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def repeated_npc_line_metrics(transcript: List[Dict[str, Any]], *, streak_threshold: int = 3) -> Dict[str, Any]:
    max_streak = 0
    max_value = ""
    current = ""
    streak = 0
    counts: Dict[str, int] = {}

    for row in transcript:
        row = _safe_dict(row)
        npc = _safe_dict(row.get("npc"))
        speaker = _safe_str(npc.get("speaker") or row.get("npc_speaker"))
        line = _safe_str(npc.get("line") or row.get("npc_line"))
        value = f"{speaker}: {line}" if speaker and line else ""
        if not value:
            current = ""
            streak = 0
            continue
        counts[value] = counts.get(value, 0) + 1
        if value == current:
            streak += 1
        else:
            current = value
            streak = 1
        if streak > max_streak:
            max_streak = streak
            max_value = value

    repeated = sorted(
        [{"value": key, "count": count} for key, count in counts.items() if count >= streak_threshold],
        key=lambda row: int(row["count"]),
        reverse=True,
    )
    return {
        "ok": max_streak < int(streak_threshold or 3),
        "max_streak": max_streak,
        "max_value": max_value,
        "repeated": repeated[:10],
        "streak_threshold": int(streak_threshold or 3),
    }


def detect_repeated_action_loop(
    transcript: List[Dict[str, Any]],
    *,
    max_repeated_actions: int = 5,
) -> Dict[str, Any]:
    if max_repeated_actions <= 0:
        return {"ok": True, "reason": "disabled"}
    actions = [
        _safe_str(row.get("player_action")).strip().lower()
        for row in transcript
        if _safe_str(row.get("player_action")).strip()
    ]
    if not actions:
        return {"ok": True, "reason": "no_actions"}

    streak = 1
    last = actions[-1]
    for previous in reversed(actions[:-1]):
        if previous == last:
            streak += 1
        else:
            break
    if streak > max_repeated_actions:
        return {
            "ok": False,
            "reason": "repeated_action_loop",
            "action": last,
            "streak": streak,
            "max_repeated_actions": max_repeated_actions,
        }
    return {
        "ok": True,
        "reason": "no_repeated_action_loop",
        "action": last,
        "streak": streak,
    }


def compute_progress_metrics(
    transcript: List[Dict[str, Any]],
    *,
    latest_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    latest_context = latest_context or {}
    action_categories = Counter()
    fallback_count = 0
    player_agent_exception_count = 0
    invalid_player_agent_count = 0
    runtime_error_count = 0
    compatibility_turn_runtime_count = 0
    real_turn_runtime_count = 0
    progress_category_counts = Counter()
    checkpoint_count = 0
    checkpoint_failure_count = 0
    state_bound_warning_count = 0
    max_state_size_bytes_seen = 0
    story_hook_fire_count = 0
    story_hook_ids = []

    narration_missing_count = 0

    for row in transcript:
        selected = _safe_dict(row.get("selected_player_action"))
        if selected.get("fallback"):
            fallback_count += 1
        if selected.get("player_agent_exception"):
            player_agent_exception_count += 1
        if not selected.get("ok"):
            invalid_player_agent_count += 1
        if row.get("runtime_error"):
            runtime_error_count += 1
        if _safe_dict(row.get("turn_result")).get("compatibility_turn_runtime"):
            compatibility_turn_runtime_count += 1
        if _safe_dict(row.get("turn_result")).get("runtime_name"):
            real_turn_runtime_count += 1
        if not _safe_str(row.get("narration")):
            narration_missing_count += 1
        for category in _safe_list(_safe_dict(row.get("progress_delta")).get("categories")):
            if category:
                progress_category_counts[str(category)] += 1
        checkpoint = _safe_dict(row.get("save_load_checkpoint"))
        if checkpoint:
            checkpoint_count += 1
            if checkpoint.get("ok") is not True:
                checkpoint_failure_count += 1
        bounds = _safe_dict(row.get("state_bounds"))
        if bounds:
            max_state_size_bytes_seen = max(
                max_state_size_bytes_seen,
                int(bounds.get("state_size_bytes") or 0),
            )
            if bounds.get("warnings"):
                state_bound_warning_count += 1
        hook_result = _safe_dict(row.get("story_hook_result"))
        for fired in _safe_list(hook_result.get("fired_hooks")):
            fired = _safe_dict(fired)
            story_hook_fire_count += 1
            if fired.get("hook_id"):
                story_hook_ids.append(str(fired.get("hook_id")))
        for action in _safe_list(_safe_dict(row.get("player_action_context")).get("suggested_actions")):
            category = _safe_str(_safe_dict(action).get("category"))
            if category:
                action_categories[category] += 1

    quest_summary = _safe_dict(latest_context.get("quest_log_summary"))
    progress_quality_metrics = compute_progress_quality_metrics(transcript)
    diversity_metrics = action_diversity_metrics(transcript)
    return {
        "turn_count": len(transcript),
        "fallback_player_actions": fallback_count,
        "fallback_player_action_rate": (fallback_count / len(transcript)) if transcript else 0.0,
        "player_agent_exception_count": player_agent_exception_count,
        "invalid_player_agent_responses": invalid_player_agent_count,
        "runtime_errors": runtime_error_count,
        "compatibility_turn_runtime_count": compatibility_turn_runtime_count,
        "real_turn_runtime_count": real_turn_runtime_count,
        "narration_missing_count": narration_missing_count,
        "progress_category_counts": dict(progress_category_counts),
        "no_progress_streak": no_progress_streak(transcript),
        "checkpoint_count": checkpoint_count,
        "checkpoint_failure_count": checkpoint_failure_count,
        "state_bound_warning_count": state_bound_warning_count,
        "max_state_size_bytes_seen": max_state_size_bytes_seen,
        "story_hook_fire_count": story_hook_fire_count,
        "story_hook_ids": story_hook_ids,
        "progress_quality": progress_quality_metrics,
        "action_diversity": diversity_metrics,
        "suggested_action_category_counts": dict(action_categories),
        "latest_active_objective_count": int(quest_summary.get("active_count") or 0),
        "latest_completed_objective_count": int(quest_summary.get("completed_count") or 0),
        "latest_suggested_action_count": len(_safe_list(latest_context.get("suggested_actions"))),
    }


def evaluate_autoplay_health(
    transcript: List[Dict[str, Any]],
    *,
    latest_context: Dict[str, Any] | None = None,
    max_repeated_actions: int = 5,
    max_runtime_errors: int = 0,
    allow_compatibility_turn_runtime: bool = True,
    max_player_agent_fallback_rate: float = 1.0,
    max_no_progress_turns: int = 0,
    fail_on_checkpoint_failure: bool = True,
    fail_on_state_bound_warnings: bool = True,
    min_action_diversity_rate: float = 0.0,
    min_category_diversity_rate: float = 0.0,
) -> Dict[str, Any]:
    loop = detect_repeated_action_loop(
        transcript,
        max_repeated_actions=max_repeated_actions,
    )
    metrics = compute_progress_metrics(transcript, latest_context=latest_context)
    warnings: List[str] = []

    if not loop.get("ok"):
        warnings.append(str(loop.get("reason")))
    if metrics["runtime_errors"] > max_runtime_errors:
        warnings.append("runtime_error_limit_exceeded")
    if (
        not allow_compatibility_turn_runtime
        and metrics.get("compatibility_turn_runtime_count", 0) > 0
    ):
        warnings.append("compatibility_turn_runtime_used")
    if float(metrics.get("fallback_player_action_rate") or 0.0) > float(max_player_agent_fallback_rate):
        warnings.append("player_agent_fallback_rate_exceeded")
    if max_no_progress_turns > 0 and int(metrics.get("no_progress_streak") or 0) > max_no_progress_turns:
        warnings.append("no_progress_turn_limit_exceeded")
    if fail_on_checkpoint_failure and int(metrics.get("checkpoint_failure_count") or 0) > 0:
        warnings.append("save_load_checkpoint_failed")
    if fail_on_state_bound_warnings and int(metrics.get("state_bound_warning_count") or 0) > 0:
        warnings.append("state_bounds_warning")
    diversity = _safe_dict(metrics.get("action_diversity"))
    if (
        min_action_diversity_rate > 0
        and float(diversity.get("action_diversity_rate") or 0.0) < min_action_diversity_rate
    ):
        warnings.append("action_diversity_rate_below_threshold")
    if (
        min_category_diversity_rate > 0
        and float(diversity.get("category_diversity_rate") or 0.0) < min_category_diversity_rate
    ):
        warnings.append("category_diversity_rate_below_threshold")
    if metrics["latest_suggested_action_count"] == 0:
        warnings.append("no_suggested_actions")

    return {
        "ok": not warnings,
        "warnings": warnings,
        "loop": loop,
        "metrics": metrics,
    }


def repeated_npc_line_metrics(transcript: List[Dict[str, Any]], *, streak_threshold: int = 3) -> Dict[str, Any]:
    max_streak = 0
    max_value = ""
    current = ""
    streak = 0
    counts: Dict[str, int] = {}
    for row in transcript:
        npc = _safe_dict(row.get("npc"))
        speaker = _safe_str(npc.get("speaker"))
        line = _safe_str(npc.get("line"))
        value = f"{speaker}: {line}" if speaker and line else ""
        if not value:
            current = ""
            streak = 0
            continue
        counts[value] = counts.get(value, 0) + 1
        if value == current:
            streak += 1
        else:
            current = value
            streak = 1
        if streak > max_streak:
            max_streak = streak
            max_value = value
    repeated = sorted(
        [{"value": key, "count": count} for key, count in counts.items() if count >= streak_threshold],
        key=lambda row: int(row["count"]),
        reverse=True,
    )
    return {
        "ok": max_streak < int(streak_threshold or 3),
        "max_streak": max_streak,
        "max_value": max_value,
        "repeated": repeated[:10],
        "streak_threshold": int(streak_threshold or 3),
    }