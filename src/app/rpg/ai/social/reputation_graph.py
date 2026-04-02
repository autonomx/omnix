"""Tier 21: Reputation Graph for NPC social relationships."""

from __future__ import annotations
from collections import defaultdict


class ReputationGraph:
    def __init__(self) -> None:
        self._edges: dict[tuple[str, str], float] = defaultdict(float)

    def get(self, source: str, target: str) -> float:
        return self._edges.get((source, target), 0.0)

    def set(self, source: str, target: str, value: float) -> None:
        self._edges[(source, target)] = max(-1.0, min(1.0, value))

    def update(self, source: str, target: str, delta: float) -> float:
        current = self.get(source, target)
        new_val = max(-1.0, min(1.0, current + delta))
        self._edges[(source, target)] = new_val
        return new_val

    def neighbors(self, npc: str) -> set[str]:
        result = set()
        for (s, t) in self._edges:
            if s == npc or t == npc:
                result.add(t if s == npc else s)
        return result

    def top_relations(self, npc: str, n: int = 5) -> list[tuple[str, float]]:
        rels = [(t, v) for (s, t), v in self._edges.items() if s == npc]
        rels.sort(key=lambda x: x[1], reverse=True)
        return rels[:n]

    def worst_relations(self, npc: str, n: int = 5) -> list[tuple[str, float]]:
        rels = [(t, v) for (s, t), v in self._edges.items() if s == npc]
        rels.sort(key=lambda x: x[1])
        return rels[:n]

    def get_mutual_reputation(self, a: str, b: str) -> tuple[float, float]:
        return self.get(a, b), self.get(b, a)

    def get_average_reputation(self, npc: str) -> float:
        vals = [v for (s, _), v in self._edges.items() if s == npc]
        return sum(vals) / len(vals) if vals else 0.0

    def clear(self) -> None:
        self._edges.clear()

    def get_all_reputations(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for (s, t), v in self._edges.items():
            if s not in result:
                result[s] = {}
            result[s][t] = v
        return result