"""What a world says about how it plays: its economy, its people's routines and knowledge, its pressures (RQ-2.0).

These are optional sections of a world revision's canon. A world that has them is played as its
author wrote it; one that does not is played from what launch infers from its lore
(``published_world_setup``), and the world model records which ("authored" or "derived") so
launch readiness can say so.

- ``canon.economy.providers``: who sells what, at what price and stock, and what they buy back.
- ``canon.routines``: each named person's day (where they are, hour by hour) and goals.
- ``canon.knowledge``: what each person knows, and on what terms they share it.
- ``canon.pressures``: the forces the world's clock moves (a threat, a shortage, a feud).
- ``canon.bestiary[*]``: optional fighting numbers, behaviour and loot beside threat and weakness.

Older bundles carry none of these and import as before; the sections ride inside canon, so a
bundle that has them needs no new bundle version.

A world of the library is written in the world editor (RQ-4.1): its author's sections are a draft kept with the
world (``play_section_authoring``) that each publication writes into the new revision's canon
(``with_play_sections``). People, places, items, quests and creatures are the world's own as launch reads them
(``lore_sections.lore_rows``: the section where the world wrote one, else the entities of its kinds).
"""
from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .lore_sections import lore_rows

SECTIONS = ("economy", "routines", "knowledge", "pressures", "bestiary")
ServiceKind = Literal["lodging", "meal", "drink", "shop_goods", "repair", "paid_information"]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Price(_Section):
    gold: int = Field(default=0, ge=0)
    silver: int = Field(default=0, ge=0)
    copper: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _not_free(self) -> "Price":
        if not (self.gold or self.silver or self.copper):
            raise ValueError("price_must_not_be_zero")
        return self


class ShopOffer(_Section):
    offer_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    service: ServiceKind
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    price: Price
    item_id: str = ""
    stock: int | None = Field(default=None, ge=0)
    restock_per_day: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _goods_name_an_item(self) -> "ShopOffer":
        if self.service == "shop_goods" and not self.item_id:
            raise ValueError("shop_goods_offer_needs_item_id")
        return self


class BuyBack(_Section):
    item_types: tuple[str, ...] = ()
    price_fraction: float = Field(default=0.5, ge=0.0, le=1.0)


class ProviderEconomy(_Section):
    provider_id: str = Field(min_length=1)
    location_id: str = ""
    sells: tuple[ShopOffer, ...] = ()
    buys: BuyBack | None = None


class RoutineStep(_Section):
    from_hour: int = Field(ge=0, le=23)
    to_hour: int = Field(ge=1, le=24)
    location_id: str = Field(min_length=1)
    activity: str = Field(default="", max_length=160)

    @model_validator(mode="after")
    def _forward(self) -> "RoutineStep":
        if self.to_hour <= self.from_hour:
            raise ValueError("routine_step_must_end_after_it_starts")
        return self


class NpcGoal(_Section):
    goal_id: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=300)
    priority: int = Field(default=1, ge=1, le=5)
    topics: tuple[str, ...] = ()
    location_id: str = ""


class NpcRoutine(_Section):
    npc_id: str = Field(min_length=1)
    schedule: tuple[RoutineStep, ...] = ()
    goals: tuple[NpcGoal, ...] = ()


class KnowledgeFact(_Section):
    fact_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=600)
    shares: Literal["freely", "for_price", "when_trusted", "never"] = "freely"
    price: Price | None = None
    trust_needed: int = Field(default=0, ge=0, le=100)
    topics: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _priced(self) -> "KnowledgeFact":
        if self.shares == "for_price" and self.price is None:
            raise ValueError("fact_shared_for_price_needs_price")
        return self


class NpcKnowledge(_Section):
    npc_id: str = Field(min_length=1)
    facts: tuple[KnowledgeFact, ...] = ()


class PressureLever(_Section):
    # What pulls it (rules/pressures.py): each creature of a kind felled, or a quest completed.
    action: str = Field(min_length=1, max_length=80, pattern=r"^(defeat|quest):\S+$")
    effect: Literal["lower", "raise"]
    amount: float = Field(gt=0, le=100)


