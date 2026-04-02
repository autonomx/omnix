"""Tier 21: Social Engine for processing social events and interactions."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .reputation_graph import ReputationGraph
from .alliance_system import AllianceSystem
from .rumor_system import RumorSystem


class SocialEventType(Enum):
    HELP = "help"
    ATTACK = "attack"
    BETRAYAL = "betrayal"
    TRADE = "trade"
    GOSSIP = "gossip"


@dataclass
class SocialEvent:
    event_type: SocialEventType
    actor: str
    target: str
    details: dict = field(default_factory=dict)


class SocialEngine:
    def __init__(self, reputation_graph: ReputationGraph, alliance_system: AllianceSystem, rumor_system: RumorSystem):
        self.rep = reputation_graph
        self.alliances = alliance_system
        self.rumors = rumor_system
        self._event_history: list[dict] = []

    def process_event(self, event: dict) -> list[dict]:
        actor = event.get("actor", "")
        target = event.get("target", "")
        event_type = event.get("type", "")

        if not actor:
            return []

        effects = []

        if event_type == "help":
            self.rep.update(actor, target, 0.3)
            self.rep.update(target, actor, 0.2)
            effects.append({"type": "reputation_change", "actor": actor, "target": target, "delta": 0.3})
            effects.append({"type": "reputation_change", "actor": target, "target": actor, "delta": 0.2})

        elif event_type == "attack":
            self.rep.update(actor, target, -0.5)
            self.rep.update(target, actor, -0.7)
            self.rumors.add_rumor(f"{actor} attacked {target}", target)
            effects.append({"type": "reputation_change", "actor": actor, "target": target, "delta": -0.5})

            # Propagate to allies of target
            target_faction = self.alliances.get_faction(target)
            if target_faction:
                for ally in self.alliances.get_faction_members(target):
                    self.rep.update(ally, actor, -0.3)
                    effects.append({"type": "reputation_change", "actor": ally, "target": actor, "delta": -0.3})

        elif event_type == "betrayal":
            # If they were allies, break alliance
            if self.alliances.are_allies(actor, target):
                self.alliances.break_alliance(actor, target)
            self.rep.update(actor, target, -0.8)
            self.rep.update(target, actor, -0.6)
            self.rumors.add_rumor(f"{actor} betrayed {target}", target)
            effects.append({"type": "alliance_broken", "actor": actor, "target": target})

        elif event_type == "trade":
            self.rep.update(actor, target, 0.1)
            self.rep.update(target, actor, 0.1)
            effects.append({"type": "reputation_change", "actor": actor, "target": target, "delta": 0.1})

        elif event_type == "gossip":
            content = event.get("content", f"{actor} gossiped about {target}")
            self.rumors.add_rumor(content, actor)
            effects.append({"type": "rumor_started", "actor": actor, "content": content})

        self._event_history.append(event)
        return effects

    def tick(self, npcs: list[str]) -> dict:
        expired_rumors = self.rumors.tick(npcs)
        return {
            "expired_rumors": expired_rumors,
            "active_rumors": self.rumors.get_active_count(),
            "faction_count": self.alliances.faction_count(),
        }

    def get_npc_social_context(self, npc: str) -> dict:
        return {
            "relationships": self.rep.top_relations(npc),
            "faction": self.alliances.get_faction(npc),
            "faction_members": list(self.alliances.get_faction_members(npc)),
            "rumors": self.rumors.get_rumors_known_by(npc),
        }

    def get_state_snapshot(self) -> dict:
        return {
            "reputation_edges": dict(self.rep.get_all_reputations()),
            "factions": self.alliances.list_factions(),
            "rumors": self.rumors.get_active_count(),
            "event_history": list(self._event_history),
        }

    def clear(self) -> None:
        self.rep.clear()
        self.alliances.clear()
        self.rumors.clear()
        self._event_history.clear()