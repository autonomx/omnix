"""The balance simulation (RQ-5.3; docs/rpg/design/README.md, "Balance bands").

A deterministic "reasonable player" plays a campaign on the turn pipeline's own rules, in memory: each turn is read,
planned and resolved as the turn route does, its changes reduced, the world ticked and what it led to followed (quests,
pressures; no persistence, no narration, no model call). The policy rests when hurt, eats or buys food when hungry,
buys a better weapon or armour when it has coin to spare and wears it, has its gear improved where it carries the
materials (EV-5), takes every quest offered and does it (walks to its places, or its stage's first way: the creature,
the person, the place), fights what the world holds, breaks away when losing (from a finale, which has no breaking
away, it drinks a potion instead, if it has one), and otherwise wanders. ``simulate`` returns the
measures the bands are judged on after each checkpoint.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.reducer import ChangeRejected, reduce

BANDS = {  # docs/rpg/design/README.md: (low, high) after 100 turns, and after 500
    100: {"level": (2, 4), "purse": (50, 2_000), "win_rate": (0.55, 0.90), "defeats": (0, 3),
          "low_hp_share": (0.0, 0.15), "starving_share": (0.0, 0.05), "quests_completed": (1, 10_000)},
    500: {"level": (5, 9), "purse": (200, 10_000), "win_rate": (0.55, 0.90), "defeats": (0, 10),
          "low_hp_share": (0.0, 0.15), "starving_share": (0.0, 0.05), "quests_completed": (4, 10_000)},
}


@dataclass
class _Tally:
    fights_started: int = 0
    spent: int = 0  # copper paid out (EV-5: the purse rises and is spent)
    fights_won: int = 0
    defeats: int = 0
    low_hp_turns: int = 0
    starving_turns: int = 0
    unplanned: int = 0
    commands: dict[str, int] = field(default_factory=dict)
    fights: dict[str, dict[str, int]] = field(default_factory=dict)  # by foe: how each fight ended
    rounds: dict[str, list[int]] = field(default_factory=dict)  # EV-2: each won or lost fight's rounds, by kind
    boss_turns: int = 0
    boss_potions: int = 0


def _player(session: Mapping[str, Any]) -> dict[str, Any]:
    return _d(_d(session.get("simulation_state")).get("player_state"))


def _hp(session: Mapping[str, Any]) -> tuple[int, int]:
    pool = _d(_d(_player(session).get("resources")).get("hp"))
    return int(pool.get("current") or 0), max(1, int(pool.get("max") or 1))


def _purse(session: Mapping[str, Any]) -> int:
    currency = _d(_d(_player(session).get("inventory_state")).get("currency")) or _d(_player(session).get("currency"))
    return int(currency.get("gold") or 0) * 100 + int(currency.get("silver") or 0) * 10 + int(currency.get("copper") or 0)


def _world(session: Mapping[str, Any]) -> dict[str, Any]:
    return _d(_d(session.get("simulation_state")).get("world_model"))


def _here(session: Mapping[str, Any]) -> str:
    return _s(_player(session).get("location_id"))


def _path_to(session: Mapping[str, Any], goals: set[str]) -> str:
    """The first place on the shortest road from here to any of ``goals`` ("" when none is reachable)."""
    here = _here(session)
    roads: dict[str, set[str]] = {}
    for route in _l(_world(session).get("routes")):
        a, b = _s(_d(route).get("from")), _s(_d(route).get("to"))
        roads.setdefault(a, set()).add(b)
        roads.setdefault(b, set()).add(a)
    seen, queue = {here}, deque([(here, "")])
    while queue:
        place, first = queue.popleft()
        if place in goals and place != here:
            return first
        for road in sorted(roads.get(place, ())):
            if road not in seen:
                seen.add(road)
                queue.append((road, first or road))
    return ""


def _wild(session: Mapping[str, Any], place_id: str) -> bool:
    from app.apps.rpg.rules.routines import is_wild

    return is_wild(_d(session.get("simulation_state")), place_id)


def _wild_places(session: Mapping[str, Any]) -> set[str]:
    """Where no one lives: where the world's creatures are met (encounters.md)."""
    return {_s(place) for place in _d(_world(session).get("locations")) if _wild(session, _s(place))}


