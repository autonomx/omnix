from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Tuple


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _event_turn(event: Mapping[str, Any]) -> int:
    try:
        return int(event.get("turn") or event.get("turn_index") or 0)
    except Exception:
        return 0


def _importance(value: Mapping[str, Any]) -> int:
    try:
        return int(value.get("importance") or value.get("intensity") or value.get("priority") or 0)
    except Exception:
        return 0


def expire_world_signals(
    *,
    world_signals: Iterable[Mapping[str, Any]],
    current_turn: int,
) -> Dict[str, Any]:
    active: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []

    for raw in _safe_list(list(world_signals)):
        signal = dict(_safe_dict(raw))
        created_turn = int(signal.get("created_turn") or signal.get("turn") or 0)
        ttl_turns = int(signal.get("ttl_turns") or 0)

        if ttl_turns > 0 and created_turn > 0 and current_turn - created_turn >= ttl_turns:
            signal["expired_turn"] = current_turn
            expired.append(signal)
        else:
            active.append(signal)

    return {
        "ok": True,
        "active": active,
        "expired": expired,
        "active_count": len(active),
        "expired_count": len(expired),
    }


def compact_event_history(
    *,
    events: Iterable[Mapping[str, Any]],
    current_turn: int,
    keep_recent_turns: int = 25,
    keep_recent_count: int = 50,
    keep_important_count: int = 25,
) -> Dict[str, Any]:
    rows = [dict(_safe_dict(event)) for event in _safe_list(list(events))]
    recent_cutoff = max(0, int(current_turn) - int(keep_recent_turns))

    recent = [
        row for row in rows
        if _event_turn(row) >= recent_cutoff
    ]

    old = [
        row for row in rows
        if _event_turn(row) < recent_cutoff
    ]

    recent = sorted(recent, key=_event_turn)[-keep_recent_count:]

    important = sorted(
        old,
        key=lambda row: (_importance(row), _event_turn(row)),
        reverse=True,
    )[:keep_important_count]

    kept_keys = {
        id(row) for row in recent
    } | {
        id(row) for row in important
    }

    compacted_count = max(0, len(rows) - len(recent) - len(important))

    summary = {
        "compacted_count": compacted_count,
        "oldest_turn": min([_event_turn(row) for row in rows], default=0),
        "newest_turn": max([_event_turn(row) for row in rows], default=0),
        "kept_recent_count": len(recent),
        "kept_important_count": len(important),
    }

    return {
        "ok": True,
        "kept": sorted(recent + important, key=_event_turn),
        "summary": summary,
        "compacted_count": compacted_count,
    }


def compact_story_arcs(
    *,
    story_arcs: Mapping[str, Any],
    current_turn: int,
    keep_history_recent_turns: int = 25,
    keep_history_recent_count: int = 20,
    keep_history_important_count: int = 10,
) -> Dict[str, Any]:
    arcs: Dict[str, Any] = {}
    compacted_histories: Dict[str, Any] = {}

    for arc_id, raw_arc in _safe_dict(story_arcs).items():
        arc = dict(_safe_dict(raw_arc))
        history = _safe_list(arc.get("history"))

        compacted = compact_event_history(
            events=history,
            current_turn=current_turn,
            keep_recent_turns=keep_history_recent_turns,
            keep_recent_count=keep_history_recent_count,
            keep_important_count=keep_history_important_count,
        )

        if compacted.get("compacted_count"):
            arc["history"] = compacted.get("kept", [])
            arc["history_compaction_summary"] = compacted.get("summary", {})
            compacted_histories[str(arc_id)] = compacted.get("summary", {})

        arcs[str(arc_id)] = arc

    return {
        "ok": True,
        "story_arcs": arcs,
        "compacted_histories": compacted_histories,
        "compacted_arc_count": len(compacted_histories),
    }


def compact_faction_reputation(
    *,
    faction_state: Mapping[str, Any],
    current_turn: int,
    keep_recent_turns: int = 30,
    keep_recent_count: int = 20,
    keep_important_count: int = 8,
) -> Dict[str, Any]:
    factions: Dict[str, Any] = {}
    compacted: Dict[str, Any] = {}

    for faction_id, raw in _safe_dict(faction_state).items():
        row = dict(_safe_dict(raw))
        history = _safe_list(row.get("history"))

        compressed = compact_event_history(
            events=history,
            current_turn=current_turn,
            keep_recent_turns=keep_recent_turns,
            keep_recent_count=keep_recent_count,
            keep_important_count=keep_important_count,
        )

        if compressed.get("compacted_count"):
            row["history"] = compressed.get("kept", [])
            row["history_compaction_summary"] = compressed.get("summary", {})
            compacted[str(faction_id)] = compressed.get("summary", {})

        factions[str(faction_id)] = row

    return {
        "ok": True,
        "factions": factions,
        "compacted_faction_count": len(compacted),
        "compacted": compacted,
    }


