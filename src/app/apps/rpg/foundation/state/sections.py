"""The campaign document's sections, typed (RQ-1.1, roadmap §4.2).

A v6 campaign document keeps the v5 layout: the engine's 5,000 string-key readers move to typed state one
mechanic at a time (RQ-2), and a physical move before then would break each of them at once. What v6 adds is
the section map: every section names the document paths it owns (``SECTION_PATHS``), and its model reads
those paths. A key a section owns but does not type yet is kept in its ``extensions``, so a section is
complete even while it is partly typed, and the reducer (RQ-1.2) writes through these same paths.

``npcs`` holds runtime state only (where people are, who is present, how they regard the hero); the people
themselves, their routines, goals and knowledge are authored in the world revision.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

Path = tuple[str, ...]


def read_path(document: Mapping[str, Any], path: Path) -> Any:
    """The value at ``path`` in the document, or None."""
    value: Any = document
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split(mapping: Mapping[str, Any], typed: set[str]) -> dict[str, Any]:
    return {str(key): value for key, value in mapping.items() if key not in typed}


class Typed(BaseModel):
    """A typed record whose untyped keys are kept, not dropped."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    extensions: dict[str, Any] = Field(default_factory=dict)


class Purse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gold: int = 0
    silver: int = 0
    copper: int = 0

    @property
    def total_copper(self) -> int:
        return self.gold * 100 + self.silver * 10 + self.copper

    @classmethod
    def read(cls, value: Any) -> Purse | None:
        if not isinstance(value, Mapping):
            return None
        return cls(gold=_int(value.get("gold")), silver=_int(value.get("silver")), copper=_int(value.get("copper")))


class InventoryStack(Typed):
    item_id: str = ""
    name: str = ""
    quantity: int = 1
    category: str = ""

    @classmethod
    def read(cls, item: Mapping[str, Any]) -> InventoryStack:
        quantity = item.get("quantity", item.get("qty", 1))
        return cls(
            item_id=str(item.get("item_id") or item.get("id") or ""),
            name=str(item.get("name") or ""),
            quantity=_int(quantity, 1),
            category=str(item.get("category") or item.get("type") or ""),
            extensions=_split(item, {"item_id", "id", "name", "quantity", "qty", "category", "type"}),
        )


class SkillProgress(Typed):
    level: int = 0
    xp: int = 0
    xp_to_next: int = 25


class Section(Typed):
    """A section of the campaign document: the paths it owns, and their typed reading."""

    PATHS: ClassVar[tuple[Path, ...]] = ()

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> Section:  # pragma: no cover - each section reads
        raise NotImplementedError


PLAYER_STATE: Path = ("simulation_state", "player_state")


class PlayerSection(Section):
    """The hero: who they are, their level and experience, health and abilities' scores, skills."""

    PATHS = (PLAYER_STATE, ("state", "ability_state"))  # the hero's abilities: unlocked, ranks, cooldowns
    _TYPED: ClassVar[set[str]] = {"name", "level", "xp", "xp_to_next", "resources", "stats", "skills",
                                  # owned by other sections
                                  "inventory", "inventory_state", "currency", "party_state", "location_id",
                                  "current_location_id"}

    name: str = ""
    level: int = 1
    xp: int = 0
    xp_to_next: int = 100
    hp: int | None = None
    max_hp: int | None = None
    resources: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    skills: dict[str, SkillProgress] = Field(default_factory=dict)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> PlayerSection:
        player = _mapping(read_path(document, PLAYER_STATE))
        sheet = _mapping(read_path(document, ("state", "player")))
        resources = _mapping(player.get("resources") or sheet.get("resources"))
        hp = _mapping(resources.get("hp"))
        skills: dict[str, SkillProgress] = {}
        for skill_id, raw in _mapping(player.get("skills")).items():
            if isinstance(raw, Mapping):
                skills[str(skill_id)] = SkillProgress(
                    level=_int(raw.get("level")), xp=_int(raw.get("xp")), xp_to_next=_int(raw.get("xp_to_next"), 25),
                    extensions=_split(raw, {"level", "xp", "xp_to_next"}),
                )
        return cls(
            name=str(player.get("name") or sheet.get("name") or ""),
            level=_int(player.get("level") or sheet.get("level"), 1),
            xp=_int(player.get("xp")),
            xp_to_next=_int(player.get("xp_to_next"), 100),
            hp=_int(hp["current"]) if "current" in hp else None,
            max_hp=_int(hp["max"]) if "max" in hp else None,
            resources=resources,
            stats=_mapping(player.get("stats") or sheet.get("stats")),
            skills=skills,
            extensions=_split(player, cls._TYPED),
        )


