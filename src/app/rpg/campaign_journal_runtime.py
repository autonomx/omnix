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


INTERNAL_JOURNAL_TOKENS = {
    "target_not_found",
    "no_supported_semantic_action_detected",
    "talk_handled_by_conversation_runtime",
    "service_not_available",
    "action_unhandled",
    "semantic_action_unsupported",
    "unsupported_action",
    "unknown_action",
    "no_effect",
    "no_op",
    "noop",
}


def _looks_internal_code(value: str) -> bool:
    text = _safe_str(value).strip()
    if not text:
        return False
    lower = text.lower()
    if lower in INTERNAL_JOURNAL_TOKENS:
        return True
    if " " not in lower and "_" in lower:
        return True
    if lower.endswith("_runtime") or lower.endswith("_detected") or lower.endswith("_unsupported"):
        return True
    if lower.startswith("target_") or lower.startswith("semantic_"):
        return True
    return False


def _looks_malformed_journal_fragment(value: str) -> bool:
    text = _safe_str(value).strip()
    if not text:
        return True
    lower = text.lower()

    # Fragments caused by prompt/action truncation or quote slicing.
    if text[0] in ".;,:!?)]}":
        return True
    if text.startswith(("\".", "'.", "“.", "‘.")):
        return True
    if ".and " in lower or "\n.and " in lower:
        return True
    if text.startswith(("…", "...")):
        return True
    if lower.startswith(("or trouble", "gold? or", "or gold", "and ask", "then ask")):
        return True

    # Too short to be useful unless it is a normal sentence-like command.
    words = [part for part in text.replace("…", " ").split() if part.strip()]
    if len(words) <= 2 and not text.endswith((".", "!", "?")):
        return True

    # Broken fragments often have no leading verb/subject and include ellipses.
    if "…" in text or "..." in text:
        if len(words) < 8:
            return True
        if text.count("…") + text.count("...") >= 2:
            return True

    return False


def _clean_journal_text(value: Any, *, max_len: int = 700) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    if _looks_internal_code(text):
        return ""
    if _looks_malformed_journal_fragment(text):
        return ""
    # Remove isolated internal tokens from otherwise readable text.
    parts = []
    for token in text.replace("\n", " ").split():
        cleaned = token.strip(".,;:()[]{}\"'")
        if _looks_internal_code(cleaned):
            continue
        parts.append(token)
    text = " ".join(parts).strip()
    if not text:
        return ""
    text = text.replace('".and ', '"and ')
    text = text.replace("'.and ", "'and ")
    text = text.replace("“.and ", "“and ")
    text = text.replace("‘.and ", "‘and ")
    text = text.replace(': ".', ": ")
    text = text.replace(": '.", ": ")
    text = text.replace('".what', "what")
    text = text.replace("'.what", "what")
    text = text.replace('".What', "What")
    text = text.replace("'.What", "What")
    text = text.replace('".', "")
    text = text.replace("'.", "")
    while "  " in text:
        text = text.replace("  ", " ")
    if _looks_malformed_journal_fragment(text):
        return ""
    if len(text) > max_len:
        # Prefer cutting at a sentence boundary when possible.
        candidate = text[: max_len - 1].rstrip()
        boundary = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
        if boundary >= max(80, int(max_len * 0.45)):
            text = candidate[: boundary + 1].strip()
        else:
            text = candidate.rstrip(" ,;:") + "…"
    return text


def _normalize_sentence_punctuation(text: str) -> str:
    text = _safe_str(text).strip()
    if not text:
        return ""
    while "  " in text:
        text = text.replace("  ", " ")
    # Normalize common doubled punctuation from joined snippets.
    replacements = {
        "..": ".",
        "!.": "!",
        "?.": "?",
        ";.": ";",
        ",.": ".",
        ".;": ".",
    }
    changed = True
    while changed:
        changed = False
        for old, new in replacements.items():
            if old in text:
                text = text.replace(old, new)
                changed = True
    # Avoid trailing semicolon/comma fragments.
    text = text.rstrip(" ;,")
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _sentence_join(parts: List[str], *, max_items: int = 4) -> str:
    cleaned: List[str] = []
    seen = set()
    for part in _safe_list(parts):
        text = _normalize_sentence_punctuation(_clean_journal_text(part, max_len=240))
        if not text:
            continue
        if '".and ' in text.lower() or "'.and " in text.lower():
            continue
        marker = text.lower()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(text)
        if len(cleaned) >= max_items:
            break
    return " ".join(cleaned).strip()


