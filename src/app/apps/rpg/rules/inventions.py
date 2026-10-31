"""What the game master invents (evolution roadmap EV-0, part 2). Pure.

When the story needs someone or something the world does not have, the game master may invent a person, a place, an
item, a creature or a quest (``gm_invent``). An invention is a lore entry in the shape the world model's entries of its
family already have, and it carries its play data, as an authored entry's play sections would:

- a person: their home (``location_id``), their day (``schedule``, as a routine's) and what they know (``knowledge``);
- a place: its roads to the world's places (``roads``: ``{"to", "travel_time"}``, at least one);
- an item: its type, and for gear its slot and numbers (``equipment``); where it lies (``location_id``) or who sells
  it, at what price (``seller_id``, ``price_copper``);
- a creature: its level and numbers (``hp``, ``damage_max``, ``defense``), behaviour, weakness and resistances;
- a quest: who gives it, its objective, its steps (each a list of conditions, as authored steps are), its reward.

``fold_invention`` checks it before it is played, mechanically: its id is the campaign's own (``gm:<campaign>:<name>``)
and new, and its name clashes with no entry of the world's; what it names exists and is not kept from the hero; its
numbers sit inside the level's budgets (``rules/budgets.py``); the facts it sets contradict none that hold; its text
names no secret; a place joins the roads; within the game master's day's limit. Folded in, it is ``InventionAdded``:
the reducer keeps it in the campaign's lore layer and adds it to the effective world model, where every rule reads
it, and the commit files it for its world's review where question 15 says it goes. Whether its prose fits the canon's
meaning is the review's to judge.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import FactSet, InventionAdded, StateChange

FAMILIES = ("person", "place", "item", "creature", "quest")
MAX_TEXT = 600
_CONDITIONS = ("reach", "talk", "hold", "defeat", "check", "companion")


def invention_id(campaign_id: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:60]
    return f"gm:{campaign_id}:{slug}"


def _campaign(document: Mapping[str, Any]) -> str:
    manifest = _d(document.get("manifest"))
    return _s(manifest.get("id") or manifest.get("session_id")) or "campaign"


def _level(simulation: Mapping[str, Any]) -> int:
    return max(1, int(_d(_sections.player_state_of(simulation)).get("level") or 1))


def _known_names(simulation: Mapping[str, Any]) -> set[str]:
    from app.apps.rpg.rules.hero_knowledge import world_entries

    return {_s(row.get(key)).casefold() for row in world_entries(simulation).values()
            for key in ("name", "title") if _s(row.get(key))}


def _hidden(simulation: Mapping[str, Any], entry_id: str, *, family: str = "") -> bool:
    """Whether ``entry_id`` is not one of the world's entries (of ``family``, when given) that the hero may be shown."""
    from app.apps.rpg.rules.hero_knowledge import world_entries

    row = world_entries(simulation).get(entry_id)
    return (row is None or row.get("hidden") is True or row.get("secret") is True
            or bool(family) and row.get("family") != family)


def _person(simulation: Mapping[str, Any], name: str, text: str, play: Mapping[str, Any]) -> tuple[dict, dict, str]:
    home = _s(play.get("location_id"))
    if _hidden(simulation, home, family="place"):
        return {}, {}, "a person needs a home among the world's places"
    schedule = []
    for step in map(_d, _l(play.get("schedule"))[:6]):
        start, end, place = int(step.get("from_hour") or 0), int(step.get("to_hour") or 24), _s(step.get("location_id"))
        if not (0 <= start < end <= 24) or _hidden(simulation, place, family="place"):
            return {}, {}, "a step of their day is not an hour range at one of the world's places"
        schedule.append({"from_hour": start, "to_hour": end, "location_id": place,
                         "activity": _s(step.get("activity"))[:160]})
    knowledge = [{"fact_id": f"knowledge:{index}", "text": _s(fact.get("text"))[:MAX_TEXT], "shares": "freely",
                  "topics": [_s(topic) for topic in _l(fact.get("topics"))[:6]]}
                 for index, fact in enumerate(map(_d, _l(play.get("knowledge"))[:4])) if _s(fact.get("text"))]
    row = {"name": name, "role": _s(play.get("role"))[:120], "description": text, "location_id": home}
    return row, {"schedule": schedule, "knowledge": knowledge}, ""