def age_npc_memory_events(
    *,
    npc_memory_events: Iterable[Mapping[str, Any]],
    current_turn: int,
    keep_recent_turns: int = 40,
    max_memories: int = 50,
) -> Dict[str, Any]:
    memories = [dict(_safe_dict(memory)) for memory in _safe_list(list(npc_memory_events))]
    aged: List[Dict[str, Any]] = []

    for memory in memories:
        created_turn = int(memory.get("created_turn") or memory.get("turn") or 0)
        age = int(current_turn) - created_turn if created_turn else 0
        importance = _importance(memory)

        memory["age_turns"] = age
        memory["decayed_importance"] = max(0, importance - max(0, age // 40))

        if age <= keep_recent_turns or memory["decayed_importance"] >= 2:
            aged.append(memory)

    aged = sorted(
        aged,
        key=lambda memory: (int(memory.get("decayed_importance") or 0), int(memory.get("turn") or memory.get("created_turn") or 0)),
        reverse=True,
    )[:max_memories]

    return {
        "ok": True,
        "memories": aged,
        "kept_count": len(aged),
        "dropped_count": max(0, len(memories) - len(aged)),
    }


def estimate_state_size_bytes(value: Any) -> int:
    import json

    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8"))


def build_state_budget_summary(
    *,
    state: Mapping[str, Any],
    budgets: Mapping[str, int] | None = None,
) -> Dict[str, Any]:
    budgets = _safe_dict(budgets) or {
        "summary_bytes": 2_000_000,
        "story_arcs_bytes": 250_000,
        "world_signals_bytes": 200_000,
        "faction_state_bytes": 100_000,
        "npc_memory_events_bytes": 150_000,
    }

    sections = {
        "summary": state,
        "story_arcs": _safe_dict(state.get("story_arcs")),
        "world_signals": _safe_list(state.get("world_signals")),
        "faction_state": _safe_dict(state.get("faction_reputation")),
        "npc_memory_events": _safe_list(state.get("npc_memory_events")),
    }

    rows: Dict[str, Any] = {}
    ok = True

    for name, section in sections.items():
        size = estimate_state_size_bytes(section)
        budget = int(budgets.get(f"{name}_bytes") or budgets.get("summary_bytes") or 0)
        section_ok = size <= budget if budget > 0 else True
        ok = ok and section_ok
        rows[name] = {
            "bytes": size,
            "budget_bytes": budget,
            "ok": section_ok,
        }

    return {
        "format_version": "state_budget_summary_v1",
        "ok": ok,
        "sections": rows,
        "budgets": dict(budgets),
    }


def compress_world_state_snapshot(
    *,
    state: Mapping[str, Any],
    current_turn: int,
) -> Dict[str, Any]:
    state = dict(_safe_dict(state))

    world_signals_result = expire_world_signals(
        world_signals=_safe_list(state.get("world_signals")),
        current_turn=current_turn,
    )
    story_arcs_result = compact_story_arcs(
        story_arcs=_safe_dict(state.get("story_arcs")),
        current_turn=current_turn,
    )
    faction_result = compact_faction_reputation(
        faction_state=_safe_dict(state.get("faction_reputation")),
        current_turn=current_turn,
    )
    npc_memory_result = age_npc_memory_events(
        npc_memory_events=_safe_list(state.get("npc_memory_events")),
        current_turn=current_turn,
    )

    compressed = dict(state)
    compressed["world_signals"] = world_signals_result.get("active", [])
    compressed["expired_world_signals"] = world_signals_result.get("expired", [])
    compressed["story_arcs"] = story_arcs_result.get("story_arcs", {})
    compressed["faction_reputation"] = faction_result.get("factions", {})
    compressed["npc_memory_events"] = npc_memory_result.get("memories", [])

    budget = build_state_budget_summary(state=compressed)

    return {
        "ok": True,
        "compressed_state": compressed,
        "world_signals": world_signals_result,
        "story_arcs": story_arcs_result,
        "faction_reputation": faction_result,
        "npc_memory": npc_memory_result,
        "state_budget_summary": budget,
    }