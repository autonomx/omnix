from __future__ import annotations

from typing import Any, Dict, List

_MAX_MEMORIES = 50


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


class NPCMemory:
    def __init__(self, npc_id: str, entries: List[Dict[str, Any]] | None = None):
        self.npc_id = _safe_str(npc_id)
        self.entries: List[Dict[str, Any]] = list(entries or [])

    def remember(self, event: Dict[str, Any], tick: int):
        idx = len(self.entries)
        memory = {
            "memory_id": f"mem:{self.npc_id}:{tick}:{idx}",
            "tick": int(tick),
            "type": _safe_str(event.get("type")),
            "actor": _safe_str(event.get("actor")),
            "target": _safe_str(event.get("target_id")),
            "location_id": _safe_str(event.get("location_id")),
            "faction_id": _safe_str(event.get("faction_id")),
            "summary": _safe_str(event.get("summary")),
            "salience": _safe_float(event.get("salience", 0.5)),
        }
        self.entries.append(memory)
        self._trim()

    def remember_many(self, events: List[Dict[str, Any]], tick: int):
        for e in events:
            self.remember(e, tick)

    def _trim(self):
        self.entries.sort(
            key=lambda x: (-x["salience"], -x["tick"], x["memory_id"])
        )
        self.entries = self.entries[:_MAX_MEMORIES]

    def top_memories(self, limit: int = 5) -> List[Dict[str, Any]]:
        ranked = sorted(
            self.entries,
            key=lambda x: (-x["salience"], -x["tick"], x["memory_id"])
        )
        return [dict(item) for item in ranked[:max(0, limit)]]

    def summary(self, limit: int = 5) -> List[str]:
        return [m["summary"] for m in self.entries[:limit] if m.get("summary")]

    def to_dict(self) -> Dict[str, Any]:
        return {"npc_id": self.npc_id, "entries": list(self.entries)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(data.get("npc_id", ""), data.get("entries") or [])