class InventorySection(Section):
    """One store: the pack's stacks, the purse, what is equipped, and what lies on the ground where.

    The simulation's store (``player_state.inventory_state``) is the store; the sheet's list
    (``state.player.inventory``) is its projection for the play screen, made to agree on upgrade (v6).
    """

    PATHS = (PLAYER_STATE + ("inventory_state",), PLAYER_STATE + ("currency",), ("simulation_state", "world_items"))

    items: list[InventoryStack] = Field(default_factory=list)
    purse: Purse | None = None
    equipment: dict[str, Any] = Field(default_factory=dict)
    ground: dict[str, list[InventoryStack]] = Field(default_factory=dict)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> InventorySection:
        store = _mapping(read_path(document, PLAYER_STATE + ("inventory_state",)))
        sheet = _mapping(read_path(document, ("state", "player")))
        items = store.get("items") if isinstance(store.get("items"), list) else sheet.get("inventory")
        purse = (Purse.read(read_path(document, PLAYER_STATE + ("currency",)))
                 or Purse.read(store.get("currency")) or Purse.read(sheet.get("currency")))
        by_location = _mapping(_mapping(read_path(document, ("simulation_state", "world_items"))).get("by_location"))
        return cls(
            items=[InventoryStack.read(item) for item in items or () if isinstance(item, Mapping)],
            purse=purse,
            equipment=_mapping(store.get("equipment")),
            ground={str(place): [InventoryStack.read(item) for item in stacks if isinstance(item, Mapping)]
                    for place, stacks in by_location.items() if isinstance(stacks, list)},
            extensions=_split(store, {"items", "currency", "equipment"}),
        )


class LocationSection(Section):
    """Where the hero is, and the places they have been."""

    PATHS = (PLAYER_STATE + ("location_id",), PLAYER_STATE + ("current_location_id",), ("simulation_state", "travel_state"),
             ("simulation_state", "location_state"), ("runtime_state", "current_scene"),
             # the older readers' copies of where the hero is, kept in step by the reducer until they go (RQ-2.10)
             *(("simulation_state", key) for key in ("location_id", "location_name", "current_location",
                                                     "current_location_id", "current_location_name",
                                                     "previous_location", "visited_locations")))

    location_id: str = ""
    location_name: str = ""
    visited_location_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> LocationSection:
        simulation = _mapping(document.get("simulation_state"))
        location_id = str(read_path(document, PLAYER_STATE + ("location_id",)) or simulation.get("location_id")
                          or read_path(document, ("state", "current_location_id")) or "")
        visited = simulation.get("visited_locations") or read_path(document, ("simulation_state", "travel_state",
                                                                               "visited_location_ids")) or ()
        return cls(
            location_id=location_id,
            location_name=str(read_path(document, ("state", "current_location_name")) or ""),
            visited_location_ids=[str(place) for place in visited if place],
            extensions={"travel_state": simulation.get("travel_state"), "location_state": simulation.get("location_state")},
        )


class TimeSection(Section):
    """The turn counter, the simulation tick, and the in-game calendar."""

    PATHS = (("simulation_state", "tick"), ("manifest", "turn_count"), ("manifest", "current_turn"),
             ("runtime_state", "campaign_calendar"))

    tick: int = 0
    turn_count: int = 0
    calendar: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> TimeSection:
        calendar = _mapping(read_path(document, ("runtime_state", "campaign_calendar")))
        return cls(
            tick=_int(read_path(document, ("simulation_state", "tick"))),
            turn_count=_int(read_path(document, ("manifest", "turn_count"))),
            calendar=_mapping(calendar.get("current")),
            extensions=_split(calendar, {"current"}),
        )


class Companion(Typed):
    npc_id: str
    name: str = ""
    hp: int = 100
    max_hp: int = 100
    role: str = ""
    status: str = "active"