class WorldPressure(_Section):
    pressure_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=600)
    region_id: str = Field(min_length=1)
    # The region dimension it bears on (the causal runtime's region dimensions).
    dimension: Literal["political_stability", "trade_access", "resource_access", "population_index"] = "political_stability"
    severity: float = Field(default=40.0, ge=0, le=100)
    trend: Literal["escalating", "contained", "volatile", "stable"] = "escalating"
    escalation_threshold: float = Field(default=75.0, ge=0, le=100)
    resolution_threshold: float = Field(default=15.0, ge=0, le=100)
    levers: tuple[PressureLever, ...] = ()

    @model_validator(mode="after")
    def _thresholds(self) -> "WorldPressure":
        if self.resolution_threshold >= self.escalation_threshold:
            raise ValueError("pressure_resolution_threshold_must_be_below_escalation")
        return self


class CreatureStats(_Section):
    level: int = Field(ge=1, le=30)
    hp: int = Field(ge=1, le=1000)
    defense: int = Field(ge=1, le=40)
    damage_min: int = Field(ge=0, le=200)
    damage_max: int = Field(ge=1, le=200)
    accuracy_bonus: int = Field(default=0, ge=-5, le=20)
    xp_value: int = Field(default=25, ge=0, le=10_000)

    @model_validator(mode="after")
    def _range(self) -> "CreatureStats":
        if self.damage_max < self.damage_min:
            raise ValueError("creature_damage_max_below_min")
        return self


class LootDrop(_Section):
    item_id: str = Field(min_length=1)
    chance: float = Field(gt=0, le=1)
    quantity: int = Field(default=1, ge=1, le=99)


class BestiaryPlay(BaseModel):
    """The play fields of a bestiary row; its lore fields (name, threat, traits, weakness) stay free-form."""

    model_config = ConfigDict(extra="allow", frozen=True)

    id: str = Field(min_length=1)
    stats: CreatureStats | None = None
    behaviour: Literal["fights", "flees_when_hurt", "calls_allies", "guards", "ambushes"] = "fights"
    loot: tuple[LootDrop, ...] = ()


class WorldPlaySections(_Section):
    providers: tuple[ProviderEconomy, ...] = ()
    routines: tuple[NpcRoutine, ...] = ()
    knowledge: tuple[NpcKnowledge, ...] = ()
    pressures: tuple[WorldPressure, ...] = ()
    bestiary: tuple[BestiaryPlay, ...] = ()
    authored: tuple[str, ...] = ()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _error_code(error: ValidationError) -> str:
    first = error.errors()[0] if error.errors() else {}
    location = ".".join(str(part) for part in first.get("loc") or ())
    message = str(first.get("msg") or "invalid").removeprefix("Value error, ")
    return f"{location}:{message}" if location else message


_BESTIARY_PLAY = ("stats", "behaviour", "loot")


def _plays(row: Mapping[str, Any]) -> bool:
    """A bestiary row that says how its creature fights (numbers, behaviour or loot), beside its lore."""
    return any(row.get(key) for key in _BESTIARY_PLAY)


def parse_play_sections(canon: Mapping[str, Any]) -> tuple[WorldPlaySections, tuple[str, ...]]:
    """The world's play sections and what is wrong with them (``play_section_invalid:...``); absent ones are empty."""

    canon = _mapping(canon)
    findings: list[str] = []
    parsed: dict[str, Any] = {}
    authored: list[str] = []

    def parse(section: str, model: type[BaseModel], rows: list[Any]) -> tuple[Any, ...]:
        result = []
        for index, row in enumerate(rows):
            try:
                result.append(model.model_validate(row))
            except ValidationError as error:
                findings.append(f"play_section_invalid:{section}[{index}]:{_error_code(error)}")
        return tuple(result)

    providers = _rows(_mapping(canon.get("economy")).get("providers"))
    if providers:
        parsed["providers"] = parse("economy.providers", ProviderEconomy, providers)
        authored.append("economy")
    for section, model in (("routines", NpcRoutine), ("knowledge", NpcKnowledge), ("pressures", WorldPressure)):
        rows = _rows(canon.get(section))
        if rows:
            parsed[section] = parse(section, model, rows)
            authored.append(section)
    bestiary = [row for row in _rows(canon.get("bestiary")) if isinstance(row, Mapping)]
    parsed["bestiary"] = parse("bestiary", BestiaryPlay, bestiary)
    if any(_plays(row) for row in bestiary):
        authored.append("bestiary")
    return WorldPlaySections(**parsed, authored=tuple(authored)), tuple(findings)


