"""World Forge's first draft of how a world plays, from its lore (RQ-4.1).

The world editor offers it to an author who has written no sections yet, or wants a section filled in: each section
is what launch would infer from the world's words (``published_world_setup``, ``published_pressures``), written out
so the author can see it, correct it and keep it. A section the world already wrote is returned as written. Pure and
deterministic: no model is asked, so the same lore gives the same draft.

- economy: each person whose role serves the public sells what launch would have them sell, at its prices; only
  goods that are the world's own items.
- routines: where each person is found (their place, all day) and their goals as the lore states them.
- knowledge: what each person says openly (their public truth) and what they keep until trusted (their secrets).
- pressures: the world's own pressures (its ``pressure`` entities, pulled by the quests that name them), then the
  danger its creatures put on each region's roads.
- bestiary: each creature's numbers by its threat and its behaviour as its lore tells.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Mapping

from pydantic import ValidationError

from .lore_sections import lore_location_rows, lore_rows
from .published_pressures import derived_pressures
from .published_world_setup import derived_behaviour, session_world_model, threat_stats
from .world_play_sections import (
    CreaturePlay,
    KnowledgeFact,
    NpcGoal,
    NpcKnowledge,
    NpcRoutine,
    PlaySectionsDraft,
    ProviderEconomy,
    RoutineStep,
    ShopOffer,
    WorldPressure,
    parse_play_sections,
    play_sections_document,
)

# A pressure's words name the region dimension it wears down; anything else unsettles who governs.
_DIMENSIONS = (
    (("trade", "market", "merchant", "smuggl", "caravan", "price", "shortage", "supply"), "trade_access"),
    (("food", "water", "harvest", "famine", "power", "fuel", "resource", "mine"), "resource_access"),
    (("plague", "sickness", "disease", "refugee", "population", "exodus", "death"), "population_index"),
)
_TRUSTED = 50  # the trust a secret waits for
_QUEST_PULL = 15.0  # how far finishing a quest that names a pressure eases it


def _text(value: Any) -> str:
    return str(value or "").strip()


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [_text(item) for item in value or () if _text(item)] if isinstance(value, (list, tuple)) else []


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "offer"


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _entities(canon: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    entities = canon.get("entities")
    rows = entities.values() if isinstance(entities, Mapping) else entities or ()
    return {_text(row.get("id")): dict(row) for row in rows if isinstance(row, Mapping) and _text(row.get("id"))}


def _economy(canon: Mapping[str, Any], model: Mapping[str, Any]) -> list[ProviderEconomy]:
    items = {_text(row.get("id")) for row in lore_rows(canon, "items")} - {""}
    providers = []
    for provider_id, provider in sorted(model["providers"].items()):
        sells: list[ShopOffer] = []
        keys: set[str] = set()
        for offer in model["offers"].get(provider_id, ()):
            added = [row for row in offer.get("effects", {}).get("items_added") or () if isinstance(row, Mapping)]
            item_id = _text(added[0].get("item_id")) if added else ""
            if offer["service_kind"] == "shop_goods" and item_id not in items:
                continue  # launch's stand-in goods (a healing potion the world never names) are not the world's
            key = _slug(_text(offer["offer_id"]).removeprefix(f"{provider_id}:"))
            while key in keys:
                key += "-2"
            keys.add(key)
            try:
                sells.append(ShopOffer(offer_key=key, service=offer["service_kind"], name=_short(offer["label"], 120),
                                       description=_short(_text(offer.get("description")), 500), price=offer["price"],
                                       item_id=item_id, stock=offer.get("stock")))
            except ValidationError:
                continue
        if sells:
            providers.append(ProviderEconomy(provider_id=provider_id, location_id=provider["location_id"],
                                             sells=tuple(sells)))
    return providers


def _routines(model: Mapping[str, Any]) -> list[NpcRoutine]:
    routines = []
    for npc_id, npc in sorted(model["npcs"].items()):
        schedule = (
            (RoutineStep(from_hour=0, to_hour=24, location_id=npc["location_id"],
                         activity=_short(_text(npc.get("role")), 160)),)
            if npc.get("location_id") else ()
        )
        goals = tuple(
            NpcGoal(goal_id=f"{_slug(npc_id.rsplit(':', 1)[-1])}-goal-{index + 1}", summary=_short(goal, 300),
                    priority=max(1, 4 - index))
            for index, goal in enumerate(_texts(npc.get("goals")))
        )
        if schedule or goals:
            routines.append(NpcRoutine(npc_id=npc_id, schedule=schedule, goals=goals))
    return routines


def _knowledge(canon: Mapping[str, Any]) -> list[NpcKnowledge]:
    entities = _entities(canon)
    knowledge = []
    for row in lore_rows(canon, "characters"):
        npc_id = _text(row.get("id"))
        if not npc_id:
            continue
        lore = {**entities.get(npc_id, {}), **row}
        stem = _slug(npc_id.rsplit(":", 1)[-1])
        facts = [
            KnowledgeFact(fact_id=f"{stem}-told-{index + 1}", text=_short(text, 600), shares="freely")
            for index, text in enumerate(_texts(lore.get("public_truth")) + _texts(lore.get("rumors")))
        ]
        facts += [
            KnowledgeFact(fact_id=f"{stem}-kept-{index + 1}", text=_short(text, 600), shares="when_trusted",
                          trust_needed=_TRUSTED)
            for index, text in enumerate(_texts(lore.get("secrets")) or _texts(lore.get("hidden_truth")))
        ]
        if facts:
            knowledge.append(NpcKnowledge(npc_id=npc_id, facts=tuple(facts)))
    return knowledge


def _dimension(text: str) -> str:
    text = text.casefold()
    return next((dimension for words, dimension in _DIMENSIONS if any(word in text for word in words)),
                "political_stability")


def _pressures(canon: Mapping[str, Any], places: Mapping[str, Mapping[str, Any]]) -> list[WorldPressure]:
    entities = _entities(canon)
    regions = [_text(row.get("id")) for row in lore_rows(canon, "regions") if _text(row.get("id"))]
    quests = [dict(row) for row in canon.get("quests") or () if isinstance(row, Mapping)] or [
        row for row in entities.values() if _text(row.get("kind")).casefold() == "quest"]
    pressures = []
    for entity in entities.values():
        if _text(entity.get("kind")).casefold() != "pressure":
            continue
        pressure_id = _text(entity.get("id"))
        place = next((places[place_id] for place_id in _texts(entity.get("place_ids")) if place_id in places), {})
        region_id = _text(entity.get("region_id")) or _text(place.get("region_id")) or _text(place.get("id"))
        region_id = region_id or (regions[0] if regions else "")
        if not region_id:
            continue
        words = " ".join((_text(entity.get("name")), _text(entity.get("short_summary")),
                          _text(entity.get("consequence"))))
        levers = tuple(
            {"action": f"quest:{_text(quest.get('id'))}", "effect": "lower", "amount": _QUEST_PULL}
            for quest in quests
            if pressure_id in _texts(quest.get("pressure_ids")) and " " not in _text(quest.get("id"))
        )
        try:
            pressures.append(WorldPressure(
                pressure_id=pressure_id, name=_short(_text(entity.get("name")) or pressure_id, 120),
                description=_short(_text(entity.get("short_summary") or entity.get("description")), 600),
                region_id=region_id, dimension=_dimension(words), severity=50.0, levers=levers,
            ))
        except ValidationError:
            continue
    return pressures + list(derived_pressures(canon))


def _bestiary(canon: Mapping[str, Any]) -> list[CreaturePlay]:
    creatures = []
    for row in lore_rows(canon, "bestiary"):
        creature_id = _text(row.get("id"))
        if not creature_id:
            continue
        creatures.append(CreaturePlay(id=creature_id, stats=threat_stats(_text(row.get("threat"))),
                                      behaviour=derived_behaviour(row)))
    return creatures


def generate_play_sections(revision: Any, *, start_location_id: str = "") -> dict[str, Any]:
    """A draft of every section from the revision's lore; a section the world already wrote is kept as written. A
    quest's steps are its author's: World Forge drafts none (a quest without them is done by reaching its places)."""
    canon = dict(getattr(revision, "canon", None) or {})
    written = play_sections_document(canon)
    authored = set(parse_play_sections(canon)[0].authored)
    model = session_world_model(revision, SimpleNamespace(starting_location_id=start_location_id))
    places = {_text(row.get("id")): row for row in lore_location_rows(canon, dict(getattr(revision, "topology", None)
                                                                                    or {}))}
    draft = {
        "economy": written["economy"] if "economy" in authored
        else {"providers": [row.model_dump(mode="json", exclude_none=True) for row in _economy(canon, model)]},
        "routines": written["routines"] if "routines" in authored
        else [row.model_dump(mode="json", exclude_none=True) for row in _routines(model)],
        "knowledge": written["knowledge"] if "knowledge" in authored
        else [row.model_dump(mode="json", exclude_none=True) for row in _knowledge(canon)],
        "pressures": written["pressures"] if "pressures" in authored
        else [row.model_dump(mode="json", exclude_none=True) for row in _pressures(canon, places)],
        "bestiary": written["bestiary"] if "bestiary" in authored
        else [row.model_dump(mode="json", exclude_none=True) for row in _bestiary(canon)],
        "quests": written["quests"],
    }
    return PlaySectionsDraft.model_validate(draft).model_dump(mode="json", exclude_none=True)


__all__ = ["generate_play_sections"]