class PartySection(Section):
    PATHS = (PLAYER_STATE + ("party_state",),)

    companions: list[Companion] = Field(default_factory=list)
    max_size: int = 3

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> PartySection:
        party = _mapping(read_path(document, PLAYER_STATE + ("party_state",)))
        companions = [
            Companion(npc_id=str(raw.get("npc_id")), name=str(raw.get("name") or ""), hp=_int(raw.get("hp"), 100),
                      max_hp=_int(raw.get("max_hp"), 100), role=str(raw.get("role") or ""),
                      status=str(raw.get("status") or "active"),
                      extensions=_split(raw, {"npc_id", "name", "hp", "max_hp", "role", "status"}))
            for raw in party.get("companions") or () if isinstance(raw, Mapping) and raw.get("npc_id")
        ]
        return cls(companions=companions, max_size=_int(party.get("max_size"), 3),
                   extensions=_split(party, {"companions", "max_size"}))


class Combatant(Typed):
    hp: int = 0
    max_hp: int = 0
    team: str = ""


class CombatSection(Section):
    PATHS = (("simulation_state", "combat_state"),)

    active: bool = False
    combat_id: str = ""
    round: int = 0
    current_actor_id: str = ""
    participants: dict[str, Combatant] = Field(default_factory=dict)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> CombatSection:
        combat = _mapping(read_path(document, ("simulation_state", "combat_state")))
        participants = {
            str(actor): Combatant(
                hp=_int(_mapping(raw.get("resources")).get("hp", raw.get("hp"))), max_hp=_int(raw.get("max_hp")),
                team=str(raw.get("combat_team") or raw.get("team") or raw.get("side") or ""),
                extensions=_split(raw, {"hp", "max_hp", "combat_team", "team", "side"}))
            for actor, raw in _mapping(combat.get("participants")).items() if isinstance(raw, Mapping)
        }
        return cls(active=bool(combat.get("active")), combat_id=str(combat.get("combat_id") or ""),
                   round=_int(combat.get("round")), current_actor_id=str(combat.get("current_actor_id") or ""),
                   participants=participants,
                   extensions=_split(combat, {"active", "combat_id", "round", "current_actor_id", "participants"}))


class Quest(Typed):
    quest_id: str
    title: str = ""
    status: str = ""
    visited_locations: list[str] = Field(default_factory=list)


class QuestsSection(Section):
    """Quest progress. The play screen's ``state.quests`` is its projection."""

    PATHS = (("simulation_state", "quest_state"),)

    quests: list[Quest] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> QuestsSection:
        quest_state = _mapping(read_path(document, ("simulation_state", "quest_state")))
        rows = quest_state.get("quests") if isinstance(quest_state.get("quests"), list) else (
            read_path(document, ("state", "quests")) or ())
        quests = [
            Quest(quest_id=str(raw.get("quest_id") or raw.get("id") or ""), title=str(raw.get("title") or ""),
                  status=str(raw.get("status") or ""),
                  visited_locations=[str(place) for place in raw.get("visited_locations") or ()],
                  extensions=_split(raw, {"quest_id", "id", "title", "status", "visited_locations"}))
            for raw in rows if isinstance(raw, Mapping)
        ]
        return cls(quests=quests, extensions=_split(quest_state, {"quests"}))


class SurvivalSection(Section):
    PATHS = (("simulation_state", "survival"),)

    enabled: bool = False
    hunger: int = 0
    thirst: int = 0
    fatigue: int = 0

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> SurvivalSection:
        survival = _mapping(read_path(document, ("simulation_state", "survival")))
        return cls(enabled=bool(survival.get("enabled")), hunger=_int(survival.get("hunger")),
                   thirst=_int(survival.get("thirst")), fatigue=_int(survival.get("fatigue")),
                   extensions=_split(survival, {"enabled", "hunger", "thirst", "fatigue"}))


class NpcRuntime(Typed):
    name: str = ""
    role: str = ""
    location_id: str = ""


_NPC_RUNTIME_KEYS = ("npc_reputation_state", "npc_knowledge_state", "npc_dialogue_recall_state",
                     "npc_emotion_state", "npc_schedule_state", "npc_goal_state", "npc_evolution_state",
                     "npc_minds", "npc_decisions", "npc_history_state", "relationship_state", "social_state")