def _ids(canon: Mapping[str, Any], section: str) -> set[str]:
    return {str(row.get("id") or "") for row in lore_rows(canon, section)} - {""}


def play_section_findings(
    canon: Mapping[str, Any],
    *,
    location_ids: set[str],
    region_ids: set[str],
) -> tuple[str, ...]:
    """Release findings: invalid sections, and authored references to people, places or items the world lacks."""

    sections, findings = parse_play_sections(canon)
    canon = _mapping(canon)
    npc_ids = _ids(canon, "characters")
    item_ids = _ids(canon, "items")
    unknown: list[str] = []

    def place(section: str, location_id: str) -> None:
        if location_id and location_id not in location_ids:
            unknown.append(f"play_section_unknown_place:{section}:{location_id}")

    for provider in sections.providers:
        if provider.provider_id not in npc_ids:
            unknown.append(f"play_section_unknown_person:economy:{provider.provider_id}")
        place("economy", provider.location_id)
        for offer in provider.sells:
            if offer.item_id and offer.item_id not in item_ids:
                unknown.append(f"play_section_unknown_item:economy:{offer.item_id}")
    for routine in sections.routines:
        if routine.npc_id not in npc_ids:
            unknown.append(f"play_section_unknown_person:routines:{routine.npc_id}")
        for step in routine.schedule:
            place("routines", step.location_id)
        for goal in routine.goals:
            place("routines", goal.location_id)
    for knowledge in sections.knowledge:
        if knowledge.npc_id not in npc_ids:
            unknown.append(f"play_section_unknown_person:knowledge:{knowledge.npc_id}")
    creature_ids = _ids(canon, "bestiary")
    quest_ids = _ids(canon, "quests")
    for pressure in sections.pressures:
        if pressure.region_id not in region_ids and pressure.region_id not in location_ids:
            unknown.append(f"play_section_unknown_place:pressures:{pressure.region_id}")
        for lever in pressure.levers:
            kind, _, subject = lever.action.partition(":")
            if subject not in (creature_ids if kind == "defeat" else quest_ids):
                unknown.append(f"play_section_unknown_lever:pressures:{lever.action}")
    for creature in sections.bestiary:
        for drop in creature.loot:
            if drop.item_id not in item_ids:
                unknown.append(f"play_section_unknown_item:bestiary:{drop.item_id}")
    return tuple(sorted(set((*findings, *unknown))))


def authorship(sections: WorldPlaySections) -> dict[str, str]:
    """Each section's source for launch readiness: ``authored`` by the world, or ``derived`` from its lore."""
    return {section: ("authored" if section in sections.authored else "derived") for section in SECTIONS}


class EconomyDraft(_Section):
    providers: tuple[ProviderEconomy, ...] = ()


class CreaturePlay(_Section):
    """How one of the world's creatures fights; a field left out is taken from its lore."""

    id: str = Field(min_length=1)
    stats: CreatureStats | None = None
    behaviour: Literal["fights", "flees_when_hurt", "calls_allies", "guards", "ambushes"] | None = None
    loot: tuple[LootDrop, ...] = ()


class PlaySectionsDraft(_Section):
    """What a world's author wrote of how it plays, as the world editor keeps it. Once saved it is the whole of
    it: a section left empty is played from the world's lore."""

    economy: EconomyDraft = EconomyDraft()
    routines: tuple[NpcRoutine, ...] = ()
    knowledge: tuple[NpcKnowledge, ...] = ()
    pressures: tuple[WorldPressure, ...] = ()
    bestiary: tuple[CreaturePlay, ...] = ()


