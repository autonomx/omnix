from __future__ import annotations

from typing import Any, Dict, List

MAX_CAMPAIGN_JOURNAL_ENTRIES = 300
MAX_CAMPAIGN_RECAP_ITEMS = 25


VALID_JOURNAL_VISIBILITY = {"player", "hidden", "debug"}
VALID_JOURNAL_FACT_STATUS = {"confirmed", "rumor", "unknown", "secret"}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _unique_strs(values: Any, *, limit: int = 50) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in _safe_list(values):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def normalize_campaign_journal_entry(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    visibility = _safe_str(value.get("visibility")) or "player"
    if visibility not in VALID_JOURNAL_VISIBILITY:
        visibility = "player"
    fact_status = _safe_str(value.get("fact_status")) or "confirmed"
    if fact_status not in VALID_JOURNAL_FACT_STATUS:
        fact_status = "unknown"
    return {
        "entry_id": _safe_str(value.get("entry_id")),
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "kind": _safe_str(value.get("kind")) or "story",
        "title": _safe_str(value.get("title")),
        "summary": _safe_str(value.get("summary")),
        "visibility": visibility,
        "fact_status": fact_status,
        "arc_ids": _unique_strs(value.get("arc_ids"), limit=20),
        "lore_ids": _unique_strs(value.get("lore_ids"), limit=20),
        "event_ids": _unique_strs(value.get("event_ids"), limit=20),
        "npc_ids": _unique_strs(value.get("npc_ids"), limit=20),
        "quest_ids": _unique_strs(value.get("quest_ids"), limit=20),
        "tags": _unique_strs(value.get("tags"), limit=20),
        "metadata": dict(_safe_dict(value.get("metadata"))),
    }


def normalize_campaign_journal_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    value = _safe_dict(value)
    entries = [
        normalize_campaign_journal_entry(row)
        for row in _safe_list(value.get("entries"))
        if isinstance(row, dict)
    ]
    entries = [
        row
        for row in entries
        if row.get("entry_id") and row.get("summary")
    ][-MAX_CAMPAIGN_JOURNAL_ENTRIES:]
    entries.sort(
        key=lambda row: (
            int(row.get("turn_index") or 0),
            str(row.get("entry_id") or ""),
        )
    )
    return {
        "version": 1,
        "entries": entries,
        "max_entries": MAX_CAMPAIGN_JOURNAL_ENTRIES,
        "max_recap_items": MAX_CAMPAIGN_RECAP_ITEMS,
    }


def ensure_campaign_journal_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_campaign_journal_state(simulation_state.get("campaign_journal_state"))
    simulation_state["campaign_journal_state"] = state
    return state