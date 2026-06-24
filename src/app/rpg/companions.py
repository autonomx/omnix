"""Deterministic party and companion helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping, Sequence

CompanionRole = Literal["fighter", "healer", "scout", "merchant", "guide", "scholar", "lockpick", "face"]
CompanionDecision = Literal["joined", "left", "blocked"]


@dataclass(frozen=True)
class CompanionState:
    npc_id: str
    role: CompanionRole
    loyalty: int = 0
    morale: int = 0
    fear: int = 0
    debt: int = 0
    personal_goal: str = ""
    in_party: bool = False

    def with_delta(self, *, loyalty: int = 0, morale: int = 0, fear: int = 0, debt: int = 0) -> "CompanionState":
        return replace(
            self,
            loyalty=_clamp(self.loyalty + loyalty),
            morale=_clamp(self.morale + morale),
            fear=_clamp(self.fear + fear),
            debt=_clamp(self.debt + debt),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "npc_id": self.npc_id,
            "role": self.role,
            "loyalty": self.loyalty,
            "morale": self.morale,
            "fear": self.fear,
            "debt": self.debt,
            "personal_goal": self.personal_goal,
            "in_party": self.in_party,
        }


@dataclass(frozen=True)
class PartyState:
    companions: Mapping[str, CompanionState]

    def active_companions(self) -> tuple[CompanionState, ...]:
        return tuple(sorted((companion for companion in self.companions.values() if companion.in_party), key=lambda item: item.npc_id))

    def with_companion(self, companion: CompanionState) -> "PartyState":
        updated = dict(self.companions)
        updated[companion.npc_id] = companion
        return PartyState(updated)


@dataclass(frozen=True)
class CompanionResolution:
    npc_id: str
    decision: CompanionDecision
    reason: str
    party: PartyState

    def as_dict(self) -> dict[str, object]:
        return {"npc_id": self.npc_id, "decision": self.decision, "reason": self.reason, "party_size": len(self.party.active_companions())}


def companion_can_join(companion: CompanionState, *, relationship_ok: bool, quest_ok: bool = True, conflict: bool = False) -> bool:
    return relationship_ok and quest_ok and not conflict and companion.loyalty >= 0 and companion.fear < 75


def join_companion(
    party: PartyState,
    companion: CompanionState,
    *,
    relationship_ok: bool,
    quest_ok: bool = True,
    conflict: bool = False,
) -> CompanionResolution:
    if not companion_can_join(companion, relationship_ok=relationship_ok, quest_ok=quest_ok, conflict=conflict):
        return CompanionResolution(companion.npc_id, "blocked", "eligibility_failed", party)
    updated = replace(companion, in_party=True)
    return CompanionResolution(companion.npc_id, "joined", "eligible", party.with_companion(updated))


def leave_companion(party: PartyState, npc_id: str, *, reason: str) -> CompanionResolution:
    companion = party.companions.get(npc_id)
    if companion is None:
        return CompanionResolution(npc_id, "blocked", "unknown_companion", party)
    updated = replace(companion, in_party=False)
    return CompanionResolution(npc_id, "left", reason, party.with_companion(updated))


def party_bonus(party: PartyState, check_kind: str) -> int:
    role_bonus = {
        "combat": {"fighter"},
        "healing": {"healer"},
        "travel": {"guide", "scout"},
        "social": {"face", "merchant"},
        "knowledge": {"scholar"},
        "locks": {"lockpick"},
    }
    roles = role_bonus.get(check_kind, set())
    return sum(2 for companion in party.active_companions() if companion.role in roles and companion.morale >= -25)


def companion_report_payload(party: PartyState) -> dict[str, object]:
    active = party.active_companions()
    return {"party_size": len(active), "companions": [companion.as_dict() for companion in active]}


def _clamp(value: int) -> int:
    return max(-100, min(100, int(value)))


def party_from_companions(companions: Sequence[CompanionState]) -> PartyState:
    return PartyState({companion.npc_id: companion for companion in companions})