def draft_findings(document: Any) -> tuple[PlaySectionsDraft | None, tuple[str, ...]]:
    """The draft, or what is wrong with it (``play_section_invalid:<where>:<why>``, one per error)."""
    try:
        return PlaySectionsDraft.model_validate(document), ()
    except ValidationError as error:
        findings = []
        for detail in error.errors():
            location = ".".join(str(part) for part in detail.get("loc") or ())
            message = str(detail.get("msg") or "invalid").removeprefix("Value error, ")
            findings.append(f"play_section_invalid:{location}:{message}")
        return None, tuple(findings)


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)


def play_sections_document(canon: Mapping[str, Any]) -> dict[str, Any]:
    """The sections a revision's canon carries, as the editor's draft (the rows that are valid)."""
    sections, _findings = parse_play_sections(canon)
    plays = []
    for row in _rows(_mapping(canon).get("bestiary")):
        if isinstance(row, Mapping) and _plays(row):
            candidate = {key: row[key] for key in ("id", *_BESTIARY_PLAY) if row.get(key)}
            try:
                plays.append(_dump(CreaturePlay.model_validate(candidate)))
            except ValidationError:
                continue
    return {
        "economy": {"providers": [_dump(row) for row in sections.providers]},
        "routines": [_dump(row) for row in sections.routines],
        "knowledge": [_dump(row) for row in sections.knowledge],
        "pressures": [_dump(row) for row in sections.pressures],
        "bestiary": plays,
    }


def with_play_sections(canon: Mapping[str, Any], draft: PlaySectionsDraft) -> dict[str, Any]:
    """``canon`` with the author's sections in place of its own: a section the draft leaves empty is removed (played
    from the lore), and each creature keeps its lore with the draft's numbers, behaviour and loot beside it."""
    canon = dict(canon)
    economy = {key: value for key, value in _mapping(canon.get("economy")).items() if key != "providers"}
    if draft.economy.providers:
        economy["providers"] = [_dump(row) for row in draft.economy.providers]
    if economy:
        canon["economy"] = economy
    else:
        canon.pop("economy", None)
    for section in ("routines", "knowledge", "pressures"):
        rows = getattr(draft, section)
        if rows:
            canon[section] = [_dump(row) for row in rows]
        else:
            canon.pop(section, None)
    plays = {row.id: row for row in draft.bestiary}
    if plays or "bestiary" in canon:
        creatures = []
        for row in lore_rows(canon, "bestiary"):
            lore = {key: value for key, value in row.items() if key not in _BESTIARY_PLAY}
            play = plays.pop(str(row.get("id") or ""), None)
            creatures.append({**lore, **({key: value for key, value in _dump(play).items() if key != "id"}
                                         if play is not None else {})})
        canon["bestiary"] = creatures  # a creature the world lacks is left out (unknown_creatures names it)
    return canon


def unknown_creatures(canon: Mapping[str, Any], draft: PlaySectionsDraft) -> tuple[str, ...]:
    """The draft's creatures ``canon`` does not have (``play_section_unknown_creature:bestiary:<id>``)."""
    known = _ids(canon, "bestiary")
    return tuple(sorted(f"play_section_unknown_creature:bestiary:{row.id}" for row in draft.bestiary
                        if row.id not in known))


__all__ = [
    "SECTIONS",
    "BestiaryPlay",
    "CreaturePlay",
    "CreatureStats",
    "EconomyDraft",
    "KnowledgeFact",
    "NpcGoal",
    "NpcKnowledge",
    "NpcRoutine",
    "PlaySectionsDraft",
    "ProviderEconomy",
    "RoutineStep",
    "ShopOffer",
    "WorldPlaySections",
    "WorldPressure",
    "authorship",
    "draft_findings",
    "parse_play_sections",
    "play_section_findings",
    "play_sections_document",
    "unknown_creatures",
    "with_play_sections",
]