def _name(session: Mapping[str, Any], place_id: str) -> str:
    return _s(_d(_d(_world(session).get("locations")).get(place_id)).get("name")) or place_id


def _food_offer(session: Mapping[str, Any], place_id: str) -> tuple[str, str]:
    world = _world(session)
    for provider_id, offers in sorted(_d(world.get("offers")).items()):
        person = _d(_d(world.get("npcs")).get(provider_id))
        if _s(person.get("location_id")) != place_id:
            continue
        for offer in _l(offers):
            if _s(_d(offer).get("service_kind") or _d(offer).get("kind")) in {"meal", "food", "drink_meal"}:
                return _s(_d(offer).get("label")), _s(person.get("name"))
    return "", ""


def _lodging(session: Mapping[str, Any], place_id: str) -> tuple[str, int]:
    """Someone here who lets rooms, and the cheapest room's price in copper (("", 0) when no one does)."""
    world = _world(session)
    for provider_id, offers in sorted(_d(world.get("offers")).items()):
        person = _d(_d(world.get("npcs")).get(provider_id))
        rooms = [_d(offer) for offer in _l(offers)
                 if _s(_d(offer).get("service_kind") or _d(offer).get("kind")) in {"lodging", "room"}]
        if _s(person.get("location_id")) == place_id and rooms:
            return _s(person.get("name")), min(_copper(_d(room.get("price"))) for room in rooms)
    return "", 0


def _spoils_to_sell(session: Mapping[str, Any]) -> tuple[str, str] | None:
    """A spoil of a fight the hero carries (not food), and someone here who buys its kind; else ``None``."""
    world = _world(session)
    carried = [_d(item) for item in _l(_d(_player(session).get("inventory_state")).get("items"))
               if _s(_d(item).get("source")) == "loot" and _s(_d(item).get("category") or _d(item).get("type")) != "food"]
    for provider_id, provider in sorted(_d(world.get("providers")).items()):
        kinds = set(_l(_d(_d(provider).get("buys")).get("item_types")))
        if _s(_d(provider).get("location_id")) != _here(session) or not kinds:
            continue
        for item in carried:
            if _s(item.get("category") or item.get("type")) in kinds:
                return _s(item.get("name")), _s(_d(provider).get("provider_name"))
    return None


_GEAR_SLOTS = {"main_hand": "damage_max", "body": "armor", "off_hand": "armor", "head": "armor"}
SPARE_COPPER = 300  # what the player keeps for food and rooms before spending on gear


