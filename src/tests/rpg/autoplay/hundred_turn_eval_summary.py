from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.autoplay.hundred_turn_eval import (
    _safe_dict,
    summarize_action_diversity,
    summarize_long_run_warnings,
    summarize_progress_timeline,
)


def summarize_hundred_turn_eval(
    *,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    turns_for_strict_gates: int = 100,
) -> Dict[str, Any]:
    action = summarize_action_diversity(transcript)
    progress = summarize_progress_timeline(transcript)
    warnings = summarize_long_run_warnings(
        transcript=transcript,
        action_diversity_summary=action,
        progress_timeline_summary=progress,
        console_log_summary=_safe_dict(summary.get("console_log_summary")),
        manual_turn_error_summary=_safe_dict(summary.get("manual_turn_error_summary")),
        turns_for_strict_gates=turns_for_strict_gates,
    )
    turn_count = len(transcript if isinstance(transcript, list) else [])
    return {
        "ok": bool(warnings.get("ok")),
        "turn_count": turn_count,
        "strict_100_turn_mode": turn_count >= turns_for_strict_gates,
        "readiness": "strict" if turn_count >= turns_for_strict_gates else "smoke",
        "action_diversity_summary": action,
        "progress_timeline_summary": progress,
        "long_run_warning_summary": warnings,
    }
