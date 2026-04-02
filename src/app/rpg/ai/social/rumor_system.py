"""Tier 21: Rumor System for social information spread."""
from __future__ import annotations
from dataclasses import dataclass, field
import random


@dataclass
class Rumor:
    content: str
    originator: str
    known_by: set = field(default_factory=set)
    ttl: int = 10
    active: bool = True


class RumorSystem:
    def __init__(self, spread_probability=0.5, default_ttl=10):
        self._rumors = []
        self.spread_probability = spread_probability
        self.default_ttl = default_ttl

    def add_rumor(self, content, originator):
        r = Rumor(content=content, originator=originator, known_by={originator}, ttl=self.default_ttl)
        self._rumors.append(r)
        return r

    def get_rumors_known_by(self, npc):
        result = []
        for r in self._rumors:
            if r.active and npc in r.known_by:
                result.append({"content": r.content, "originator": r.originator})
        return result

    def get_rumors_about(self, npc):
        result = []
        for r in self._rumors:
            if npc in r.content:
                result.append({"content": r.content, "originator": r.originator})
        return result

    def who_knows_rumor(self, content):
        result = set()
        for r in self._rumors:
            if r.content == content and r.active:
                result.update(r.known_by)
        return list(result)

    def get_active_count(self):
        return sum(1 for r in self._rumors if r.active)

    def tick(self, npcs):
        expired = []
        to_spread = []
        for rumor in self._rumors:
            if not rumor.active:
                continue
            rumor.ttl -= 1
            if rumor.ttl <= 0:
                rumor.active = False
                expired.append(rumor.content)
                continue
            for npc in npcs:
                if npc not in rumor.known_by and random.random() < self.spread_probability:
                    to_spread.append((npc, rumor))
        for npc, rumor in to_spread:
            rumor.known_by.add(npc)
        return expired

    def clear(self):
        self._rumors.clear()