def _gear(session: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """What the hero wears, by slot: the carried row and its numbers."""
    store = _d(_player(session).get("inventory_state"))
    worn = _d(store.get("equipment"))
    items = {_s(_d(item).get("item_id")): _d(item) for item in _l(store.get("items"))}
    return {slot: items[item_id] for slot, item_id in worn.items() if item_id in items}


def _equipment(row: Mapping[str, Any]) -> dict[str, Any]:
    from app.apps.rpg.rules.interactions.equipment_runtime import item_equipment

    return _d(item_equipment(dict(row)))  # as it fights: its own block, else its kind's ("Iron Dagger": a dagger)


def _score(row: Mapping[str, Any], slot: str) -> int:
    return int(_d(_equipment(row).get("stats")).get(_GEAR_SLOTS[slot]) or 0)


def gear_score(session: Mapping[str, Any]) -> int:
    """How well the hero is armed and armoured: the worn weapon's most damage and the worn armour's."""
    return sum(_score(row, slot) for slot, row in _gear(session).items() if slot in _GEAR_SLOTS)


def _gear_step(session: Mapping[str, Any]) -> str:
    """A better piece of gear carried and not worn, put on; one on sale here bought with coin to spare; else gear
    improved where an upgrade is sold. The trade rule is asked first, so a purchase it would refuse (an upgrade
    without its materials, or past the level's budget) is not tried."""
    from app.apps.rpg.rules.economy.trade import buy

    store = _d(_player(session).get("inventory_state"))
    worn = _gear(session)
    for item in map(_d, _l(store.get("items"))):
        slot = _s(_equipment(item).get("slot"))
        if slot in _GEAR_SLOTS and _s(item.get("item_id")) not in _d(store.get("equipment")).values() \
                and _score(item, slot) > _score(worn.get(slot, {}), slot):
            return f"I equip the {_s(item.get('name'))}."
    here = _here(session)
    world = _world(session)
    simulation = _d(session.get("simulation_state"))
    for provider_id, provider in sorted(_d(world.get("providers")).items()):
        if _s(_d(provider).get("location_id")) != here:
            continue
        for offer in map(_d, _l(_d(world.get("offers")).get(provider_id))):
            added = [_d(row) for row in _l(_d(offer.get("effects")).get("items_added"))]
            slot = _s(_equipment(added[0]).get("slot")) if added else ""
            better = slot in _GEAR_SLOTS and _score(added[0], slot) > _score(worn.get(slot, {}), slot)
            if not better and _s(offer.get("service_kind")) != "upgrade":
                continue
            outcome = buy(simulation, _s(offer.get("offer_id")), provider_id)
            paid = -sum(int(getattr(change, "delta_copper", 0) or 0) for change in (outcome.changes if outcome else ()))
            if outcome is not None and outcome.kind == "bought" and _purse(session) - paid >= SPARE_COPPER:
                return f"I buy {_s(offer.get('label'))} from {_s(_d(provider).get('provider_name'))}."
    return ""


def _potions(session: Mapping[str, Any]) -> int:
    """How many potions the hero carries."""
    return sum(int(_d(row).get("qty") or _d(row).get("quantity") or 1)
               for row in _l(_d(_player(session).get("inventory_state")).get("items"))
               if "potion" in _s(_d(row).get("name")).casefold())


def _copper(price: Mapping[str, Any]) -> int:
    return int(price.get("gold") or 0) * 100 + int(price.get("silver") or 0) * 10 + int(price.get("copper") or 0)


def _command(session: Mapping[str, Any], turn: int) -> str:
    """The reasonable player's next command."""
    simulation = _d(session.get("simulation_state"))
    hp, max_hp = _hp(session)
    combat = _d(simulation.get("combat_state"))
    if combat.get("active") is True:
        if hp >= max_hp * 0.25:
            return "attack"
        finale = any(_d(row).get("no_escape") and _s(_d(row).get("side")) == "enemy" and int(_d(row).get("hp") or 0) > 0
                     for row in _d(combat.get("participants")).values())
        if not finale:  # a finale has no breaking away (EV-2): a potion if one is carried, else the fight goes on
            return "I break away and flee."
        potion = next((_s(_d(item).get("name")) for item in _l(_d(_player(session).get("inventory_state")).get("items"))
                       if "potion" in _s(_d(item).get("name")).casefold()), "")
        return f"I drink the {potion}." if potion else "attack"
    hunger = int(_d(simulation.get("survival")).get("hunger") or 0)
    if hunger > 60:
        food = next((_s(_d(item).get("name")) for item in _l(_d(_player(session).get("inventory_state")).get("items"))
                     if _s(_d(item).get("category") or _d(item).get("type")) in {"food", "consumable"}
                     and _s(_d(item).get("name"))), "")
        if food:
            return f"I eat the {food}."
        label, seller = _food_offer(session, _here(session))
        if label:
            return f"I buy {label} from {seller}."
        places = {place for place in _d(_world(session).get("locations")) if _food_offer(session, place)[0]}
        step = _path_to(session, places)
        if step:
            return f"go to {_name(session, step)}"
    if hp < max_hp * 0.40:  # a night's sleep heals (a short rest does not): a room where rooms are let, else a camp
        if any(_s(_d(row).get("service_kind")) == "lodging" and _s(_d(row).get("status")) == "active"
               for row in _l(simulation.get("active_services"))):
            return "I go to my room and sleep for the night."
        keeper, price = _lodging(session, _here(session))
        if keeper and _purse(session) >= price:
            return f"I rent a room for the night from {keeper}."
        if not keeper:
            return "I make camp and sleep for the night."
        # No coin for the room: out to where no one lets rooms, and camp there.
        step = _path_to(session, {place for place in _d(_world(session).get("locations")) if not _lodging(session, place)[0]})
        if step:
            return f"go to {_name(session, step)}"
    spoils = _spoils_to_sell(session)
    if spoils:  # what the fights left them, sold to someone here who buys its kind (food is kept)
        return f"I sell my {spoils[0]} to {spoils[1]}."
    gear = _gear_step(session)
    if gear:  # better gear, put on or bought with coin to spare, or improved (EV-5)
        return gear
    if int(_player(session).get("level_choices_pending") or 0) > 0:  # a level's choice: strength, then dexterity
        return "raise my strength" if int(_player(session).get("level") or 1) % 2 else "raise my dexterity"
    quests = [_d(quest) for quest in _l(_d(simulation.get("quest_state")).get("quests"))]
    offered = next((quest for quest in quests if quest.get("status") == "available"), None)
    if offered:
        return f"I accept the quest {_s(offered.get('title'))}."
    goals = {_s(place) for quest in quests if quest.get("status") == "active" and not _l(quest.get("steps"))
             for place in _l(quest.get("locations")) if _s(place) not in _l(quest.get("visited_locations"))}
    for quest in quests:  # a quest of steps: its stage's first way (quests.md)
        steps, stage = _l(quest.get("steps")), int(_d(quest.get("progress")).get("stage") or 0)
        if quest.get("status") != "active" or stage >= len(steps):
            continue
        from app.apps.rpg.rules.quest.progress import step_ways

        condition = _d((step_ways(_d(steps[stage]))[0][0] or [{}])[0])
        if condition.get("defeat"):
            from app.apps.rpg.rules.combat.campaign_mechanics import campaign_creature_definition

            creature = _d(campaign_creature_definition(simulation, _s(condition["defeat"])))
            places = {_s(place) for place in _l(quest.get("locations"))}
            if _s(creature.get("name")) and (_wild(session, _here(session)) or _here(session) in places):
                return f"I attack the {_s(creature.get('name'))}."
            goals.update(places or _wild_places(session))  # hunted where the quest says, else where no one lives
        elif condition.get("talk"):
            from app.apps.rpg.rules.routines import clock, whereabouts

            person = _d(_d(_world(session).get("npcs")).get(_s(condition["talk"])))
            about = [_s(word) for word in (_l(condition.get("about")) or [condition.get("about")]) if _s(word)]
            where = whereabouts(simulation, clock(simulation)).get(_s(condition["talk"]))  # where their day has them
            at = where.location_id if where else _s(person.get("location_id"))
            if at == _here(session):
                return f"I ask {_s(person.get('name'))} about the {about[0] if about else 'job'}."
            goals.add(at)
        elif condition.get("reach"):
            goals.add(_s(condition["reach"]))
        elif condition.get("companion"):  # someone met along the way, asked to come
            from app.apps.rpg.rules.routines import clock, companions, present_at

            wanted = _s(condition["companion"])
            here = [npc for npc in present_at(simulation, _here(session), clock(simulation))
                    if npc not in companions(simulation) and wanted in {"anyone", npc}]
            if here:
                name = _s(_d(_d(_world(session).get("npcs")).get(here[0])).get("name"))
                return f"I ask {name} to join my party."
    goals.discard("")
    if turn % 4 == 0 and not _wild(session, _here(session)):  # the world's creatures keep to the wild
        step = _path_to(session, _wild_places(session)) if turn % 8 == 0 else ""
        if step:
            return f"go to {_name(session, step)}"
    elif turn % 4 == 0:  # the world's creatures, met now and then
        level = int(_player(session).get("level") or 1)
        creatures = sorted((_s(_d(row).get("name")) for row in _d(_d(simulation.get("campaign_mechanics")).get(
            "creatures")).values() if int(_d(row).get("level") or 1) <= level + 2 and _s(_d(row).get("name"))))
        if creatures:
            return f"I attack the {creatures[turn // 4 % len(creatures)]}."
    step = _path_to(session, goals) if goals else ""
    if step:
        return f"go to {_name(session, step)}"
    neighbours = sorted({_s(_d(route).get("to")) if _s(_d(route).get("from")) == _here(session) else _s(_d(route).get("from"))
                         for route in _l(_world(session).get("routes"))
                         if _here(session) in {_s(_d(route).get("from")), _s(_d(route).get("to"))}})
    if neighbours and turn % 3 == 0:
        return f"go to {_name(session, neighbours[turn % len(neighbours)])}"
    return "look around"


def _turn(session: dict[str, Any], text: str) -> tuple[dict[str, Any], bool]:
    """One turn on the pipeline's rules, in memory; ``False`` when no rule of the pipeline plays it."""
    from app.apps.rpg.session.turn.intent import valid_readings
    from app.apps.rpg.session.turn.planning import plan_action
    from app.apps.rpg.session.turn.resolution import resolve_turn
    from app.apps.rpg.session.turn.run import turn_consequences
    from app.apps.rpg.session.turn.world_tick import world_tick
    from tests.support.rpg_line_reader.reader import read_line, scene_of

    simulation = _d(session.get("simulation_state"))
    # Every typed line is the model's to read (EV-9); the simulation reads it as the scripted model does.
    readings = valid_readings(list(read_line(session, text).get("readings") or ()), scene_of(session))
    planned = (plan_action(readings[0], fighting=_d(simulation.get("combat_state")).get("active") is True)
               if readings else None)
    resolution = resolve_turn(planned, session, text) if planned is not None else None
    if resolution is None and planned is not None and planned.mechanic == "talk" and planned.target_id:
        # A conversation needs the model's line, which the simulation does not call: the person is taken to answer.
        from app.apps.rpg.foundation.state.changes import DialogueExchanged
        from app.apps.rpg.session.turn.resolution import Resolution

        resolution = Resolution([DialogueExchanged(npc_id=planned.target_id, player_line=text[:500])], [], minutes=1,
                                needs="standard_turn")
    if resolution is None:
        return session, False
    try:
        document, _ = reduce(session, resolution.changes)
        if resolution.minutes:
            ticked, _, _ = world_tick(document, needs=resolution.needs, minutes=resolution.minutes,
                                      turn_key=f"sim:{_d(document.get('state')).get('turn_count')}")
            document, _ = reduce(document, ticked)
        else:
            ticked = []
        document, _, _ = turn_consequences(document, [*resolution.changes, *ticked])  # step 5: what it led to
    except ChangeRejected:
        return session, False
    return document, True


def _measures(session: Mapping[str, Any], tally: _Tally, turns: int) -> dict[str, Any]:
    quests = [_d(quest) for quest in _l(_d(_d(session.get("simulation_state")).get("quest_state")).get("quests"))]
    return {
        "turns": turns, "level": int(_player(session).get("level") or 1), "purse": _purse(session),
        # EV-5's bands: how the hero is armed (the worn weapon's and armour's numbers) and the coin spent so far.
        "gear": gear_score(session), "spent": tally.spent,
        "win_rate": round(tally.fights_won / tally.fights_started, 3) if tally.fights_started else None,
        "fights_started": tally.fights_started, "defeats": tally.defeats,
        "low_hp_share": round(tally.low_hp_turns / turns, 3), "starving_share": round(tally.starving_turns / turns, 3),
        "quests_completed": sum(1 for quest in quests if quest.get("status") == "completed"),
        "unplanned": tally.unplanned, "commands": dict(sorted(tally.commands.items(), key=lambda kv: -kv[1])[:8]),
        # EV-2's pacing: the median rounds of an ordinary fight and of a boss's, and a boss fight's potion share.
        "ordinary_fight_rounds": _median(tally.rounds.get("ordinary", [])),
        "boss_fight_rounds": _median(tally.rounds.get("boss", [])),
        "boss_potion_share": round(tally.boss_potions / tally.boss_turns, 3) if tally.boss_turns else None,
        "fights": tally.fights,
    }


def simulate(session: Mapping[str, Any], *, turns: int = 500, checkpoints: tuple[int, ...] = (100, 500)) -> dict[int, dict]:
    """Play ``turns`` turns; the measures at each checkpoint."""
    from app.apps.rpg.rules.player.player_progression_state import ensure_player_progression_state
    from app.apps.rpg.session.public_state_bridge import hydrate_simulation_player

    document = hydrate_simulation_player(deepcopy(dict(session)))
    document["simulation_state"]["player_state"] = ensure_player_progression_state(_player(document))
    tally, report = _Tally(), {}
    for turn in range(1, turns + 1):
        text = _command(document, turn)
        verb = text.split()[1] if text.startswith("I ") else text.split()[0]
        tally.commands[verb] = tally.commands.get(verb, 0) + 1
        fighting = _d(_d(document.get("simulation_state")).get("combat_state")).get("active") is True
        defeats = int(_player(document).get("defeats") or 0)
        purse, potions = _purse(document), _potions(document)
        document, played = _turn(document, text)
        if text.startswith("I buy"):  # coin paid for goods and services (a defeat's loss is no purchase)
            tally.spent += max(0, purse - _purse(document))
        if not played:
            tally.unplanned += 1
            document, _ = _turn(document, "wait")
        combat = _d(_d(document.get("simulation_state")).get("combat_state"))
        if not fighting and combat.get("active") is True:
            tally.fights_started += 1
        if fighting and combat.get("active") is not True and combat.get("ended_reason") == "enemy_side_defeated":
            tally.fights_won += 1
        boss = any(_d(row).get("boss") for row in _d(combat.get("participants")).values()
                   if _s(_d(row).get("side")) == "enemy")
        if fighting and boss:  # a boss fight's turns, and those spent on a potion (EV-2's pacing)
            tally.boss_turns += 1
            tally.boss_potions += _potions(document) < potions  # one was drunk, not only asked for
        if fighting and combat.get("active") is not True and combat.get("ended_reason") in {
                "enemy_side_defeated", "party_side_defeated"}:
            tally.rounds.setdefault("boss" if boss else "ordinary", []).append(int(combat.get("round") or 1))
        if fighting and combat.get("active") is not True:
            foe = next((_s(_d(row).get("name")) for row in _d(combat.get("participants")).values()
                        if _s(_d(row).get("side")) == "enemy"), "?")
            ended = tally.fights.setdefault(foe, {})
            ended[_s(combat.get("ended_reason")) or "?"] = ended.get(_s(combat.get("ended_reason")) or "?", 0) + 1
        tally.defeats += int(_player(document).get("defeats") or 0) > defeats
        hp, max_hp = _hp(document)
        tally.low_hp_turns += hp < max_hp * 0.25
        tally.starving_turns += int(_d(_d(document.get("simulation_state")).get("survival")).get("hunger") or 0) >= 80
        if turn in checkpoints:
            report[turn] = _measures(document, tally, turn)
    return report


def _median(values: list[int]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    return float(ordered[middle]) if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


# EV-2's pacing targets: an ordinary fight lasts 3-5 rounds and a boss 8-12; a boss fight's potions under a quarter.
PACING = {"ordinary_fight_rounds": (3, 5), "boss_fight_rounds": (8, 12), "boss_potion_share": (0.0, 0.25)}


def pacing_outside(report: Mapping[int, Mapping[str, Any]]) -> list[str]:
    """The pacing targets a report breaks, at its last checkpoint (a measure with no fight of its kind is not
    judged)."""
    if not report:
        return []
    turns = max(report)
    return [f"after {turns} turns, {key} {report[turns].get(key)} is outside {low}-{high}"
            for key, (low, high) in PACING.items()
            if report[turns].get(key) is not None and not low <= report[turns][key] <= high]


def outside(report: Mapping[int, Mapping[str, Any]]) -> list[str]:
    """The bands a report breaks."""
    broken = []
    for turns, measures in report.items():
        for key, (low, high) in BANDS.get(turns, {}).items():
            value = measures.get(key)
            if value is not None and not low <= value <= high:
                broken.append(f"after {turns} turns, {key} {value} is outside {low}-{high}")
    return broken


__all__ = ["BANDS", "PACING", "outside", "pacing_outside", "simulate"]
