"""Tier 21: Group Decision Engine for NPC collective behavior."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DecisionType(Enum):
    ATTACK = "attack"
    FLEE = "flee"
    DEFEND = "defend"
    TRADE = "trade"
    TALK = "talk"


@dataclass
class NPCDecision:
    npc_id: str
    intent: str
    confidence: float = 0.5


class GroupDecisionEngine:
    def __init__(self):
        self.leaders: set[str] = set()

    def decide(self, npc_ids: list[str], decisions: dict[str, NPCDecision], strategy: str = "majority") -> Optional[NPCDecision]:
        if not npc_ids or not decisions:
            return None

        active_decisions = {npc_id: decisions[npc_id] for npc_id in npc_ids if npc_id in decisions}

        if not active_decisions:
            return None

        if strategy == "majority":
            return self._majority_decide(active_decisions)
        elif strategy == "weighted_majority":
            return self._weighted_majority_decide(active_decisions)
        elif strategy == "leader":
            return self._leader_decide(active_decisions)
        else:
            return self._majority_decide(active_decisions)

    def _majority_decide(self, decisions: dict[str, NPCDecision]) -> NPCDecision:
        intent_counts: dict[str, list[str]] = defaultdict(list)
        for npc_id, decision in decisions.items():
            intent_counts[decision.intent].append(npc_id)

        winning_intent = max(intent_counts.keys(), key=lambda i: len(intent_counts[i]))
        supporters = intent_counts[winning_intent]

        avg_confidence = sum(decisions[npc_id].confidence for npc_id in supporters) / len(supporters)

        return NPCDecision(
            npc_id=supporters[0],
            intent=winning_intent,
            confidence=avg_confidence
        )

    def _weighted_majority_decide(self, decisions: dict[str, NPCDecision]) -> NPCDecision:
        intent_weights: dict[str, float] = defaultdict(float)
        intent_supporters: dict[str, list[str]] = defaultdict(list)

        for npc_id, decision in decisions.items():
            intent_weights[decision.intent] += decision.confidence
            intent_supporters[decision.intent].append(npc_id)

        winning_intent = max(intent_weights.keys(), key=lambda i: intent_weights[i])
        total_weight = intent_weights[winning_intent]
        avg_weight = total_weight / len(intent_supporters[winning_intent])

        return NPCDecision(
            npc_id=intent_supporters[winning_intent][0],
            intent=winning_intent,
            confidence=avg_weight
        )

    def _leader_decide(self, decisions: dict[str, NPCDecision]) -> NPCDecision:
        for npc_id, decision in decisions.items():
            if npc_id in self.leaders:
                return NPCDecision(
                    npc_id=npc_id,
                    intent=decision.intent,
                    confidence=decision.confidence
                )

        # Fall back to majority if no leader has a decision
        return self._majority_decide(decisions)

    def add_leader(self, npc_id: str) -> None:
        self.leaders.add(npc_id)

    def remove_leader(self, npc_id: str) -> None:
        self.leaders.discard(npc_id)

    def set_leaders(self, leaders: set[str]) -> None:
        self.leaders = leaders

    def get_intents_summary(self, npc_ids: list[str], decisions: dict[str, NPCDecision]) -> dict[str, list[str]]:
        intent_map: dict[str, list[str]] = defaultdict(list)
        for npc_id in npc_ids:
            if npc_id in decisions:
                intent_map[decisions[npc_id].intent].append(npc_id)
        return dict(intent_map)