class NpcsSection(Section):
    """Runtime state of the world's people: where each is, who is present, cursors and regard."""

    PATHS = (("simulation_state", "npc_index"), ("simulation_state", "present_npc_state"),
             ("runtime_state", "current_scene", "present_npc_ids"), ("simulation_state", "present_npcs"),
             ("simulation_state", "dialogue"), ("runtime_state", "dialogue_focus"),
             *(("simulation_state", key) for key in _NPC_RUNTIME_KEYS))

    index: dict[str, NpcRuntime] = Field(default_factory=dict)
    present_npc_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> NpcsSection:
        simulation = _mapping(document.get("simulation_state"))
        index = {
            str(npc_id): NpcRuntime(name=str(raw.get("name") or ""), role=str(raw.get("role") or ""),
                                    location_id=str(raw.get("location_id") or ""),
                                    extensions=_split(raw, {"name", "role", "location_id"}))
            for npc_id, raw in _mapping(simulation.get("npc_index")).items() if isinstance(raw, Mapping)
        }
        present = read_path(document, ("runtime_state", "current_scene", "present_npc_ids"))
        if not isinstance(present, list):
            present = _mapping(simulation.get("present_npc_state")).get("present_npc_ids") or []
        return cls(index=index, present_npc_ids=[str(npc) for npc in present if npc],
                   extensions={key: simulation[key] for key in ("present_npc_state", *_NPC_RUNTIME_KEYS)
                               if key in simulation})


_WORLD_KEYS = ("world_model", "causal_world_runtime", "causal_runtime_projection", "faction_pressure", "factions",
               "events", "world_events", "world_event_state", "active_rumors", "incidents", "consequences",
               "environment", "campaign_mechanics")


class WorldSection(Section):
    """The world as the campaign runs it: its model (places, people, routes, offers), pressures, events."""

    PATHS = tuple(("simulation_state", key) for key in _WORLD_KEYS) + (("state", "world_binding"),)

    binding_kind: str = "starter"
    world_id: str = ""

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> WorldSection:
        simulation = _mapping(document.get("simulation_state"))
        binding = _mapping(read_path(document, ("state", "world_binding")))
        world_id = str(binding.get("world_id") or read_path(document, ("manifest", "world_id")) or "")
        kind = str(binding.get("kind") or ("published" if world_id else "starter"))
        return cls(binding_kind=kind, world_id=world_id,
                   extensions={key: simulation[key] for key in _WORLD_KEYS if key in simulation})


class EconomySection(Section):
    PATHS = (("simulation_state", "merchant_state"), ("simulation_state", "economy_state"),
             ("simulation_state", "trade"), ("simulation_state", "active_services"))

    offers: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> EconomySection:
        simulation = _mapping(document.get("simulation_state"))
        return cls(offers=_mapping(_mapping(simulation.get("world_model")).get("offers")),
                   extensions={key: simulation[key] for key in ("merchant_state", "economy_state") if key in simulation})


class NarrativeSection(Section):
    """Journal pointers and recent beats. Narration text moves to the narration tables (RQ-1.4)."""

    PATHS = (("simulation_state", "journal_state"), ("runtime_state", "player_journal"),
             ("runtime_state", "narration_artifacts"), ("runtime_state", "recent_scene_beats"))

    journal_entries: int = 0

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> NarrativeSection:
        runtime = _mapping(document.get("runtime_state"))
        journal = runtime.get("player_journal")
        entries = journal.get("entries") if isinstance(journal, Mapping) else journal
        return cls(journal_entries=len(entries) if isinstance(entries, list) else 0,
                   extensions={key: runtime[key] for key in ("player_journal", "narration_artifacts",
                                                              "recent_scene_beats") if key in runtime})


class MetaSection(Section):
    PATHS = (("manifest",), ("simulation_state", "rng_seed"), ("simulation_state", "campaign_end"))

    campaign_id: str = ""
    document_version: int = 1
    seed: int | None = None

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> MetaSection:
        manifest = _mapping(document.get("manifest"))
        seed = read_path(document, ("simulation_state", "rng_seed"))
        return cls(campaign_id=str(manifest.get("session_id") or manifest.get("id") or ""),
                   document_version=_int(manifest.get("schema_version"), 1),
                   seed=seed if isinstance(seed, int) and not isinstance(seed, bool) else None,
                   extensions=_split(manifest, {"session_id", "id", "schema_version"}))


SECTIONS: dict[str, type[Section]] = {
    "player": PlayerSection,
    "inventory": InventorySection,
    "location": LocationSection,
    "time": TimeSection,
    "party": PartySection,
    "combat": CombatSection,
    "quests": QuestsSection,
    "survival": SurvivalSection,
    "npcs": NpcsSection,
    "world": WorldSection,
    "economy": EconomySection,
    "narrative": NarrativeSection,
    "meta": MetaSection,
}
SECTION_PATHS: dict[str, tuple[Path, ...]] = {name: section.PATHS for name, section in SECTIONS.items()}
