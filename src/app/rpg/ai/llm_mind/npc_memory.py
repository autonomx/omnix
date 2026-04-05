from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


_MAX_MEMORIES = 32


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _memory_sort_key(item: Dict[str, Any]):
    salience = _safe_float(item.get("salience"), 0.0)
    tick = int(item.get("tick", 0) or 0)
    memory_id = _safe_str(item.get("memory_id"))
    return (-salience, -tick, memory_id)


@dataclass
class NPCMemory:
    npc_id: str
    entries: List[Dict[str, Any]] = field(default_factory=list)
    max_entries: int = _MAX_MEMORIES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "entries": [dict(entry) for entry in self.entries],
            "max_entries": int(self.max_entries),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "NPCMemory":
        data = data or {}
        npc_id = _safe_str(data.get("npc_id"))
        max_entries = int(data.get("max_entries", _MAX_MEMORIES) or _MAX_MEMORIES)
        raw_entries = data.get("entries") or []
        entries: List[Dict[str, Any]] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            entries.append({
                "memory_id": _safe_str(item.get("memory_id")),
                "tick": int(item.get("tick", 0) or 0),
                "type": _safe_str(item.get("type")),
                "actor": _safe_str(item.get("actor")),
                "target_id": _safe_str(item.get("target_id")),
                "target_kind": _safe_str(item.get("target_kind")),
                "location_id": _safe_str(item.get("location_id")),
                "faction_id": _safe_str(item.get("faction_id")),
                "summary": _safe_str(item.get("summary")),
                "salience": _clamp01(_safe_float(item.get("salience"), 0.0)),
            })
        memory = cls(npc_id=npc_id, entries=entries, max_entries=max_entries)
        memory._trim()
        return memory

    def _trim(self) -> None:
        self.entries = sorted(self.entries, key=_memory_sort_key)[: self.max_entries]
        self.entries = sorted(
            self.entries,
            key=lambda item: (
                int(item.get("tick", 0) or 0),
                _safe_str(item.get("memory_id")),
            ),
        )

    def remember(self, event: Dict[str, Any], tick: int, index: int = 0) -> None:
        event = event or {}
        event_type = _safe_str(event.get("type")) or "unknown"
        actor = _safe_str(event.get("actor"))
        target_id = _safe_str(event.get("target_id"))
        target_kind = _safe_str(event.get("target_kind"))
        location_id = _safe_str(event.get("location_id"))
        faction_id = _safe_str(event.get("faction_id"))
        summary = _safe_str(event.get("summary")) or event_type

        salience = _clamp01(_safe_float(event.get("salience"), 0.4))
        if actor == "player":
            salience = max(salience, 0.7)
        if target_id == self.npc_id:
            salience = max(salience, 0.9)

        memory_id = f"mem:{self.npc_id}:{tick}:{index}:{event_type}:{target_id or 'none'}"

        self.entries.append({
            "memory_id": memory_id,
            "tick": int(tick),
            "type": event_type,
            "actor": actor,
            "target_id": target_id,
            "target_kind": target_kind,
            "location_id": location_id,
            "faction_id": faction_id,
            "summary": summary,
            "salience": salience,
        })
        self._trim()

    def remember_many(self, events: List[Dict[str, Any]], tick: int) -> None:
        for index, event in enumerate(events):
            self.remember(event, tick=tick, index=index)

    def top_memories(self, limit: int = 5) -> List[Dict[str, Any]]:
        ranked = sorted(self.entries, key=_memory_sort_key)
        return [dict(item) for item in ranked[: max(0, limit)]]

    def summary(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.top_memories(limit=limit)
