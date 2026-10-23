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
"""
from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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
    action: str = Field(min_length=1, max_length=80)
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
    if any(isinstance(row, Mapping) and (row.get("stats") or row.get("loot")) for row in bestiary):
        authored.append("bestiary")
    return WorldPlaySections(**parsed, authored=tuple(authored)), tuple(findings)


def play_section_findings(
    canon: Mapping[str, Any],
    *,
    location_ids: set[str],
    region_ids: set[str],
) -> tuple[str, ...]:
    """Release findings: invalid sections, and authored references to people, places or items the world lacks."""

    sections, findings = parse_play_sections(canon)
    canon = _mapping(canon)
    npc_ids = {str(_mapping(row).get("id") or "") for row in _rows(canon.get("characters"))} - {""}
    item_ids = {str(_mapping(row).get("id") or "") for row in _rows(canon.get("items"))} - {""}
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
    for pressure in sections.pressures:
        if pressure.region_id not in region_ids and pressure.region_id not in location_ids:
            unknown.append(f"play_section_unknown_place:pressures:{pressure.region_id}")
    for creature in sections.bestiary:
        for drop in creature.loot:
            if drop.item_id not in item_ids:
                unknown.append(f"play_section_unknown_item:bestiary:{drop.item_id}")
    return tuple(sorted(set((*findings, *unknown))))


def authorship(sections: WorldPlaySections) -> dict[str, str]:
    """Each section's source for launch readiness: ``authored`` by the world, or ``derived`` from its lore."""
    return {section: ("authored" if section in sections.authored else "derived") for section in SECTIONS}


__all__ = [
    "SECTIONS",
    "BestiaryPlay",
    "CreatureStats",
    "KnowledgeFact",
    "NpcGoal",
    "NpcKnowledge",
    "NpcRoutine",
    "ProviderEconomy",
    "RoutineStep",
    "ShopOffer",
    "WorldPlaySections",
    "WorldPressure",
    "authorship",
    "parse_play_sections",
    "play_section_findings",
]
