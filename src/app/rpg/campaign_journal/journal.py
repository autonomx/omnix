from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.rpg.campaign_journal.state import (
    MAX_CAMPAIGN_RECAP_ITEMS,
    ensure_campaign_journal_state,
    normalize_campaign_journal_state,
)
from app.rpg.lore.state import get_lore_entry
from app.rpg.npc_evolution.state import ensure_npc_evolution_state


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _stable_entry_id(*, kind: str, summary: str, turn_index: int, source_id: str = "") -> str:
    payload = json.dumps(
        {
            "kind": kind,
            "summary": summary,
            "turn_index": int(turn_index or 0),
            "source_id": source_id,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"journal:{digest}"


def _fact_status_from_lore(simulation_state: Dict[str, Any], lore_ids: List[str]) -> str:
    statuses = []
    for lore_id in lore_ids:
        entry = get_lore_entry(simulation_state, lore_id)
        if entry:
            statuses.append(str(entry.get("truth_status") or "unknown"))
    if not statuses:
        return "confirmed"
    if any(status == "secret" for status in statuses):
        return "secret"
    if any(status in {"rumor", "myth"} for status in statuses):
        return "rumor"
    if any(status == "unknown" for status in statuses):
        return "unknown"
    return "confirmed"


def _should_show_lore_entry(entry: Dict[str, Any]) -> bool:
    truth_status = str(entry.get("truth_status") or "unknown")
    if truth_status == "secret" and not bool(entry.get("revealed_to_player")):
        return False
    return bool(entry.get("revealed_to_player")) or truth_status in {"true", "rumor", "myth", "unknown"}


def record_campaign_journal_entry(
    simulation_state: Dict[str, Any],
    *,
    kind: str,
    summary: str,
    title: str = "",
    turn_index: int = 0,
    visibility: str = "player",
    fact_status: str = "",
    arc_ids: List[str] | None = None,
    lore_ids: List[str] | None = None,
    event_ids: List[str] | None = None,
    npc_ids: List[str] | None = None,
    quest_ids: List[str] | None = None,
    tags: List[str] | None = None,
    source_id: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not summary:
        return {"ok": False, "reason": "missing_summary"}
    state = ensure_campaign_journal_state(simulation_state)
    lore_ids = lore_ids or []
    if not fact_status:
        fact_status = _fact_status_from_lore(simulation_state, lore_ids)
    if fact_status == "secret" and visibility == "player":
        visibility = "hidden"
    entry_id = _stable_entry_id(
        kind=kind,
        summary=summary,
        turn_index=turn_index,
        source_id=source_id,
    )
    existing = [
        row
        for row in state.get("entries") or []
        if row.get("entry_id") == entry_id
    ]
    if existing:
        return {
            "ok": True,
            "reason": "already_recorded",
            "entry": existing[0],
        }
    entry = {
        "entry_id": entry_id,
        "turn_index": int(turn_index or 0),
        "kind": kind,
        "title": title or kind.replace("_", " ").title(),
        "summary": summary,
        "visibility": visibility,
        "fact_status": fact_status,
        "arc_ids": arc_ids or [],
        "lore_ids": lore_ids,
        "event_ids": event_ids or [],
        "npc_ids": npc_ids or [],
        "quest_ids": quest_ids or [],
        "tags": tags or [],
        "metadata": metadata or {},
    }
    state.setdefault("entries", []).append(entry)
    simulation_state["campaign_journal_state"] = normalize_campaign_journal_state(state)
    return {
        "ok": True,
        "reason": "recorded",
        "entry": entry,
    }


def _journal_entries(simulation_state: Dict[str, Any], *, include_hidden: bool = False) -> List[Dict[str, Any]]:
    state = ensure_campaign_journal_state(simulation_state)
    entries = list(state.get("entries") or [])
    if not include_hidden:
        entries = [row for row in entries if row.get("visibility") == "player"]
    entries.sort(key=lambda row: (int(row.get("turn_index") or 0), str(row.get("entry_id") or "")))
    return entries


def _known_lore_rows(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    lore_state = _safe_dict(simulation_state.get("lore_state"))
    entries = _safe_dict(lore_state.get("entries"))
    rows = []
    for lore_id, entry in entries.items():
        entry = _safe_dict(entry)
        if not _should_show_lore_entry(entry):
            continue
        rows.append(
            {
                "lore_id": str(lore_id),
                "title": entry.get("title") or str(lore_id),
                "truth_status": entry.get("truth_status") or "unknown",
                "summary": entry.get("summary") or "",
                "tags": list(entry.get("tags") or [])[:10],
            }
        )
    rows.sort(key=lambda row: (str(row.get("truth_status") or ""), str(row.get("lore_id") or "")))
    return rows[:MAX_CAMPAIGN_RECAP_ITEMS]


def _active_arc_rows(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    arc_state = _safe_dict(simulation_state.get("story_arc_state"))
    arcs = _safe_dict(arc_state.get("arcs"))
    rows = []
    for arc_id, arc in arcs.items():
        arc = _safe_dict(arc)
        if arc.get("status") in {"resolved", "failed"}:
            continue
        rows.append(
            {
                "arc_id": str(arc_id),
                "title": arc.get("title") or str(arc_id),
                "status": arc.get("status") or "active",
                "stage": arc.get("stage") or "",
                "pressure": int(arc.get("pressure") or 0),
                "linked_lore": list(arc.get("linked_lore") or [])[:10],
                "linked_entities": list(arc.get("linked_entities") or [])[:10],
            }
        )
    rows.sort(key=lambda row: (-int(row.get("pressure") or 0), str(row.get("arc_id") or "")))
    return rows[:MAX_CAMPAIGN_RECAP_ITEMS]


def _recent_applied_event_rows(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = _safe_dict(simulation_state.get("story_event_state"))
    applied = _safe_dict(state.get("applied_events"))
    rows = []
    for event_id, event in applied.items():
        event = _safe_dict(event)
        rows.append(
            {
                "event_id": str(event_id),
                "arc_id": event.get("arc_id") or "",
                "turn_index": int(event.get("turn_index") or event.get("applied_turn") or 0),
                "summary": event.get("summary") or event.get("reason") or "",
                "kind": event.get("kind") or "story_event",
            }
        )
    rows.sort(key=lambda row: (int(row.get("turn_index") or 0), str(row.get("event_id") or "")), reverse=True)
    return rows[:MAX_CAMPAIGN_RECAP_ITEMS]


def _pending_queue_rows(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    queue_state = _safe_dict(simulation_state.get("story_event_queue_state"))
    rows = []
    for item in _safe_list(queue_state.get("pending")):
        item = _safe_dict(item)
        rows.append(
            {
                "queue_id": item.get("queue_id"),
                "event_id": item.get("event_id"),
                "due_turn": int(item.get("due_turn") or 0),
                "priority": int(item.get("priority") or 0),
                "reason": item.get("reason") or "",
                "source": item.get("source") or "",
            }
        )
    rows.sort(key=lambda row: (int(row.get("due_turn") or 0), -int(row.get("priority") or 0)))
    return rows[:MAX_CAMPAIGN_RECAP_ITEMS]


def _npc_evolution_rows(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    state = ensure_npc_evolution_state(simulation_state)
    rows = []
    for npc_id, evolution in _safe_dict(state.get("npcs")).items():
        evolution = _safe_dict(evolution)
        if not evolution.get("active_arcs") and not evolution.get("motivation") and not evolution.get("companion_eligible"):
            continue
        rows.append(
            {
                "npc_id": str(npc_id),
                "active_arcs": list(evolution.get("active_arcs") or [])[:10],
                "profession": evolution.get("profession") or "",
                "role": evolution.get("role") or "",
                "motivation": evolution.get("motivation") or "",
                "companion_eligible": bool(evolution.get("companion_eligible")),
                "flags": dict(_safe_dict(evolution.get("flags"))),
            }
        )
    rows.sort(key=lambda row: str(row.get("npc_id") or ""))
    return rows[:MAX_CAMPAIGN_RECAP_ITEMS]


def _party_rows(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.rpg.companions.party import ensure_party_state
    state = ensure_party_state(simulation_state)
    rows = []
    for npc_id, member in _safe_dict(state.get("members")).items():
        member = _safe_dict(member)
        if member.get("status") != "active":
            continue
        rows.append(
            {
                "npc_id": str(npc_id),
                "role": member.get("role") or "",
                "motivation": member.get("motivation") or "",
                "joined_turn": int(member.get("joined_turn") or 0),
            }
        )
    rows.sort(key=lambda row: (int(row.get("joined_turn") or 0), str(row.get("npc_id") or "")))
    return rows[:MAX_CAMPAIGN_RECAP_ITEMS]


def build_campaign_journal(
    simulation_state: Dict[str, Any],
    *,
    include_hidden: bool = False,
    max_entries: int = MAX_CAMPAIGN_RECAP_ITEMS,
) -> Dict[str, Any]:
    entries = _journal_entries(simulation_state, include_hidden=include_hidden)[-max_entries:]
    return {
        "ok": True,
        "entries": entries,
        "known_lore": _known_lore_rows(simulation_state),
        "active_arcs": _active_arc_rows(simulation_state),
        "recent_events": _recent_applied_event_rows(simulation_state),
        "pending_consequences": _pending_queue_rows(simulation_state),
        "npc_evolution": _npc_evolution_rows(simulation_state),
        "party": _party_rows(simulation_state),
        "bounded": {
            "max_entries": max_entries,
            "max_recap_items": MAX_CAMPAIGN_RECAP_ITEMS,
        },
    }


def build_player_story_recap(
    simulation_state: Dict[str, Any],
    *,
    turn_index: int = 0,
    max_items: int = MAX_CAMPAIGN_RECAP_ITEMS,
) -> Dict[str, Any]:
    journal = build_campaign_journal(simulation_state, include_hidden=False, max_entries=max_items)
    latest_entries = list(journal.get("entries") or [])[-max_items:]
    recent_events = list(journal.get("recent_events") or [])[:max_items]
    return {
        "ok": True,
        "format_version": "campaign_story_recap_v1",
        "turn_index": int(turn_index or 0),
        "latest_journal_entries": latest_entries,
        "known_lore": list(journal.get("known_lore") or [])[:max_items],
        "active_arcs": list(journal.get("active_arcs") or [])[:max_items],
        "recent_events": recent_events,
        "pending_consequences": list(journal.get("pending_consequences") or [])[:max_items],
        "npc_evolution": list(journal.get("npc_evolution") or [])[:max_items],
        "party": list(journal.get("party") or [])[:max_items],
        "narrator_context": {
            "rules": [
                "Use only facts in this recap.",
                "Mark rumors as rumors.",
                "Do not reveal hidden or secret lore.",
                "Do not invent rewards, quests, deaths, or outcomes.",
            ],
            "story_so_far": latest_entries,
            "current_arcs": list(journal.get("active_arcs") or [])[:max_items],
            "known_rumors": [
                row
                for row in list(journal.get("known_lore") or [])
                if row.get("truth_status") in {"rumor", "myth", "unknown"}
            ][:max_items],
        },
        "bounded": {
            "max_items": max_items,
            "max_recap_items": MAX_CAMPAIGN_RECAP_ITEMS,
        },
    }