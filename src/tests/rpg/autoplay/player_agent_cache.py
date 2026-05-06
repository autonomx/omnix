from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional


class PlayerAgentDecisionCache:
    def __init__(self, *, max_entries: int = 256) -> None:
        self.max_entries = max(1, int(max_entries))
        self._rows: Dict[str, Dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0
        self.stores = 0
        self.rejected_stores = 0

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not key:
            self.misses += 1
            return None
        row = self._rows.get(key)
        if not row:
            self.misses += 1
            return None
        self.hits += 1
        return deepcopy(row)

    def put(self, key: str, value: Dict[str, Any]) -> None:
        if not key or not isinstance(value, dict):
            self.rejected_stores += 1
            return
        # Only cache successful LLM decisions. Fallback/scripted decisions must
        # not become cache hits masquerading as LLM output.
        if value.get("source") != "llm_player_agent":
            self.rejected_stores += 1
            return
        if not value.get("ok") or not value.get("action"):
            self.rejected_stores += 1
            return
        if len(self._rows) >= self.max_entries:
            oldest = next(iter(self._rows.keys()))
            self._rows.pop(oldest, None)
        self._rows[key] = deepcopy(value)
        self.stores += 1

    def summary(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self._rows),
            "hits": self.hits,
            "misses": self.misses,
            "stores": self.stores,
            "rejected_stores": self.rejected_stores,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }