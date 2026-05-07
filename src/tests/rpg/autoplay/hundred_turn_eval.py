from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _turn_index(row: Dict[str, Any], fallback: int) -> int:
    try:
        return int(_safe_dict(row).get("turn_index") or fallback)
    except Exception:
        return fallback


def _player_action(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    selected = _safe_dict(row.get("selected_player_action"))
    return (
        _safe_str(row.get("player_action"))
        or _safe_str(row.get("player_input"))
        or _safe_str(selected.get("action"))
        or _safe_str(_safe_dict(row.get("turn_contract")).get("player_input"))
        or _safe_str(_safe_dict(row.get("turn_contract")).get("action"))
    )


def _semantic_action(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    contract = _safe_dict(row.get("turn_contract"))
    semantic = _safe_dict(contract.get("semantic_action"))
    resolved = _safe_dict(contract.get("resolved_action"))
    selected = _safe_dict(row.get("selected_player_action"))
    return (
        _safe_str(semantic.get("type"))
        or _safe_str(semantic.get("kind"))
        or _safe_str(resolved.get("type"))
        or _safe_str(resolved.get("kind"))
        or _safe_str(selected.get("semantic_action_type"))
        or _safe_str(row.get("semantic_action_type"))
        or "unknown"
    )


def _target(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    contract = _safe_dict(row.get("turn_contract"))
    semantic = _safe_dict(contract.get("semantic_action"))
    resolved = _safe_dict(contract.get("resolved_action"))
    selected = _safe_dict(row.get("selected_player_action"))
    return (
        _safe_str(semantic.get("target"))
        or _safe_str(semantic.get("target_id"))
        or _safe_str(resolved.get("target"))
        or _safe_str(resolved.get("target_id"))
        or _safe_str(selected.get("target"))
        or ""
    )


def _result_reason(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    contract = _safe_dict(row.get("turn_contract"))
    resolved = _safe_dict(contract.get("resolved_result"))
    service = _safe_dict(contract.get("service_result"))
    turn_result = _safe_dict(row.get("turn_result"))
    return (
        _safe_str(resolved.get("reason"))
        or _safe_str(resolved.get("code"))
        or _safe_str(service.get("reason"))
        or _safe_str(turn_result.get("reason"))
        or _safe_str(turn_result.get("error"))
        or ""
    )


def _location(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    state_candidates = [
        _safe_dict(row.get("simulation_state")),
        _safe_dict(row.get("final_authoritative_state")),
        _safe_dict(_safe_dict(row.get("turn_result")).get("simulation_state")),
        _safe_dict(_safe_dict(_safe_dict(row.get("turn_result")).get("session")).get("simulation_state")),
    ]
    for state in state_candidates:
        for key in ("location", "current_location", "scene_id"):
            value = _safe_str(state.get(key))
            if value:
                return value
        scene = _safe_dict(state.get("scene"))
        value = _safe_str(scene.get("id") or scene.get("scene_id") or scene.get("title") or scene.get("name"))
        if value:
            return value
    contract = _safe_dict(row.get("turn_contract"))
    resolved = _safe_dict(contract.get("resolved_result"))
    location_state = _safe_dict(resolved.get("location_state"))
    current = _safe_dict(location_state.get("current_location"))
    return _safe_str(current.get("id") or current.get("title") or current.get("name"))


def _has_story_beat(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)
    if _safe_str(row.get("narration")):
        return True
    if _safe_dict(row.get("combined_background_llm_result")).get("narration"):
        return True
    if _safe_dict(row.get("story_hook_result")):
        return True
    if _safe_dict(row.get("progress_delta")):
        return True
    contract = _safe_dict(row.get("turn_contract"))
    if _safe_dict(contract.get("state_delta")):
        return True
    if _safe_dict(contract.get("resolved_result")).get("summary"):
        return True
    return False


def _quest_count(row: Dict[str, Any]) -> int:
    row = _safe_dict(row)
    runtime = _safe_dict(row.get("runtime_state"))
    quest_progress = _safe_dict(runtime.get("quest_progress"))
    quests = _safe_dict(quest_progress.get("quests"))
    return len(quests)


def _journal_entry_count(row: Dict[str, Any]) -> int:
    row = _safe_dict(row)
    runtime = _safe_dict(row.get("runtime_state"))
    journal = _safe_dict(runtime.get("player_journal"))
    return len(_safe_list(journal.get("entries")))


def _npc_signal_count(row: Dict[str, Any]) -> int:
    row = _safe_dict(row)
    runtime = _safe_dict(row.get("runtime_state"))
    evo = _safe_dict(runtime.get("npc_evolution"))
    return len(_safe_list(evo.get("signals")))


def _manual_error(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    return (
        _safe_str(row.get("runtime_error"))
        or _safe_str(_safe_dict(row.get("manual_turn_summary")).get("error"))
        or _safe_str(_safe_dict(row.get("turn_result")).get("error"))
    )


def _is_noop_reason(reason: str) -> bool:
    lower = _safe_str(reason).lower()
    if not lower:
        return False
    return any(
        token in lower
        for token in (
            "target_not_found",
            "no_supported_semantic_action_detected",
            "unsupported_action",
            "action_unhandled",
            "no_effect",
            "no_op",
            "noop",
            "service_not_available",
        )
    )


def _max_streak(values: List[bool]) -> int:
    best = 0
    current = 0
    for value in values:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _repeat_streak(items: List[str]) -> Dict[str, Any]:
    best_value = ""
    best = 0
    current_value = ""
    current = 0
    for item in items:
        marker = item or "unknown"
        if marker == current_value:
            current += 1
        else:
            current_value = marker
            current = 1
        if current > best:
            best = current
            best_value = marker
    return {"value": best_value, "streak": best}


def summarize_action_diversity(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in (transcript if isinstance(transcript, list) else [])]
    actions = [_player_action(row) for row in rows]
    semantics = [_semantic_action(row) for row in rows]
    targets = [_target(row) for row in rows]
    semantic_target = [
        f"{semantic}:{target or 'none'}"
        for semantic, target in zip(semantics, targets)
    ]

    action_counter = Counter(action for action in actions if action)
    semantic_counter = Counter(semantics)
    target_counter = Counter(target for target in targets if target)
    semantic_target_counter = Counter(semantic_target)

    return {
        "turns": len(rows),
        "unique_action_count": len(action_counter),
        "unique_semantic_action_count": len(semantic_counter),
        "unique_target_count": len(target_counter),
        "unique_semantic_target_count": len(semantic_target_counter),
        "top_actions": action_counter.most_common(10),
        "top_semantic_actions": semantic_counter.most_common(10),
        "top_targets": target_counter.most_common(10),
        "top_semantic_targets": semantic_target_counter.most_common(10),
        "max_same_action_streak": _repeat_streak(actions),
        "max_same_semantic_action_streak": _repeat_streak(semantics),
        "max_same_target_streak": _repeat_streak(targets),
        "max_same_semantic_target_streak": _repeat_streak(semantic_target),
    }


def summarize_progress_timeline(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in (transcript if isinstance(transcript, list) else [])]
    timeline: List[Dict[str, Any]] = []
    previous_location = ""
    previous_quest_count = 0
    previous_journal_count = 0
    previous_npc_signal_count = 0

    no_progress_flags: List[bool] = []
    storyless_flags: List[bool] = []
    noop_flags: List[bool] = []
    location_changes = 0
    quest_progress_turns = 0
    journal_entry_turns = 0
    npc_signal_turns = 0
    story_beat_turns = 0

    for index, row in enumerate(rows, start=1):
        turn = _turn_index(row, index)
        location = _location(row)
        quest_count = _quest_count(row)
        journal_count = _journal_entry_count(row)
        npc_signal_count = _npc_signal_count(row)
        story_beat = _has_story_beat(row)
        reason = _result_reason(row)
        noop = _is_noop_reason(reason)

        location_changed = bool(previous_location and location and location != previous_location)
        quest_changed = quest_count > previous_quest_count
        journal_changed = journal_count > previous_journal_count
        npc_signal_changed = npc_signal_count > previous_npc_signal_count

        if location_changed:
            location_changes += 1
        if quest_changed:
            quest_progress_turns += 1
        if journal_changed:
            journal_entry_turns += 1
        if npc_signal_changed:
            npc_signal_turns += 1
        if story_beat:
            story_beat_turns += 1

        meaningful_progress = any(
            [
                location_changed,
                quest_changed,
                journal_changed,
                npc_signal_changed,
                story_beat,
            ]
        ) and not noop

        no_progress_flags.append(not meaningful_progress)
        storyless_flags.append(not story_beat)
        noop_flags.append(noop)

        timeline.append(
            {
                "turn_index": turn,
                "semantic_action": _semantic_action(row),
                "target": _target(row),
                "location": location,
                "location_changed": location_changed,
                "quest_count": quest_count,
                "quest_changed": quest_changed,
                "journal_entry_count": journal_count,
                "journal_changed": journal_changed,
                "npc_signal_count": npc_signal_count,
                "npc_signal_changed": npc_signal_changed,
                "story_beat": story_beat,
                "noop": noop,
                "reason": reason,
                "meaningful_progress": meaningful_progress,
                "manual_error": _manual_error(row),
            }
        )

        if location:
            previous_location = location
        previous_quest_count = max(previous_quest_count, quest_count)
        previous_journal_count = max(previous_journal_count, journal_count)
        previous_npc_signal_count = max(previous_npc_signal_count, npc_signal_count)

    turns = len(rows)
    meaningful_turns = sum(1 for item in timeline if item.get("meaningful_progress"))
    return {
        "turns": turns,
        "meaningful_progress_turns": meaningful_turns,
        "meaningful_progress_rate": round(meaningful_turns / turns, 4) if turns else 0.0,
        "story_beat_turns": story_beat_turns,
        "story_beat_rate": round(story_beat_turns / turns, 4) if turns else 0.0,
        "location_changes": location_changes,
        "quest_progress_turns": quest_progress_turns,
        "journal_entry_turns": journal_entry_turns,
        "npc_signal_turns": npc_signal_turns,
        "noop_turns": sum(1 for item in noop_flags if item),
        "noop_rate": round(sum(1 for item in noop_flags if item) / turns, 4) if turns else 0.0,
        "max_no_progress_streak": _max_streak(no_progress_flags),
        "max_storyless_streak": _max_streak(storyless_flags),
        "max_noop_streak": _max_streak(noop_flags),
        "timeline": timeline[-150:],
    }


def summarize_long_run_warnings(
    *,
    transcript: List[Dict[str, Any]],
    action_diversity_summary: Dict[str, Any],
    progress_timeline_summary: Dict[str, Any],
    console_log_summary: Dict[str, Any],
    manual_turn_error_summary: Dict[str, Any],
    turns_for_strict_gates: int = 100,
) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in (transcript if isinstance(transcript, list) else [])]
    turn_count = len(rows)
    strict = turn_count >= turns_for_strict_gates
    warnings: List[Dict[str, Any]] = []

    def add(code: str, severity: str, message: str, details: Dict[str, Any] | None = None) -> None:
        warnings.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "details": details or {},
            }
        )

    same_semantic_target_streak = int(
        _safe_dict(action_diversity_summary.get("max_same_semantic_target_streak")).get("streak") or 0
    )
    if same_semantic_target_streak >= (8 if strict else 5):
        add(
            "repeated_semantic_target_streak",
            "error" if strict else "warning",
            "The player-agent repeated the same semantic action/target too many times.",
            _safe_dict(action_diversity_summary.get("max_same_semantic_target_streak")),
        )

    no_progress_streak = int(progress_timeline_summary.get("max_no_progress_streak") or 0)
    if no_progress_streak >= (10 if strict else 6):
        add(
            "no_progress_streak",
            "error" if strict else "warning",
            "The run had a long streak without meaningful progress.",
            {"max_no_progress_streak": no_progress_streak},
        )

    storyless_streak = int(progress_timeline_summary.get("max_storyless_streak") or 0)
    if storyless_streak >= (12 if strict else 8):
        add(
            "storyless_streak",
            "error" if strict else "warning",
            "The run had a long streak without story beats.",
            {"max_storyless_streak": storyless_streak},
        )

    noop_streak = int(progress_timeline_summary.get("max_noop_streak") or 0)
    if noop_streak >= (5 if strict else 3):
        add(
            "noop_streak",
            "error" if strict else "warning",
            "The run had repeated no-op/internal failure results.",
            {"max_noop_streak": noop_streak},
        )

    if int(_safe_dict(console_log_summary).get("turn_error_count") or 0) > 0:
        add(
            "console_turn_errors",
            "error",
            "Console log contains TURN N ERROR lines.",
            {"turn_errors": _safe_list(console_log_summary.get("turn_errors"))[:10]},
        )

    if int(_safe_dict(manual_turn_error_summary).get("error_count") or 0) > 0:
        add(
            "manual_turn_errors",
            "error",
            "Transcript rows contain manual turn runtime errors.",
            {"errors": _safe_list(manual_turn_error_summary.get("errors"))[:10]},
        )

    error_count = sum(1 for warning in warnings if warning.get("severity") == "error")
    warning_count = sum(1 for warning in warnings if warning.get("severity") == "warning")
    return {
        "ok": error_count == 0,
        "turn_count": turn_count,
        "strict_100_turn_mode": strict,
        "warning_count": warning_count,
        "error_count": error_count,
        "warnings": warnings,
    }


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