def _contains_learning_signal(text: str) -> bool:
    lower = _safe_str(text).lower()
    return any(
        token in lower
        for token in (
            "heard",
            "learned",
            "told",
            "mentioned",
            "warned",
            "revealed",
            "rumor",
            "witness",
            "missing",
            "danger",
            "strange lights",
            "road",
            "woods",
            "quest",
            "clue",
            "trail",
            "sign",
            "saw",
            "seen",
            "knows",
            "asked",
            "answer",
            "answers",
            "lowered his voice",
            "lowered her voice",
        )
    )


def _contains_next_signal(text: str) -> bool:
    lower = _safe_str(text).lower()
    return any(
        token in lower
        for token in (
            "find",
            "report",
            "look for",
            "ask",
            "follow",
            "investigate",
            "search",
            "return",
            "next",
            "should",
            "need",
            "witness",
        )
    )


def _infer_learned_lines(results: List[str]) -> List[str]:
    learned: List[str] = []
    for result in _safe_list(results):
        text = _clean_journal_text(result, max_len=260)
        if text and (_contains_learning_signal(text) or len(text.split()) >= 10):
            learned.append(text)
    return learned


def _infer_next_lines(actions: List[str], results: List[str]) -> List[str]:
    candidates = list(_safe_list(results)[-3:]) + list(_safe_list(actions)[-3:])
    next_lines: List[str] = []
    for item in candidates:
        text = _clean_journal_text(item, max_len=220)
        if text and _contains_next_signal(text):
            next_lines.append(text)
    return next_lines


def _quest_progress_lines(runtime_state: Dict[str, Any]) -> List[str]:
    quest_state = _safe_dict(_safe_dict(runtime_state).get("quest_progress"))
    quests = _safe_dict(quest_state.get("quests"))
    lines: List[str] = []
    for quest in quests.values():
        quest = _safe_dict(quest)
        title = _safe_str(quest.get("title") or quest.get("quest_id"))
        objectives = _safe_list(quest.get("objectives"))
        active_objectives = []
        for objective in objectives:
            objective = _safe_dict(objective)
            if objective.get("completed") is True:
                continue
            status = _safe_str(objective.get("status")).lower()
            if status in {"completed", "done", "resolved"}:
                continue
            summary = _safe_str(objective.get("summary") or objective.get("title"))
            if summary:
                active_objectives.append(summary)
        if title and active_objectives:
            lines.append(f"{title}: " + "; ".join(active_objectives[:3]))
    return lines[:3]


def _first_clean_text(*values: Any, max_len: int = 700) -> str:
    for value in values:
        cleaned = _clean_journal_text(value, max_len=max_len)
        if cleaned:
            return cleaned
    return ""


