from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any, Dict, List

SOURCE = "deterministic_quest_journal_runtime"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def ensure_journal_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    journal_state = _safe_dict(simulation_state.get("journal_state"))
    journal_state.setdefault("version", 1)
    journal_state["entries"] = [normalize_journal_entry(row) for row in _safe_list(journal_state.get("entries")) if isinstance(row, dict)]
    simulation_state["journal_state"] = journal_state
    return journal_state


def normalize_journal_entry(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    tags = [_safe_str(row) for row in _safe_list(value.get("tags")) if _safe_str(row)]
    entry_id = _safe_str(value.get("entry_id"))
    return {
        "entry_id": entry_id,
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "quest_id": _safe_str(value.get("quest_id")),
        "objective_id": _safe_str(value.get("objective_id")),
        "event_type": _safe_str(value.get("event_type")) or "note",
        "what_happened": _safe_str(value.get("what_happened")),
        "what_i_learned": _safe_str(value.get("what_i_learned")),
        "next_objective": _safe_str(value.get("next_objective")),
        "tags": tags,
        "source": _safe_str(value.get("source")) or SOURCE,
    }


def add_journal_entry(
    simulation_state: Dict[str, Any],
    *,
    quest_id: str,
    objective_id: str = "",
    event_type: str = "note",
    what_happened: str = "",
    what_i_learned: str = "",
    next_objective: str = "",
    turn_index: int = 0,
    tags: List[str] | None = None,
) -> Dict[str, Any]:
    normalized_quest_id = _safe_str(quest_id)
    if not normalized_quest_id:
        return _reject("quest_id_missing", quest_id="", objective_id=objective_id)
    happened = _safe_str(what_happened)
    learned = _safe_str(what_i_learned)
    next_step = _safe_str(next_objective)
    if not (happened or learned or next_step):
        return _reject("journal_entry_empty", quest_id=normalized_quest_id, objective_id=objective_id)

    journal_state = ensure_journal_state(simulation_state)
    entry = normalize_journal_entry(
        {
            "entry_id": _build_entry_id(journal_state, normalized_quest_id, objective_id, turn_index),
            "turn_index": turn_index,
            "quest_id": normalized_quest_id,
            "objective_id": objective_id,
            "event_type": event_type,
            "what_happened": happened,
            "what_i_learned": learned,
            "next_objective": next_step,
            "tags": tags or [],
            "source": SOURCE,
        }
    )
    journal_state.setdefault("entries", []).append(entry)
    return {"ok": True, "reason": "journal_entry_added", "entry": deepcopy(entry), "journal_state": deepcopy(journal_state), "source": SOURCE}


def add_journal_entry_from_objective_result(
    simulation_state: Dict[str, Any],
    objective_result: Dict[str, Any],
    *,
    turn_index: int = 0,
    what_i_learned: str = "",
    next_objective: str = "",
) -> Dict[str, Any]:
    result = _safe_dict(objective_result)
    if not result.get("ok"):
        return _reject("objective_result_not_ok", quest_id=_safe_str(result.get("quest_id")), objective_id=_safe_str(result.get("objective_id")))
    quest_id = _safe_str(result.get("quest_id"))
    objective_id = _safe_str(result.get("objective_id"))
    reason = _safe_str(result.get("reason")) or "objective_update"
    objective = _safe_dict(result.get("objective"))
    description = _safe_str(objective.get("description")) or objective_id
    status = _safe_str(objective.get("status")) or "open"
    happened = f"{reason}: {description} ({status})"
    if result.get("quest", {}).get("status") == "completed":
        next_objective = next_objective or "Return for the quest reward or ask about the next lead."
    return add_journal_entry(
        simulation_state,
        quest_id=quest_id,
        objective_id=objective_id,
        event_type=reason,
        what_happened=happened,
        what_i_learned=what_i_learned,
        next_objective=next_objective,
        turn_index=turn_index,
        tags=["quest", "objective", status],
    )


def build_quest_journal_summary(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    entries = [normalize_journal_entry(row) for row in _safe_list(_safe_dict(simulation_state.get("journal_state")).get("entries")) if isinstance(row, dict)]
    by_quest: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        quest_id = entry.get("quest_id") or "unassigned"
        bucket = by_quest.setdefault(quest_id, {"quest_id": quest_id, "entries": [], "latest_next_objective": "", "sources": []})
        bucket["entries"].append(entry)
        if entry.get("next_objective"):
            bucket["latest_next_objective"] = entry["next_objective"]
        if entry.get("source") and entry["source"] not in bucket["sources"]:
            bucket["sources"].append(entry["source"])
    return {"source": SOURCE, "entry_count": len(entries), "quests": list(by_quest.values())}


def render_quest_journal_report_html(report_data: Dict[str, Any]) -> str:
    summary = build_quest_journal_summary(_safe_dict(report_data.get("simulation_state")))
    turns = _safe_list(report_data.get("turns"))
    for turn in turns:
        journal_state = _safe_dict(turn).get("journal_state")
        if journal_state:
            turn_summary = build_quest_journal_summary({"journal_state": journal_state})
            summary["entry_count"] += turn_summary["entry_count"]
            summary["quests"].extend(turn_summary["quests"])
    if summary["entry_count"] <= 0:
        return ""
    rows = ["<section><h2>Quest Journal</h2>", f"<p>Deterministic journal entries: <strong>{summary['entry_count']}</strong></p>"]
    for quest in summary["quests"]:
        rows.append(f"<h3>{escape(_safe_str(quest.get('quest_id')))}</h3>")
        latest = _safe_str(quest.get("latest_next_objective"))
        if latest:
            rows.append(f"<p><strong>Next:</strong> {escape(latest)}</p>")
        rows.append("<ul>")
        for entry in _safe_list(quest.get("entries")):
            rows.append("<li>" + _format_entry(entry) + "</li>")
        rows.append("</ul>")
    rows.append(f"<p class=\"source\">Source: {SOURCE}</p></section>")
    return "\n".join(rows)


def _format_entry(entry: Dict[str, Any]) -> str:
    pieces = [f"Turn {escape(str(_safe_int(entry.get('turn_index'), 0)))}"]
    if entry.get("objective_id"):
        pieces.append(escape(_safe_str(entry.get("objective_id"))))
    if entry.get("what_happened"):
        pieces.append(escape(_safe_str(entry.get("what_happened"))))
    if entry.get("what_i_learned"):
        pieces.append("Learned: " + escape(_safe_str(entry.get("what_i_learned"))))
    if entry.get("next_objective"):
        pieces.append("Next: " + escape(_safe_str(entry.get("next_objective"))))
    return " — ".join(pieces)


def _build_entry_id(journal_state: Dict[str, Any], quest_id: str, objective_id: str, turn_index: int) -> str:
    sequence = len(_safe_list(journal_state.get("entries"))) + 1
    return f"journal:{quest_id}:{objective_id or 'quest'}:{int(turn_index or 0)}:{sequence}"


def _reject(reason: str, *, quest_id: str, objective_id: str = "") -> Dict[str, Any]:
    return {"ok": False, "reason": reason, "quest_id": quest_id, "objective_id": objective_id, "source": SOURCE}
