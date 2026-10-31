"""What a typed line means, as the intent call reads it (evolution roadmap EV-9): the reading and the scene.

The model reads every typed line (``session/turn/intent.py``); no rule reads the player's words. A reading names the
family the pipeline runs and what in the scene it is aimed at, and carries what the rules need as typed slots: how
many, how long to wait or the hour to wait until, how to rest, what the hero asks about their standing, a
companion's order, a level's choice, the topics a line asks a person about, and the open quest step it addresses
(EV-3). Code checks every reading and every slot against the scene and the rules before anything is planned.

A card the player clicks carries the same reading, made by the game: it runs with no model call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Family = Literal[
    "look", "inspect", "move", "talk", "ask", "decline", "buy", "sell", "attack", "flee", "defend",
    "take", "drop", "give", "use_item", "equip", "unequip", "manipulate", "rest", "wait", "quest",
    "practice", "party", "status", "order", "clarify", "ability", "check", "grow", "explore",
]
EntityKind = Literal["person", "creature", "item", "place", "offer", "quest", "skill", "group", "ability"]

# Families that change the campaign's state when carried out.
STATEFUL_FAMILIES = frozenset(
    {"move", "buy", "attack", "take", "drop", "give", "use_item", "rest", "quest", "practice", "party"}
)
RestKind = Literal["while", "sleep", "camp"]
StatusTopic = Literal["health", "progress", "inventory", "quests", "skills"]
STATUS_TOPICS: tuple[str, ...] = ("health", "progress", "inventory", "quests", "skills")
MOST_AT_ONCE = 10  # goods bought, or things dropped, in one go


@dataclass(frozen=True)
class SceneEntity:
    entity_id: str
    kind: EntityKind
    names: tuple[str, ...]
    here: bool = False  # present in the scene (a person or creature here, an exit, an offer on sale here)
    topics: tuple[tuple[str, str], ...] = ()  # a person's: (topic id, what it is about) they may be asked of
    steps: tuple[tuple[str, str], ...] = ()  # a person's: (step address, what the step asks) a line may answer
    weaknesses: tuple[tuple[str, str], ...] = ()  # a creature's: (weakness, its names) a line may use (EV-2)


@dataclass(frozen=True)
class SceneView:
    entities: tuple[SceneEntity, ...] = ()
    focus_id: str = ""  # the person the player is in conversation with, whom "him" or "her" means

    def of(self, *kinds: str, here: bool | None = None) -> list[SceneEntity]:
        return [
            entity for entity in self.entities
            if entity.kind in kinds and (here is None or entity.here == here)
        ]

    def entity(self, entity_id: str) -> SceneEntity | None:
        return next((entity for entity in self.entities if entity.entity_id == entity_id), None)


class ReadingSlots(BaseModel):
    """What the rules need of a line besides its family and target, typed (EV-9). Unset is "the line did not say"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: int | None = Field(default=None, ge=1, le=99)
    everything: bool = False  # all of them ("drop all my bread")
    wait_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    until_hour: int | None = Field(default=None, ge=0, le=23)  # the hour of the day to wait until
    tomorrow: bool = False  # that hour tomorrow, whatever the hour now
    rest: RestKind | None = None
    status: tuple[StatusTopic, ...] = ()
    order: str = ""  # a companion's order, one of ``rules/player/requests.ORDERS``
    parting: bool = False  # a party reading that parts ways with the companion
    choice: str = ""  # a level's choice: "attribute:<name>", "ability:<id>" or "skills:<one>,<other>"
    topics: tuple[str, ...] = ()  # what a line asks a person about: ids of the topics they may be asked of
    step: str = ""  # the open quest step a line answers: "<quest id>|<step id>|<way>" (EV-3)
    weakness: str = ""  # the weakness of the foe an attack uses (EV-2), one the scene names for it


NO_SLOTS = ReadingSlots()


@dataclass(frozen=True)
class IntentCandidate:
    family: Family
    target_id: str | None = None
    target_kind: str | None = None
    confidence: float = 0.0
    reason: str = ""
    second_target_id: str | None = None  # the recipient of a give, the seller of a buy, a buyer of a sale
    clauses: tuple[str, ...] = field(default=())
    slots: ReadingSlots = NO_SLOTS
    asks: bool = False  # the line asks or supposes; it does not do (EV-9: "what would happen if I...")

    @property
    def stateful(self) -> bool:
        """Whether carrying it out would change state, as far as the reading tells: buying needs something on sale."""
        if self.family == "buy":
            return self.target_kind == "offer"
        return self.family in STATEFUL_FAMILIES


__all__ = ["MOST_AT_ONCE", "NO_SLOTS", "STATEFUL_FAMILIES", "STATUS_TOPICS", "EntityKind", "Family", "IntentCandidate",
           "ReadingSlots", "RestKind", "SceneEntity", "SceneView", "StatusTopic"]