def _narration_payload_candidates(turn_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    turn_result = _safe_dict(turn_result)
    result = _safe_dict(turn_result.get("result"))
    combined = _safe_dict(turn_result.get("combined_background_llm_result"))
    resolved = _safe_dict(turn_result.get("resolved_narration_payload"))
    return [
        _safe_dict(turn_result.get("narration_payload")),
        _safe_dict(result.get("narration_payload")),
        _safe_dict(combined.get("narration_payload")),
        resolved,
    ]


def _narration_text_candidates(turn_result: Dict[str, Any]) -> List[str]:
    turn_result = _safe_dict(turn_result)
    combined = _safe_dict(turn_result.get("combined_background_llm_result"))
    resolved = _safe_dict(turn_result.get("resolved_narration_payload"))
    candidates: List[str] = [
        _safe_str(turn_result.get("narration")),
        _safe_str(combined.get("narration")),
        _safe_str(resolved.get("narration")),
    ]
    for payload in _narration_payload_candidates(turn_result):
        npc = _safe_dict(payload.get("npc"))
        candidates.extend(
            [
                _safe_str(payload.get("narration")),
                _safe_str(payload.get("action")),
                _safe_str(npc.get("line")),
            ]
        )
    return [item for item in candidates if item]


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
    return _first_clean_text(
        player_input,
        turn_contract.get("player_input"),
        turn_contract.get("action"),
        turn_result.get("player_action"),
        turn_result.get("player_input"),
        max_len=300,
    )


def _extract_result_summary(
    *,
    turn_contract: Dict[str, Any] | None = None,
    turn_result: Dict[str, Any] | None = None,
) -> str:
    turn_contract = _safe_dict(turn_contract)
    turn_result = _safe_dict(turn_result)
    resolved_result = _safe_dict(turn_contract.get("resolved_result"))
    resolved_action = _safe_dict(turn_contract.get("resolved_action"))

    # Prefer player-facing prose over deterministic internal reason codes.
    return _first_clean_text(
        *_narration_text_candidates(turn_result),
        resolved_result.get("summary"),
        resolved_result.get("description"),
        resolved_action.get("summary"),
        turn_contract.get("narration_brief"),
        turn_contract.get("result"),
        max_len=700,
    )


def _journal_text(
    actions: List[str],
    results: List[str],
    *,
    runtime_state: Dict[str, Any] | None = None,
) -> str:
    clean_actions = [
        _clean_journal_text(action, max_len=220)
        for action in _safe_list(actions)[-4:]
    ]
    clean_actions = [action for action in clean_actions if action]
    clean_results = [
        _clean_journal_text(result, max_len=320)
        for result in _safe_list(results)[-4:]
    ]
    clean_results = [result for result in clean_results if result]

    learned = _infer_learned_lines(clean_results)
    next_lines = _infer_next_lines(clean_actions, clean_results)
    quest_lines = _quest_progress_lines(_safe_dict(runtime_state))
    next_lines = quest_lines + next_lines

    sections: List[str] = []
    did = _sentence_join(clean_actions, max_items=4)
    if did:
        sections.append(f"What I did: {did}")

    learned_text = _sentence_join(learned, max_items=2)
    if learned_text:
        sections.append(f"What I learned: {learned_text}")

    changed_candidates = [
        item for item in clean_results
        if item and item not in learned
    ] or clean_results
    changed_text = _sentence_join(changed_candidates, max_items=2)
    if changed_text and changed_text.lower() != learned_text.lower():
        sections.append(f"What changed: {changed_text}")

    next_text = _sentence_join(next_lines, max_items=2)
    if next_text:
        sections.append(f"Next: {next_text}")

    if not sections:
        sections.append("I kept moving, watching for what changed around me.")

    raw = "\n".join(_normalize_sentence_punctuation(section) for section in sections if section).strip()
    return _repair_required_journal_sections(
        raw,
        actions=actions,
        results=results,
        runtime_state=_safe_dict(runtime_state),
    )


def _repair_required_journal_sections(
    text: str,
    *,
    actions: List[str],
    results: List[str],
    runtime_state: Dict[str, Any] | None = None,
) -> str:
    text = _safe_str(text).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    by_prefix: Dict[str, str] = {}
    for line in lines:
        lower = line.lower()
        for prefix in ("what i did:", "what i learned:", "what changed:", "next:"):
            if lower.startswith(prefix) and prefix not in by_prefix:
                by_prefix[prefix] = line

    clean_actions = [_clean_journal_text(item, max_len=220) for item in _safe_list(actions)[-4:]]
    clean_actions = [item for item in clean_actions if item]
    clean_results = [_clean_journal_text(item, max_len=300) for item in _safe_list(results)[-4:]]
    clean_results = [item for item in clean_results if item]
    quest_lines = _quest_progress_lines(_safe_dict(runtime_state))

    if "what i did:" not in by_prefix:
        fallback = _sentence_join(clean_actions, max_items=2) or "I pursued the strongest available lead."
        by_prefix["what i did:"] = "What I did: " + fallback
    if "what i learned:" not in by_prefix:
        learned = _sentence_join(_infer_learned_lines(clean_results), max_items=2)
        by_prefix["what i learned:"] = "What I learned: " + (learned or "I reviewed the current situation for actionable clues.")
    if "what changed:" not in by_prefix:
        changed = _sentence_join(clean_results, max_items=2)
        by_prefix["what changed:"] = "What changed: " + (changed or "The campaign state remained stable while I looked for a stronger lead.")
    if "next:" not in by_prefix:
        next_text = _sentence_join(quest_lines + _infer_next_lines(clean_actions, clean_results), max_items=2)
        by_prefix["next:"] = "Next: " + (next_text or "I should take a concrete action that advances a quest, location, or story lead.")

    ordered = [
        by_prefix["what i did:"],
        by_prefix["what i learned:"],
        by_prefix["what changed:"],
        by_prefix["next:"],
    ]
    return "\n".join(_normalize_sentence_punctuation(line) for line in ordered if line).strip()


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
    action = _clean_journal_text(action, max_len=300)
    result = _clean_journal_text(result, max_len=700)
    if action:
        pending_actions.append(action)
    if result:
        pending_results.append(result)

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
                    "text": _journal_text(
                        pending_actions,
                        pending_results,
                        runtime_state=runtime_state,
                    ),
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