"""Deterministic quest journal and chronicle helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

QuestStatus = Literal["unknown", "rumored", "offered", "accepted", "advanced", "blocked", "completed", "failed", "expired"]
ChronicleKind = Literal["happened", "learned", "changed", "unresolved"]


@dataclass(frozen=True)
class QuestObjective:
    objective_id: str
    summary: str
    complete: bool = False


@dataclass(frozen=True)
class QuestState:
    quest_id: str
    title: str
    status: QuestStatus
    objectives: tuple[QuestObjective, ...] = ()
    known_clues: tuple[str, ...] = ()
    npc_ids: tuple[str, ...] = ()
    location_ids: tuple[str, ...] = ()
    reward: str = ""
    risk: str = ""

    def current_objective(self) -> QuestObjective | None:
        return next((objective for objective in self.objectives if not objective.complete), None)

    def with_status(self, status: QuestStatus) -> "QuestState":
        return replace(self, status=status)

    def complete_objective(self, objective_id: str) -> "QuestState":
        return replace(
            self,
            objectives=tuple(
                replace(objective, complete=True) if objective.objective_id == objective_id else objective
                for objective in self.objectives
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "quest_id": self.quest_id,
            "title": self.title,
            "status": self.status,
            "current_objective": self.current_objective().summary if self.current_objective() else None,
            "known_clues": list(self.known_clues),
            "npc_ids": list(self.npc_ids),
            "location_ids": list(self.location_ids),
            "reward": self.reward,
            "risk": self.risk,
        }


@dataclass(frozen=True)
class QuestTransition:
    quest_id: str
    before: QuestStatus
    after: QuestStatus
    source_event_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "quest_id": self.quest_id,
            "before": self.before,
            "after": self.after,
            "source_event_id": self.source_event_id,
        }


@dataclass(frozen=True)
class ChronicleEntry:
    turn: int
    kind: ChronicleKind
    summary: str
    facts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"turn": self.turn, "kind": self.kind, "summary": self.summary, "facts": list(self.facts)}


def transition_quest_status(
    quest: QuestState,
    status: QuestStatus,
    *,
    source_event_id: str,
) -> tuple[QuestState, QuestTransition]:
    updated = quest.with_status(status)
    return updated, QuestTransition(quest.quest_id, quest.status, status, source_event_id)


def rumor_to_quest(quest_id: str, title: str, *, clue: str, location_id: str | None = None) -> QuestState:
    locations = (location_id,) if location_id else ()
    return QuestState(quest_id, title, "rumored", known_clues=(clue,), location_ids=locations)


def grounded_suggested_actions(quests: Sequence[QuestState], known_location_ids: Sequence[str]) -> tuple[str, ...]:
    known_locations = set(known_location_ids)
    suggestions: list[str] = []
    for quest in quests:
        if quest.status in ("completed", "failed", "expired", "unknown"):
            continue
        objective = quest.current_objective()
        if objective:
            suggestions.append(f"Work on {quest.title}: {objective.summary}")
        for location_id in quest.location_ids:
            if location_id in known_locations:
                suggestions.append(f"Travel to {location_id} for {quest.title}")
                break
        if quest.npc_ids:
            suggestions.append(f"Ask {quest.npc_ids[0]} about {quest.title}")
    return tuple(suggestions[:5])


def chronicle_payload(entries: Sequence[ChronicleEntry], quests: Sequence[QuestState]) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = {"happened": [], "learned": [], "changed": [], "unresolved": []}
    for entry in entries:
        grouped[entry.kind].append(entry.as_dict())
    return {
        "what_happened": grouped["happened"],
        "what_i_learned": grouped["learned"],
        "what_changed": grouped["changed"],
        "unresolved": grouped["unresolved"],
        "quests": [quest.as_dict() for quest in quests],
        "suggested_actions": list(grounded_suggested_actions(quests, _known_locations(quests))),
    }


def _known_locations(quests: Sequence[QuestState]) -> tuple[str, ...]:
    locations: set[str] = set()
    for quest in quests:
        locations.update(quest.location_ids)
    return tuple(sorted(locations))
