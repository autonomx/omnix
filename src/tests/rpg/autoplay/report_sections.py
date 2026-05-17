from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.campaign_journal_runtime import (
    _journal_text as _base_journal_text,
)
from app.rpg.campaign_journal_runtime import (
    campaign_time_for_turn,
    summarize_campaign_calendar,
    summarize_player_journal,
)
from app.rpg.quest_progress import (
    normalize_quest_status,
    quest_rows_from_story_arc_view,
    summarize_runtime_quests,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _last_nonempty_row_value(transcript: List[Dict[str, Any]], key: str) -> Any:
    for row in reversed(transcript if isinstance(transcript, list) else []):
        row = _safe_dict(row)
        value = row.get(key)
        if value:
            return value
    return {}


def _latest_runtime_state_with_journal(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in reversed(transcript if isinstance(transcript, list) else []):
        row = _safe_dict(row)
        candidates = [
            _safe_dict(row.get("runtime_state")),
            _safe_dict(_safe_dict(row.get("turn_result")).get("runtime_state")),
            _safe_dict(_safe_dict(_safe_dict(row.get("turn_result")).get("session")).get("runtime_state")),
        ]
        for runtime_state in candidates:
            if runtime_state.get("campaign_calendar") or runtime_state.get("player_journal"):
                return runtime_state
    return {}


def _latest_runtime_state_with_quests(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in reversed(transcript if isinstance(transcript, list) else []):
        row = _safe_dict(row)
        candidates = [
            _safe_dict(row.get("runtime_state")),
            _safe_dict(_safe_dict(row.get("turn_result")).get("runtime_state")),
            _safe_dict(_safe_dict(_safe_dict(row.get("turn_result")).get("session")).get("runtime_state")),
        ]
        for runtime_state in candidates:
            if _safe_dict(runtime_state.get("quest_progress")).get("quests"):
                return runtime_state
    return {}


def _loaded_profiles_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(row.get("runtime_state"))
    return _safe_dict(_safe_dict(runtime_state.get("npc_evolution")).get("loaded_profiles"))


def _arcs_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(row.get("runtime_state"))
    return _safe_dict(_safe_dict(runtime_state.get("npc_evolution")).get("arcs"))


def _signals_from_row(row: Dict[str, Any]) -> List[Any]:
    runtime_state = _safe_dict(row.get("runtime_state"))
    return _safe_list(_safe_dict(runtime_state.get("npc_evolution")).get("signals"))


def summarize_npc_evolution_for_report(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build readable NPC evolution report model from final runtime state."""
    latest_row: Dict[str, Any] = {}
    for row in reversed(transcript if isinstance(transcript, list) else []):
        row = _safe_dict(row)
        if _arcs_from_row(row) or _loaded_profiles_from_row(row):
            latest_row = row
            break

    arcs = _arcs_from_row(latest_row)
    loaded_profiles = _loaded_profiles_from_row(latest_row)
    signals = _signals_from_row(latest_row)
    latest_summary = _safe_dict(latest_row.get("npc_evolution_summary"))

    cards: List[Dict[str, Any]] = []
    all_npc_ids = sorted(set(arcs.keys()) | set(loaded_profiles.keys()))

    for npc_id in all_npc_ids:
        arc = _safe_dict(arcs.get(npc_id))
        loaded_row = _safe_dict(loaded_profiles.get(npc_id))
        profile = _safe_dict(loaded_row.get("profile"))
        axes = _safe_dict(arc.get("axes") or profile.get("axes"))
        stage = _safe_str(arc.get("arc_stage") or profile.get("arc_stage") or "stable")
        npc_signals = [
            _safe_dict(signal)
            for signal in signals
            if _safe_str(_safe_dict(signal).get("npc_id")) == _safe_str(npc_id)
        ]
        cards.append(
            {
                "npc_id": npc_id,
                "arc_stage": stage,
                "axes": axes,
                "signal_count": len(npc_signals),
                "signals_by_kind": _count_by_key(npc_signals, "kind"),
                "memories": _safe_list(arc.get("memories") or profile.get("memories"))[-6:],
                "future_hooks": _safe_list(arc.get("future_hooks") or profile.get("future_hooks"))[-6:],
                "world_signals": _safe_list(arc.get("world_signals") or profile.get("world_signals"))[-4:],
                "semantic_intents": _safe_list(arc.get("semantic_intents") or profile.get("semantic_intents"))[-4:],
                "milestones": _safe_list(arc.get("milestones") or profile.get("milestones"))[-8:],
                "profile_path": _safe_str(loaded_row.get("path")),
            }
        )

    return {
        "npc_count": len(cards),
        "cards": cards,
        "latest_summary": latest_summary,
        "has_milestones": any(_safe_list(card.get("milestones")) for card in cards),
        "has_profile_paths": any(_safe_str(card.get("profile_path")) for card in cards),
    }


def _count_by_key(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = _safe_str(_safe_dict(row).get(key)) or "unknown"
        counts[value] = int(counts.get(value) or 0) + 1
    return counts


def _quest_rows_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = _safe_dict(state)
    quest_sources = [
        state.get("quests"),
        state.get("quest_state"),
        state.get("journal_quests"),
        _safe_dict(state.get("journal")).get("quests"),
        _safe_dict(state.get("quest_log")).get("quests"),
    ]

    rows: List[Dict[str, Any]] = []
    for source in quest_sources:
        if isinstance(source, dict):
            for quest_id, quest_any in source.items():
                quest = _safe_dict(quest_any)
                if not quest and isinstance(quest_any, str):
                    quest = {"title": quest_any}
                quest.setdefault("quest_id", str(quest_id))
                rows.append(quest)
        elif isinstance(source, list):
            for index, quest_any in enumerate(source):
                quest = _safe_dict(quest_any)
                if not quest and isinstance(quest_any, str):
                    quest = {"title": quest_any}
                quest.setdefault("quest_id", _safe_str(quest.get("id")) or f"quest:{index}")
                rows.append(quest)

    return rows


def _quest_rows_from_turn_contract(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    contract = _safe_dict(contract)
    rows: List[Dict[str, Any]] = []
    for section_key in ("quest_updates", "quests", "journal_updates"):
        section = contract.get(section_key)
        if isinstance(section, list):
            for index, item in enumerate(section):
                item_dict = _safe_dict(item)
                if item_dict:
                    item_dict.setdefault("quest_id", _safe_str(item_dict.get("id")) or f"contract:{section_key}:{index}")
                    rows.append(item_dict)
        elif isinstance(section, dict):
            for quest_id, item in section.items():
                item_dict = _safe_dict(item)
                item_dict.setdefault("quest_id", str(quest_id))
                rows.append(item_dict)
    return rows


def _quest_rows_from_story_arc_view(story_arc_view: Dict[str, Any]) -> List[Dict[str, Any]]:
    story_arc_view = _safe_dict(story_arc_view)
    rows: List[Dict[str, Any]] = []
    for arc in _safe_list(story_arc_view.get("arcs")):
        arc = _safe_dict(arc)
        arc_id = _safe_str(arc.get("arc_id"))
        arc_title = _safe_str(arc.get("title") or arc_id)
        arc_status = _safe_str(arc.get("status") or "active")
        milestones = _safe_list(arc.get("milestones"))
        objectives = []
        for milestone in milestones:
            milestone = _safe_dict(milestone)
            status = _safe_str(milestone.get("status") or "active")
            objectives.append(
                {
                    "summary": _safe_str(
                        milestone.get("title")
                        or milestone.get("objective_text")
                        or milestone.get("summary")
                    ),
                    "completed": status in {"completed", "done", "resolved"},
                    "status": status,
                }
            )
        rows.append(
            {
                "quest_id": _safe_str(arc.get("quest_id") or arc_id),
                "title": arc_title,
                "status": arc_status,
                "objectives": objectives,
                "summary": _safe_str(arc.get("stage") or arc.get("summary")),
                "source": "story_arc_view",
            }
        )
    return rows


def _quest_status(quest: Dict[str, Any]) -> str:
    status = normalize_quest_status(
        quest.get("status")
        or quest.get("state")
        or quest.get("phase")
        or quest.get("progress_state")
    )
    if status != "unknown":
        return status
    completed = quest.get("completed")
    if completed is True:
        return "completed"
    if completed is False:
        return "active"
    return "unknown"


def _quest_progress_text(quest: Dict[str, Any]) -> str:
    objectives = quest.get("objectives") or quest.get("steps") or quest.get("tasks")
    if isinstance(objectives, list) and objectives:
        done = 0
        total = 0
        labels = []
        for item in objectives:
            total += 1
            item_dict = _safe_dict(item)
            label = _safe_str(item_dict.get("summary") or item_dict.get("title") or item_dict.get("name") or item)
            if item_dict.get("completed") is True or normalize_quest_status(item_dict.get("status")) == "completed":
                done += 1
            if label and len(labels) < 3:
                labels.append(label)
        return f"{done}/{total} objectives complete" + (f": {'; '.join(labels)}" if labels else "")
    progress = quest.get("progress")
    if isinstance(progress, (int, float)):
        return f"{progress}%"
    return _safe_str(quest.get("summary") or quest.get("description") or quest.get("note"))


def summarize_quests_for_report(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Best-effort quest summary from state and turn contracts."""
    quest_by_id: Dict[str, Dict[str, Any]] = {}
    timeline: List[Dict[str, Any]] = []

    runtime_state = _latest_runtime_state_with_quests(transcript)
    runtime_quest_summary = summarize_runtime_quests(runtime_state) if runtime_state else {}
    for quest in _safe_list(runtime_quest_summary.get("quests")):
        quest = _safe_dict(quest)
        quest_id = _safe_str(quest.get("quest_id") or quest.get("id") or quest.get("title"))
        if quest_id:
            quest_by_id[quest_id] = {**quest_by_id.get(quest_id, {}), **quest, "source": quest.get("source") or "runtime_quest_progress"}
    timeline.extend(_safe_list(runtime_quest_summary.get("timeline")))

    # Story arcs often contain active unresolved objectives even when quest_state
    # is not present. Project them into Quest Progress for report readability.
    story_arc_view = _safe_dict(_last_nonempty_row_value(transcript, "story_arc_view"))
    for quest in quest_rows_from_story_arc_view(story_arc_view):
        quest_id = _safe_str(quest.get("quest_id") or quest.get("title"))
        if quest_id and quest_id not in quest_by_id:
            quest_by_id[quest_id] = quest

    # Some campaign quests are tracked as story arcs rather than quest_state.
    # Pull those into Quest Progress so active objectives do not vanish.
    story_arc_view = _safe_dict(_last_nonempty_row_value(transcript, "story_arc_view"))
    for quest in _quest_rows_from_story_arc_view(story_arc_view):
        quest_id = _safe_str(quest.get("quest_id") or quest.get("title"))
        if quest_id:
            quest_by_id[quest_id] = {**quest_by_id.get(quest_id, {}), **quest}

    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        turn_index = row.get("turn_index")
        state_candidates = [
            row.get("simulation_state"),
            row.get("final_authoritative_state"),
            row.get("before_state"),
            _safe_dict(row.get("turn_result")).get("simulation_state"),
            _safe_dict(_safe_dict(row.get("turn_result")).get("session")).get("simulation_state"),
        ]
        for state_any in state_candidates:
            for quest in _quest_rows_from_state(_safe_dict(state_any)):
                quest_id = _safe_str(quest.get("quest_id") or quest.get("id") or quest.get("title"))
                if not quest_id:
                    continue
                quest_by_id[quest_id] = {**quest_by_id.get(quest_id, {}), **quest}

        contract = _safe_dict(row.get("turn_contract") or _safe_dict(row.get("turn_result")).get("turn_contract"))
        for quest in _quest_rows_from_turn_contract(contract):
            quest_id = _safe_str(quest.get("quest_id") or quest.get("id") or quest.get("title"))
            if not quest_id:
                continue
            quest_by_id[quest_id] = {**quest_by_id.get(quest_id, {}), **quest}
            timeline.append(
                {
                    "turn_index": turn_index,
                    "quest_id": quest_id,
                    "status": _quest_status(quest),
                    "summary": _safe_str(quest.get("summary") or quest.get("description") or quest.get("title")),
                }
            )

    quests = []
    for quest_id, quest in sorted(quest_by_id.items()):
        title = _safe_str(quest.get("title") or quest.get("name") or quest_id)
        status = _quest_status(quest)
        quests.append(
            {
                "quest_id": quest_id,
                "title": title,
                "status": status,
                "progress": _quest_progress_text(quest),
                "giver": _safe_str(quest.get("giver") or quest.get("quest_giver")),
                "location": _safe_str(quest.get("location")),
                "raw_keys": sorted(list(quest.keys()))[:30],
            }
        )

    return {
        "quest_count": len(quests),
        "active_count": sum(1 for quest in quests if quest.get("status") == "active"),
        "completed_count": sum(1 for quest in quests if quest.get("status") == "completed"),
        "failed_count": sum(1 for quest in quests if quest.get("status") == "failed"),
        "unknown_count": sum(1 for quest in quests if quest.get("status") == "unknown"),
        "quests": quests,
        "timeline": timeline[-20:],
    }


def _row_action(row: Dict[str, Any]) -> str:
    selected = _safe_dict(row.get("selected_player_action"))
    return (
        _safe_str(row.get("player_action"))
        or _safe_str(row.get("player_input"))
        or _safe_str(selected.get("action"))
    )


def _row_result(row: Dict[str, Any]) -> str:
    combined = _safe_dict(row.get("combined_background_llm_result"))
    narration = _safe_str(combined.get("narration"))
    if narration:
        return narration
    payload = _safe_dict(_safe_dict(row.get("turn_result")).get("narration_payload"))
    return _safe_str(payload.get("narration") or row.get("narration"))


def build_campaign_calendar_and_journal(
    transcript: List[Dict[str, Any]],
    *,
    minutes_per_turn: int = 30,
    journal_every_turns: int = 4,
) -> Dict[str, Any]:
    runtime_state = _latest_runtime_state_with_journal(transcript)
    if runtime_state:
        calendar = summarize_campaign_calendar(runtime_state)
        journal = summarize_player_journal(runtime_state)
        if calendar.get("turns_tracked") or journal.get("entry_count"):
            calendar["source"] = "base_runtime"
            journal["source"] = "base_runtime"
            return {
                "calendar": calendar,
                "journal": journal,
            }

    calendar_rows: List[Dict[str, Any]] = []
    journal_entries: List[Dict[str, Any]] = []
    current_actions: List[str] = []
    current_results: List[str] = []
    current_start_time: Dict[str, Any] = {}

    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        turn_index = int(row.get("turn_index") or len(calendar_rows) + 1)
        time_info = campaign_time_for_turn(turn_index=turn_index, minutes_per_turn=minutes_per_turn)
        row["campaign_time"] = time_info
        calendar_rows.append(time_info)

        if not current_start_time:
            current_start_time = time_info
        action = _row_action(row)
        result = _row_result(row)
        if action:
            current_actions.append(action)
        if result:
            current_results.append(result)

        should_flush = (turn_index % max(1, journal_every_turns) == 0)
        if should_flush:
            journal_entries.append(
                {
                    "entry_id": f"journal:turn:{turn_index}",
                    "start_turn": current_start_time.get("turn_index"),
                    "end_turn": turn_index,
                    "time": time_info,
                    "perspective": "player",
                    "text": _journal_text(current_actions, current_results),
                }
            )
            current_actions = []
            current_results = []
            current_start_time = {}

    if current_actions or current_results:
        end_time = calendar_rows[-1] if calendar_rows else campaign_time_for_turn(turn_index=1)
        journal_entries.append(
            {
                "entry_id": f"journal:turn:{end_time.get('turn_index')}",
                "start_turn": current_start_time.get("turn_index") or 1,
                "end_turn": end_time.get("turn_index"),
                "time": end_time,
                "perspective": "player",
                "text": _journal_text(current_actions, current_results),
            }
        )

    return {
        "calendar": {
            "source": "report_fallback",
            "minutes_per_turn": minutes_per_turn,
            "turns_tracked": len(calendar_rows),
            "start": calendar_rows[0] if calendar_rows else {},
            "end": calendar_rows[-1] if calendar_rows else {},
            "rows": calendar_rows[-20:],
        },
        "journal": {
            "source": "report_fallback",
            "entry_count": len(journal_entries),
            "entries": journal_entries[-20:],
        },
    }


def summarize_story_beats_for_report(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    beats: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for row in transcript if isinstance(transcript, list) else []:
        row = _safe_dict(row)
        turn_index = row.get("turn_index")
        action = _safe_str(row.get("player_action"))
        narration = (
            _safe_str(row.get("narration"))
            or _safe_str(_safe_dict(row.get("combined_background_llm_result")).get("narration"))
            or _safe_str(_safe_dict(row.get("resolved_narration_payload")).get("narration"))
        )
        progress_delta = _safe_dict(row.get("progress_delta"))
        story_hook_result = _safe_dict(row.get("story_hook_result"))
        turn_contract = _safe_dict(row.get("turn_contract"))

        if not turn_contract:
            warnings.append(f"turn {turn_index}: empty turn_contract")

        summary_parts = []
        if action:
            summary_parts.append(f"Player: {action}")
        if narration:
            summary_parts.append(narration[:260])
        if progress_delta:
            progress_text = _safe_str(progress_delta.get("summary") or progress_delta.get("reason"))
            if progress_text:
                summary_parts.append(progress_text[:160])
        hook_summary = _safe_str(story_hook_result.get("summary") or story_hook_result.get("story_summary"))
        if hook_summary:
            summary_parts.append(hook_summary[:180])

        if summary_parts:
            beats.append(
                {
                    "turn_index": turn_index,
                    "summary": " — ".join(summary_parts)[:600],
                    "source": "fallback_turn_summary",
                    "has_turn_contract": bool(turn_contract),
                }
            )

    return {
        "beat_count": len(beats),
        "beats": beats[-20:],
        "warnings": warnings[-20:],
        "empty_turn_contract_count": len(warnings),
    }


def _journal_text(actions: List[str], results: List[str]) -> str:
    return _base_journal_text(actions, results)