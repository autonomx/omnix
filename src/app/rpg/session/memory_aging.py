"""Deterministic aging and compaction helpers for RPG memory."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Set, Tuple

from .memory_writer import (
    MAX_MEMORY_TEXT,
    make_memory_entry,
    memory_state_from_session,
)

MEMORY_AGING_VERSION = "rpg_memory_aging_v1"
MEMORY_AGING_SOURCE = "memory_aging"
RECAP_MEMORY_KIND = "recap"
DEFAULT_DECAY_TICK_INTERVAL = 10
DEFAULT_ACTIVE_MEMORY_LIMIT = 24
MAX_MEMORY_SALIENCE = 10
MIN_COMPACTED_ENTRIES = 2


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _clean_id(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()[:120]
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _clean_text(value: Any, limit: int = MAX_MEMORY_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:limit]


def _clean_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _positive_int(value: Any, default: int) -> int:
    cleaned = _clean_int(value, default)
    return cleaned if cleaned > 0 else default


def _bounded_salience(value: Any) -> int:
    return max(0, min(MAX_MEMORY_SALIENCE, _clean_int(value)))


def _entry_tick(entry: Dict[str, Any]) -> int:
    return max(0, _clean_int(entry.get("tick")))


def _entry_id(entry: Dict[str, Any]) -> str:
    return _clean_id(entry.get("id"))


def _entry_kind(entry: Dict[str, Any]) -> str:
    return _clean_id(entry.get("kind")).casefold()


def _entry_tags(entries: Iterable[Dict[str, Any]]) -> List[str]:
    tags: List[str] = ["recap", "compressed_memory"]
    for entry in entries:
        for tag in _safe_list(entry.get("tags")):
            clean = _clean_id(tag).casefold()
            if clean and clean not in tags:
                tags.append(clean)
            if len(tags) >= 12:
                return tags
    return tags


def _memory_state_to_session(session: Dict[str, Any], memory: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    updated = deepcopy(_safe_dict(session))
    runtime = dict(_safe_dict(updated.get("runtime_state")))
    runtime["memory"] = memory
    runtime["memory_aging"] = summary
    updated["runtime_state"] = runtime
    return updated


def _age_entry(entry: Dict[str, Any], *, current_tick: int, decay_tick_interval: int) -> Dict[str, Any]:
    aged = dict(entry)
    tick = _entry_tick(aged)
    age_ticks = max(0, current_tick - tick)
    decay_steps = age_ticks // decay_tick_interval
    salience = _bounded_salience(aged.get("salience"))
    aged["salience"] = max(0, salience - decay_steps)
    aged["age_ticks"] = age_ticks
    aged["last_aged_tick"] = current_tick
    return aged


def _compaction_sort_key(indexed_entry: Tuple[int, Dict[str, Any]]) -> Tuple[int, int, str]:
    index, entry = indexed_entry
    return (
        _bounded_salience(entry.get("salience")),
        _entry_tick(entry),
        _entry_id(entry) or f"index:{index:06d}",
    )


def _recap_text(entries: List[Dict[str, Any]]) -> str:
    pieces: List[str] = []
    for entry in entries:
        entry_id = _entry_id(entry) or "memory"
        kind = _entry_kind(entry) or "memory"
        text = _clean_text(entry.get("text"), limit=120)
        if text:
            pieces.append(f"{entry_id} {kind}: {text}")
    if not pieces:
        return ""
    return _clean_text(
        f"Memory recap of {len(pieces)} older entries: " + " / ".join(pieces),
        limit=MAX_MEMORY_TEXT,
    )


def _build_recap_entry(memory: Dict[str, Any], entries: List[Dict[str, Any]], *, current_tick: int) -> Dict[str, Any] | None:
    text = _recap_text(entries)
    if not text:
        return None
    recap = make_memory_entry(
        memory,
        kind=RECAP_MEMORY_KIND,
        text=text,
        tick=current_tick,
        turn_id=f"memory-aging:{current_tick}",
        salience=max((_bounded_salience(entry.get("salience")) for entry in entries), default=1),
        tags=_entry_tags(entries),
        source=MEMORY_AGING_SOURCE,
    )
    recap["compressed_entry_ids"] = [_entry_id(entry) for entry in entries if _entry_id(entry)]
    recap["compression"] = {
        "format_version": MEMORY_AGING_VERSION,
        "source": MEMORY_AGING_SOURCE,
        "policy": "lowest_salience_oldest_first",
        "entry_count": len(entries),
    }
    return recap


def reinforce_memory_entries(
    session: Dict[str, Any],
    memory_ids: Iterable[Any],
    *,
    amount: int = 1,
    current_tick: int = 0,
) -> Dict[str, Any]:
    """Return a copied session with selected memory salience reinforced."""
    memory = memory_state_from_session(session)
    targets: Set[str] = {_clean_id(memory_id) for memory_id in memory_ids if _clean_id(memory_id)}
    increment = max(0, _clean_int(amount, 1))
    tick = max(0, _clean_int(current_tick))
    reinforced = 0
    entries: List[Dict[str, Any]] = []
    for entry in _safe_list(memory.get("entries")):
        updated = dict(_safe_dict(entry))
        if _entry_id(updated) in targets and increment:
            updated["salience"] = min(MAX_MEMORY_SALIENCE, _bounded_salience(updated.get("salience")) + increment)
            updated["reinforcement_count"] = _clean_int(updated.get("reinforcement_count")) + 1
            updated["last_reinforced_tick"] = tick
            reinforced += 1
        entries.append(updated)
    memory["entries"] = entries
    summary = {
        "format_version": MEMORY_AGING_VERSION,
        "source": MEMORY_AGING_SOURCE,
        "operation": "reinforce",
        "current_tick": tick,
        "target_ids": sorted(targets),
        "reinforced_count": reinforced,
    }
    return _memory_state_to_session(session, memory, summary)


def age_and_compact_memory(
    session: Dict[str, Any],
    *,
    current_tick: int,
    active_limit: int = DEFAULT_ACTIVE_MEMORY_LIMIT,
    decay_tick_interval: int = DEFAULT_DECAY_TICK_INTERVAL,
) -> Dict[str, Any]:
    """Return a copied session with aged salience and bounded recap compaction."""
    memory = memory_state_from_session(session)
    tick = max(0, _clean_int(current_tick))
    limit = _positive_int(active_limit, DEFAULT_ACTIVE_MEMORY_LIMIT)
    interval = _positive_int(decay_tick_interval, DEFAULT_DECAY_TICK_INTERVAL)
    aged_entries = [
        _age_entry(_safe_dict(entry), current_tick=tick, decay_tick_interval=interval)
        for entry in _safe_list(memory.get("entries"))
    ]
    compacted_entries: List[Dict[str, Any]] = []
    recap_entry: Dict[str, Any] | None = None
    if len(aged_entries) > limit:
        compact_count = len(aged_entries) - limit + 1
        indexed_candidates = [
            (index, entry)
            for index, entry in enumerate(aged_entries)
            if _entry_kind(entry) != RECAP_MEMORY_KIND
        ]
        compact_indexes = {
            index
            for index, _entry in sorted(indexed_candidates, key=_compaction_sort_key)[:compact_count]
        }
        if len(compact_indexes) >= MIN_COMPACTED_ENTRIES:
            compacted_entries = [
                entry
                for index, entry in enumerate(aged_entries)
                if index in compact_indexes
            ]
            recap_entry = _build_recap_entry(memory, compacted_entries, current_tick=tick)
            if recap_entry is not None:
                aged_entries = [
                    entry
                    for index, entry in enumerate(aged_entries)
                    if index not in compact_indexes
                ]
                aged_entries.append(recap_entry)
    memory["entries"] = aged_entries
    summary = {
        "format_version": MEMORY_AGING_VERSION,
        "source": MEMORY_AGING_SOURCE,
        "operation": "age_and_compact",
        "current_tick": tick,
        "active_limit": limit,
        "decay_tick_interval": interval,
        "aged_count": len(_safe_list(memory_state_from_session(session).get("entries"))),
        "compacted_count": len(compacted_entries),
        "recap_id": _entry_id(recap_entry or {}),
        "compressed_entry_ids": [_entry_id(entry) for entry in compacted_entries if _entry_id(entry)],
        "final_entry_count": len(aged_entries),
    }
    return _memory_state_to_session(session, memory, summary)