def _place(simulation: Mapping[str, Any], name: str, text: str, play: Mapping[str, Any]) -> tuple[dict, dict, str]:
    roads = [{"to": _s(road.get("to")), "travel_time": _s(road.get("travel_time"))[:40] or "30 minutes"}
             for road in map(_d, _l(play.get("roads"))[:4])]
    if not roads or any(_hidden(simulation, road["to"], family="place") for road in roads):
        return {}, {}, "a place joins the roads: it needs a road to one of the world's places"
    region = _s(_d(_d(_d(_sections.world_model_of(simulation)).get("locations")).get(roads[0]["to"])).get("region_id"))
    row = {"name": name, "description": text, "region_id": region, "deferred": True,
           "exits": {_s(_d(_d(_d(_sections.world_model_of(simulation)).get("locations")).get(road["to"])).get("name"))
                     .casefold() or road["to"]: road["to"] for road in roads}}
    return row, {"roads": roads}, ""


def _item(simulation: Mapping[str, Any], entry_id: str, name: str, text: str,
          play: Mapping[str, Any]) -> tuple[dict, dict, str]:
    from app.apps.rpg.rules.budgets import SLOTS, budget

    row: dict[str, Any] = {"id": entry_id, "name": name, "type": _s(play.get("type"))[:40] or "trinket",
                           "rarity": "uncommon", "effect": text}
    item_budget = None
    if isinstance(play.get("equipment"), Mapping):
        equipment = _d(play["equipment"])
        slot = _s(equipment.get("slot"))
        if slot not in SLOTS:
            return {}, {}, f"no slot {slot!r} to wear it in"
        stats = {key: int(value) for key, value in _d(equipment.get("stats")).items()
                 if key in {"damage_min", "damage_max", "accuracy_bonus", "armor", "defense_bonus"}
                 and isinstance(value, (int, float))}
        item_budget = budget(simulation, _level(simulation)).items[slot]
        # Every number it fights with sits inside the level's budget for its slot: damage only for a weapon (and
        # from no more than to), armor only for what is worn as armor, a small bonus at most.
        weapon, armor = item_budget.damage_max, item_budget.armor
        if weapon is None and (stats.get("damage_min") or stats.get("damage_max")):
            return {}, {}, f"what is worn as {slot} does no damage"
        if weapon is not None and not weapon.holds(int(stats.get("damage_max") or 0)):
            return {}, {}, f"its damage is outside the level's budget ({weapon.low}-{weapon.high})"
        if int(stats.get("damage_min") or 0) > int(stats.get("damage_max") or 0):
            return {}, {}, "its least damage is more than its most"
        if "armor" in stats and (armor is None or not armor.holds(stats["armor"])):
            bounds = f" ({armor.low}-{armor.high})" if armor is not None else ""
            return {}, {}, f"its armor is outside the level's budget{bounds}"
        most_bonus = 1 + _level(simulation) // 4
        if any(not 0 <= stats.get(key, 0) <= most_bonus for key in ("accuracy_bonus", "defense_bonus")):
            return {}, {}, f"its bonus is outside the level's budget (0-{most_bonus})"
        row["equipment"] = {"slot": slot, "stats": stats}
    out: dict[str, Any] = {}
    if _s(play.get("location_id")):
        if _hidden(simulation, _s(play.get("location_id")), family="place"):
            return {}, {}, "it lies at no place of the world's"
        out["location_id"] = _s(play.get("location_id"))
    if _s(play.get("seller_id")):
        seller = _s(play.get("seller_id"))
        price = int(play.get("price_copper") or 0)
        band = (item_budget or budget(simulation, _level(simulation)).items["tool"]).price_copper
        if seller not in _d(_d(_sections.world_model_of(simulation)).get("providers")) or not band.holds(price):
            return {}, {}, f"a seller of the world's sells it, at a price within {band.low}-{band.high} copper"
        out["offer"] = {"offer_id": f"{seller}:{entry_id}", "provider_id": seller, "label": name, "description": text,
                        "service_kind": "shop_goods", "availability": "available",
                        "price": {"gold": 0, "silver": price // 100, "copper": price % 100},
                        "effects": {"items_added": [{"item_id": entry_id, "name": name, "quantity": 1,
                                                     "type": row["type"], "description": text,
                                                     **({"equipment": row["equipment"]} if "equipment" in row else {})}]}}
    if not out:
        return {}, {}, "an item lies somewhere, or someone sells it"
    return row, out, ""


def _creature(simulation: Mapping[str, Any], entry_id: str, name: str, text: str,
              play: Mapping[str, Any]) -> tuple[dict, dict, str]:
    from app.apps.rpg.rules.budgets import creature_findings

    level = max(1, min(_level(simulation) + 2, int(play.get("level") or _level(simulation))))
    combat = {"definition_id": entry_id, "name": name, "level": level, "hp": int(play.get("hp") or 0),
              "damage_min": max(1, int(play.get("damage_min") or 1)), "damage_max": int(play.get("damage_max") or 0),
              "defense": int(play.get("defense") or 0), "armor": 0, "accuracy_bonus": 0, "initiative_bonus": 0,
              "behaviour": _s(play.get("behaviour")) or "fights", "morale_threshold": 35, "loot": [],
              "budget_cost": 25 * level, "xp_value": 25 * level, "source": "game_master",
              "tags": [_s(tag) for tag in _l(play.get("tags"))[:4]], "description": text,
              "resists": [_s(kind) for kind in _l(play.get("resists"))[:3]]}
    if _s(play.get("weakness")):
        combat["vulnerabilities"] = [{"trigger_tag": _s(play.get("weakness")), "aliases": [], "condition": "stunned",
                                      "duration_turns": 1, "magnitude": 1}]
    found = creature_findings(simulation, combat)
    if combat["damage_min"] > combat["damage_max"]:
        found.append("its least damage is more than its most")
    if found:
        return {}, {}, found[0]
    return {"name": name, "description": text}, {"combat": combat}, ""


def _quest(simulation: Mapping[str, Any], entry_id: str, name: str, text: str,
           play: Mapping[str, Any]) -> tuple[dict, dict, str]:
    from app.apps.rpg.rules.budgets import budget

    giver = _s(play.get("giver_id"))
    if _hidden(simulation, giver, family="person"):
        return {}, {}, "a quest needs a giver among the world's people"
    steps = []
    for index, step in enumerate(map(_d, _l(play.get("steps"))[:5])):
        conditions = [_d(row) for row in _l(step.get("conditions"))[:4]]
        if not conditions or any(_s(row.get("kind")) not in _CONDITIONS for row in conditions):
            return {}, {}, "each step names conditions of the kinds a quest's steps use"
        for row in conditions:
            subject = _s(row.get("subject"))
            family = {"reach": "place", "talk": "person", "hold": "item"}.get(_s(row.get("kind")), "")
            if family and _hidden(simulation, subject, family=family):
                return {}, {}, f"a step names {subject!r}, which is no {family} the hero may be shown"
        # As the canon keeps a step and the quest rule reads it: all of its conditions, each ``{kind: subject}``.
        steps.append({"id": f"step-{index + 1}", "summary": _s(step.get("summary"))[:300] or name,
                      "all_of": [{_s(row.get("kind")): _s(row.get("subject")),
                                  **({"about": [_s(word) for word in _l(row.get("about"))]} if _l(row.get("about")) else {}),
                                  **({"count": int(row.get("count") or 1)} if _s(row.get("kind")) == "defeat"
                                     and int(row.get("count") or 1) > 1 else {})} for row in conditions]})
    if not steps:
        return {}, {}, "a quest has at least one step"
    reward = _d(play.get("reward"))
    rewards = budget(simulation, _level(simulation)).quest_reward
    xp, copper = int(reward.get("xp") or 0), int(reward.get("copper") or 0)
    if not rewards.xp.holds(xp) or not rewards.copper.holds(copper):
        return {}, {}, (f"its reward is outside the level's budget ({rewards.xp.low}-{rewards.xp.high} xp, "
                        f"{rewards.copper.low}-{rewards.copper.high} copper)")
    row = {"quest_id": entry_id, "title": name, "objective": _s(play.get("objective"))[:300] or text,
           "description": text, "giver_id": giver, "status": "available", "steps": steps, "tier": "side",
           "reward": {"xp": xp, "currency": {"gold": 0, "silver": copper // 100, "copper": copper % 100}}}
    return row, {"steps": steps}, ""


def fold_invention(document: Mapping[str, Any], payload: Mapping[str, Any]):
    """An invention the game master proposes, checked and folded in (``InventionAdded``), or refused, saying why."""
    return _invent(document, payload, limited=True)


def _invent(document: Mapping[str, Any], payload: Mapping[str, Any], *, limited: bool):
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.consequences import names_a_secret_here, world_facts
    from app.apps.rpg.rules.direction import allows, counted

    simulation = _d(_sections.simulation_state_of(document))
    family, name = _s(payload.get("family")), _s(payload.get("name")).strip()
    text, play = _s(payload.get("description")).strip()[:MAX_TEXT], _d(payload.get("play"))
    if family not in FAMILIES or not name or len(name) > 120:
        return refused("an invention is a person, place, item, creature or quest, with a name")
    entry_id = invention_id(_campaign(document), name)
    if entry_id in _d(_d(_sections.lore_layer_of(simulation)).get("entries")) or name.casefold() in _known_names(simulation):
        return refused(f"{name!r} clashes with an entry the world has")
    texts = [name, text, *(str(value) for value in _flat(play))]
    if any(names_a_secret_here(simulation, value) for value in texts if value):
        return refused("it names a secret")
    from app.apps.rpg.rules.consequences import authored_outcome

    facts = world_facts(simulation)
    sets = [_d(row) for row in _l(payload.get("sets"))[:4] if _s(_d(row).get("fact"))]
    for row in sets:
        held = facts.get(_s(row.get("fact")))
        if held is not None and held.get("value") != row.get("value", True):
            return refused(f"it contradicts {_s(row.get('fact'))}, which holds")
        if authored_outcome(simulation, _s(row.get("fact"))):
            return refused(f"{_s(row.get('fact'))} is an outcome the world's author left to the hero")
    sets = [row for row in sets if _s(row.get("fact")) not in facts]  # one already so is not set again
    shaped = {"person": lambda: _person(simulation, name, text, play),
              "place": lambda: _place(simulation, name, text, play),
              "item": lambda: _item(simulation, entry_id, name, text, play),
              "creature": lambda: _creature(simulation, entry_id, name, text, play),
              "quest": lambda: _quest(simulation, entry_id, name, text, play)}[family]
    row, played, why = shaped()
    if why:
        return refused(why)
    limit = allows(simulation, "invention") if limited else ""
    if limit:
        return refused(limit)
    if family == "place" and payload.get("hidden") is True:  # found by exploring (EV-10)
        row = {**row, "hidden": True, "difficulty": max(5, min(25, int(payload.get("difficulty") or 12)))}
    if family == "place" and isinstance(payload.get("site"), Mapping):
        from app.apps.rpg.rules.exploration import build_site

        site = _d(payload["site"])
        played = {**played, "site": {"theme": _s(site.get("theme"))[:200], "rooms": build_site(
            simulation, entry_id, _l(site.get("rooms")), boss_id=_s(site.get("boss_id")),
            reward_item_id=_reward(simulation, entry_id))}}
    provenance = {"campaign_id": _campaign(document), "source": "game_master",
                  "turn": int(_d(document.get("state")).get("turn_count") or 0), "reason": _s(payload.get("reason"))[:500]}
    changes: list[StateChange] = [InventionAdded(entry_id=entry_id, family=family, name=name, row=row, play=played,
                                                 provenance=provenance)]  # type: ignore[arg-type]
    changes += [FactSet(fact_id=_s(row.get("fact")), value=row.get("value", True), source=entry_id, known=False)
                for row in sets]
    return Folded([*changes, counted(simulation, "invention")] if limited else changes)


def _reward(simulation: Mapping[str, Any], site_id: str) -> str:
    """A site's reward among the world's things (no quest's): one, seeded by the site."""
    from app.apps.rpg.foundation.core.determinism import rng_for, stable_sub_index

    items = sorted(_s(_d(row).get("id")) for row in _l(_d(_sections.world_model_of(simulation)).get("items"))
                   if _s(_d(row).get("id")) and "quest" not in _s(_d(row).get("type")).casefold())
    if not items:
        return ""
    seed = int(_sections.rng_seed_of(simulation) or 0) % 2**64
    return rng_for(seed, 0, "site_reward", stable_sub_index(site_id)).choice(items)


def _area_places(simulation: Mapping[str, Any], area_id: str) -> list[str]:
    locations = _d(_d(_sections.world_model_of(simulation)).get("locations"))
    return sorted(place_id for place_id, row in locations.items()
                  if (_s(_d(row).get("region_id")) == area_id or place_id == area_id) and _d(row).get("hidden") is not True
                  and not _d(row).get("site_id"))


def _held(simulation: Mapping[str, Any], area_id: str, kind: str) -> int:
    """How many entries of ``kind`` the area already holds: those filled in, and the places and people its author
    wrote, which count toward its budget."""
    filled = sum(1 for row in _l(_d(_d(_sections.area_detail_of(simulation)).get(area_id)).get("entries"))
                 if _s(_d(row).get("kind")) == kind)
    places = [place for place in _area_places(simulation, area_id) if not place.startswith("gm:")]
    if kind == "place":
        return filled + len(places)
    if kind == "person":
        people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
        return filled + sum(1 for npc_id, person in people.items() if not str(npc_id).startswith("gm:")
                            and _s(_d(person).get("location_id")) in places)
    return filled


def fold_area_entry(document: Mapping[str, Any], payload: Mapping[str, Any]):
    """An entry of a larger area the game master fills in as the hero approaches (EV-10): within the area's budget of
    its kind (``rules/budgets.area_budget``; authored detail counts toward it), checked as any invention, then played
    (``InventionAdded``, with ``AreaDetailed``). A rumour goes about the area's places; lore is kept with the area."""
    from app.apps.rpg.foundation.state.changes import AreaDetailed
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.budgets import area_budget
    from app.apps.rpg.rules.consequences import names_a_secret_here
    from app.apps.rpg.rules.rumours import spread

    simulation = _d(_sections.simulation_state_of(document))
    area_id, entry = _s(payload.get("area_id")), _d(payload.get("entry"))
    kind = _s(entry.get("kind"))
    places = _area_places(simulation, area_id)
    if not places:
        return refused("no such area in this world")
    budget = area_budget(simulation, area_id)
    if kind not in budget:
        return refused(f"an area holds no entry of the kind {kind!r}")
    if _held(simulation, area_id, kind) >= budget[kind]:
        return refused(f"{area_id} holds its {budget[kind]} of {kind} already")
    if kind in {"rumour", "lore"}:
        text = _s(entry.get("told"))[:600]
        if not text or names_a_secret_here(simulation, text):
            return refused("it needs a line, and names no secret")
        index = _held(simulation, area_id, kind) + 1
        entry_id = f"{kind}:{area_id}:{index}"
        made: list[StateChange] = [AreaDetailed(area_id=area_id, entry_id=entry_id, kind=kind, told=text)]  # type: ignore[arg-type]
        if kind == "rumour":
            made += spread(entry_id, text, places, source="game_master")
        return Folded(made)
    if kind == "service":
        return refused("an area's services are its people's wares: invent the person who keeps them")
    family = "place" if kind == "site" else kind
    shaped = {**entry, "family": family, **({"hidden": entry.get("hidden", True), "site": _d(entry.get("site"))}
                                            if kind == "site" else {})}
    folded = _invent(document, shaped, limited=False)
    if folded.refused:
        return folded
    invented = next(change for change in folded.changes if isinstance(change, InventionAdded))
    return Folded([*folded.changes, AreaDetailed(area_id=area_id, entry_id=invented.entry_id, kind=kind)])  # type: ignore[arg-type]


def _flat(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _flat(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _flat(item)]
    return []


def inventions(simulation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The campaign's lore layer: what the game master invented, by id."""
    return {str(entry_id): _d(row) for entry_id, row in _d(_d(_sections.lore_layer_of(simulation)).get("entries")).items()}


__all__ = ["FAMILIES", "fold_area_entry", "fold_invention", "invention_id", "inventions"]
