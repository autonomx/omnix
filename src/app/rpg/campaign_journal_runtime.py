from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


CAMPAIGN_CALENDAR_VERSION = "campaign_calendar_v1"
PLAYER_JOURNAL_VERSION = "player_journal_v1"

SEASONS = ("spring", "summer", "autumn", "winter")


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def campaign_time_for_turn(
    *,
    turn_index: int,
    start_year: int = 1000,
    start_day: int = 1,
    minutes_per_turn: int = 30,
) -> Dict[str, Any]:
    """Deterministic lightweight fantasy calendar.

    This is metadata only. It does not alter travel, rests, services, combat,
    quests, or other authoritative simulation facts.
    """
    turn_index = max(1, int(turn_index or 1))
    minutes_per_turn = max(1, int(minutes_per_turn or 30))
    total_minutes = (turn_index - 1) * minutes_per_turn
    day_offset = total_minutes // (24 * 60)
    minute_of_day = total_minutes % (24 * 60)
    hour = minute_of_day // 60
    minute = minute_of_day % 60
    day_of_year = ((start_day - 1 + day_offset) % 360) + 1
    year = start_year + ((start_day - 1 + day_offset) // 360)
    season = SEASONS[(day_of_year - 1) // 90]
    day = ((day_of_year - 1) % 30) + 1
    month = ((day_of_year - 1) // 30) + 1
    if 5 <= hour < 12:
        phase = "morning"
    elif 12 <= hour < 17:
        phase = "afternoon"
    elif 17 <= hour < 21:
        phase = "evening"
    else:
        phase = "night"
    return {
        "format_version": CAMPAIGN_CALENDAR_VERSION,
        "year": year,
        "season": season,
        "month": month,
        "day": day,
        "day_of_year": day_of_year,
        "hour": hour,
        "minute": minute,
        "time_label": f"{hour:02d}:{minute:02d}",
        "day_phase": phase,
        "absolute_day": int(day_offset) + 1,
        "turn_index": turn_index,
        "minutes_per_turn": minutes_per_turn,
    }


def campaign_journal_runtime_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    runtime_state.setdefault(
        "campaign_calendar",
        {
            "format_version": CAMPAIGN_CALENDAR_VERSION,
            "minutes_per_turn": 30,
            "current": campaign_time_for_turn(turn_index=1),
            "history": [],
        },
    )
    runtime_state.setdefault(
        "player_journal",
        {
            "format_version": PLAYER_JOURNAL_VERSION,
            "entries": [],
            "pending_actions": [],
            "pending_results": [],
            "journal_every_turns": 4,
            "max_entries": 100,
        },
    )
    return runtime_state


def _extract_player_action(
    *,
    player_input: str = "",
    turn_contract: Dict[str, Any] | None = None,
    turn_result: Dict[str, Any] | None = None,
) -> str:
    turn_contract = _safe_dict(turn_contract)
    turn_result = _safe_dict(turn_result)
    return (
        _safe_str(player_input)
        or _safe_str(turn_contract.get("player_input"))
        or _safe_str(turn_contract.get("action"))
        or _safe_str(turn_result.get("player_action"))
        or _safe_str(turn_result.get("player_input"))
    )


def _extract_result_summary(
    *,
    turn_contract: Dict[str, Any] | None = None,
    turn_result: Dict[str, Any] | None = None,
) -> str:
    turn_contract = _safe_dict(turn_contract)
    turn_result = _safe_dict(turn_result)
    resolved_result = _safe_dict(turn_contract.get("resolved_result"))
    narration_payload = _safe_dict(turn_result.get("narration_payload"))
    npc = _safe_dict(narration_payload.get("npc"))
    parts = [
        _safe_str(resolved_result.get("summary")),
        _safe_str(resolved_result.get("description")),
        _safe_str(turn_contract.get("result")),
        _safe_str(narration_payload.get("action")),
        _safe_str(narration_payload.get("narration")),
        _safe_str(npc.get("line")),
    ]
    for part in parts:
        if part:
            return part[:700]
    return ""


def _journal_text(actions: List[str], results: List[str]) -> str:
    action_part = "; ".join(actions[-4:]).strip()
    result_part = " ".join(results[-2:]).strip()
    if action_part and result_part:
        return f"I focused on: {action_part}. What stood out: {result_part[:500]}"
    if action_part:
        return f"I focused on: {action_part}."
    if result_part:
        return f"What stood out: {result_part[:500]}"
    return "I kept moving, watching for what changed around me."


def advance_campaign_journal_for_turn(
    *,
    runtime_state: Dict[str, Any],
    turn_index: int,
    player_input: str = "",
    turn_contract: Dict[str, Any] | None = None,
    turn_result: Dict[str, Any] | None = None,
    minutes_per_turn: int | None = None,
    journal_every_turns: int | None = None,
) -> Dict[str, Any]:
    """Advance base-game calendar and deterministic player journal.

    This mutates runtime_state only. It does not mutate authoritative
    simulation facts.
    """
    runtime_state = campaign_journal_runtime_state(runtime_state)
    calendar = _safe_dict(runtime_state.get("campaign_calendar"))
    journal = _safe_dict(runtime_state.get("player_journal"))

    if minutes_per_turn is None:
        minutes_per_turn = int(calendar.get("minutes_per_turn") or 30)
    if journal_every_turns is None:
        journal_every_turns = int(journal.get("journal_every_turns") or 4)

    time_info = campaign_time_for_turn(
        turn_index=int(turn_index or 1),
        minutes_per_turn=int(minutes_per_turn or 30),
    )
    calendar["minutes_per_turn"] = int(minutes_per_turn or 30)
    calendar["current"] = time_info
    history = _safe_list(calendar.get("history"))
    if not history or _safe_dict(history[-1]).get("turn_index") != time_info["turn_index"]:
        history.append(time_info)
    calendar["history"] = history[-500:]

    action = _extract_player_action(
        player_input=player_input,
        turn_contract=_safe_dict(turn_contract),
        turn_result=_safe_dict(turn_result),
    )
    result = _extract_result_summary(
        turn_contract=_safe_dict(turn_contract),
        turn_result=_safe_dict(turn_result),
    )

    pending_actions = _safe_list(journal.get("pending_actions"))
    pending_results = _safe_list(journal.get("pending_results"))
    if action:
        pending_actions.append(action[:300])
    if result:
        pending_results.append(result[:700])

    journal["pending_actions"] = pending_actions[-12:]
    journal["pending_results"] = pending_results[-12:]
    journal["journal_every_turns"] = int(journal_every_turns or 4)

    entries = _safe_list(journal.get("entries"))
    should_write = int(turn_index or 1) % max(1, int(journal_every_turns or 4)) == 0
    existing_entry_ids = {_safe_str(entry.get("entry_id")) for entry in entries if isinstance(entry, dict)}

    if should_write:
        entry_id = f"journal:turn:{int(turn_index or 1)}"
        if entry_id not in existing_entry_ids:
            entries.append(
                {
                    "format_version": PLAYER_JOURNAL_VERSION,
                    "entry_id": entry_id,
                    "start_turn": max(
                        1,
                        int(turn_index or 1) - max(len(pending_actions), 1) + 1,
                    ),
                    "end_turn": int(turn_index or 1),
                    "time": deepcopy(time_info),
                    "perspective": "player",
                    "text": _journal_text(pending_actions, pending_results),
                    "source": "deterministic_runtime_journal",
                }
            )
        journal["pending_actions"] = []
        journal["pending_results"] = []

    max_entries = int(journal.get("max_entries") or 100)
    journal["entries"] = entries[-max_entries:]
    runtime_state["campaign_calendar"] = calendar
    runtime_state["player_journal"] = journal
    return runtime_state


def summarize_campaign_calendar(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    calendar = _safe_dict(runtime_state.get("campaign_calendar"))
    history = _safe_list(calendar.get("history"))
    return {
        "minutes_per_turn": calendar.get("minutes_per_turn", 30),
        "turns_tracked": len(history),
        "start": history[0] if history else _safe_dict(calendar.get("current")),
        "end": _safe_dict(calendar.get("current")),
        "rows": history[-20:],
    }


def summarize_player_journal(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    journal = _safe_dict(runtime_state.get("player_journal"))
    entries = _safe_list(journal.get("entries"))
    return {
        "entry_count": len(entries),
        "entries": entries[-20:],
        "pending_action_count": len(_safe_list(journal.get("pending_actions"))),
        "pending_result_count": len(_safe_list(journal.get("pending_results"))),
    }