"""The balance simulation (RQ-5.3; docs/rpg/design/README.md, "Balance bands").

A deterministic "reasonable player" plays a campaign on the turn pipeline's own rules, in memory: each turn is read,
planned and resolved as the turn route does, its changes reduced, the world ticked and what it led to followed (quests,
pressures; no persistence, no narration, no model call). The policy rests when hurt, eats or buys food when hungry,
takes every quest offered and does it (walks to its places, or its stage's first way: the creature, the person, the
place), fights what the world holds, breaks away when losing, and otherwise wanders. ``simulate`` returns the
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
    fights_won: int = 0
    defeats: int = 0
    low_hp_turns: int = 0
    starving_turns: int = 0
    unplanned: int = 0
    commands: dict[str, int] = field(default_factory=dict)
    fights: dict[str, dict[str, int]] = field(default_factory=dict)  # by foe: how each fight ended


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


def _lodging(session: Mapping[str, Any], place_id: str) -> str:
    """The name of someone here who lets rooms ("" when no one does)."""
    world = _world(session)
    for provider_id, offers in sorted(_d(world.get("offers")).items()):
        person = _d(_d(world.get("npcs")).get(provider_id))
        if _s(person.get("location_id")) == place_id and any(
                _s(_d(offer).get("service_kind") or _d(offer).get("kind")) in {"lodging", "room"} for offer in _l(offers)):
            return _s(person.get("name"))
    return ""


def _command(session: Mapping[str, Any], turn: int) -> str:
    """The reasonable player's next command."""
    simulation = _d(session.get("simulation_state"))
    hp, max_hp = _hp(session)
    if _d(simulation.get("combat_state")).get("active") is True:
        return "I break away and flee." if hp < max_hp * 0.25 else "attack"
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
        keeper = _lodging(session, _here(session))
        if keeper and _purse(session) >= 50:
            return f"I rent a room for the night from {keeper}."
        if not keeper:
            return "I make camp and sleep for the night."
        step = _path_to(session, {place for place in _d(_world(session).get("locations")) if not _lodging(session, place)})
        if step:
            return f"go to {_name(session, step)}"
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
        ways = _l(_d(steps[stage]).get("any_of")) or [_l(_d(steps[stage]).get("all_of") or _d(steps[stage]).get("conditions"))]
        condition = _d((_l(ways[0]) or [{}])[0] if isinstance(ways[0], list) else ways[0])
        if condition.get("defeat"):
            from app.apps.rpg.rules.combat.campaign_mechanics import campaign_creature_definition

            creature = _d(campaign_creature_definition(simulation, _s(condition["defeat"])))
            if _s(creature.get("name")):
                return f"I attack the {_s(creature.get('name'))}."
        elif condition.get("talk"):
            person = _d(_d(_world(session).get("npcs")).get(_s(condition["talk"])))
            about = [_s(word) for word in (_l(condition.get("about")) or [condition.get("about")]) if _s(word)]
            if _s(person.get("location_id")) == _here(session):
                return f"I ask {_s(person.get('name'))} about the {about[0] if about else 'job'}."
            goals.add(_s(person.get("location_id")))
        elif condition.get("reach"):
            goals.add(_s(condition["reach"]))
    goals.discard("")
    if turn % 4 == 0:  # the world's creatures, met now and then
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
    from app.apps.rpg.rules.ability_use import known
    from app.apps.rpg.session.command_reading import read_command
    from app.apps.rpg.session.turn.planning import plan_action
    from app.apps.rpg.session.turn.resolution import resolve_turn
    from app.apps.rpg.session.turn.run import turn_consequences
    from app.apps.rpg.session.turn.world_tick import world_tick

    simulation = _d(session.get("simulation_state"))
    reading = read_command(simulation, text, _d(session.get("runtime_state")),
                           abilities=tuple((_s(row.get("ability_id")), _s(row.get("name"))) for row in known(session)))
    planned = plan_action(reading, fighting=_d(simulation.get("combat_state")).get("active") is True)
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
                                      turn_key=f"sim:{_d(document.get('state')).get('turn_count')}",
                                      turn=int(_d(document.get("state")).get("turn_count") or 0))
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
        "win_rate": round(tally.fights_won / tally.fights_started, 3) if tally.fights_started else None,
        "fights_started": tally.fights_started, "defeats": tally.defeats,
        "low_hp_share": round(tally.low_hp_turns / turns, 3), "starving_share": round(tally.starving_turns / turns, 3),
        "quests_completed": sum(1 for quest in quests if quest.get("status") == "completed"),
        "unplanned": tally.unplanned, "commands": dict(sorted(tally.commands.items(), key=lambda kv: -kv[1])[:8]),
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
        document, played = _turn(document, text)
        if not played:
            tally.unplanned += 1
            document, _ = _turn(document, "wait")
        combat = _d(_d(document.get("simulation_state")).get("combat_state"))
        if not fighting and combat.get("active") is True:
            tally.fights_started += 1
        if fighting and combat.get("active") is not True and combat.get("ended_reason") == "enemy_side_defeated":
            tally.fights_won += 1
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


def outside(report: Mapping[int, Mapping[str, Any]]) -> list[str]:
    """The bands a report breaks."""
    broken = []
    for turns, measures in report.items():
        for key, (low, high) in BANDS.get(turns, {}).items():
            value = measures.get(key)
            if value is not None and not low <= value <= high:
                broken.append(f"after {turns} turns, {key} {value} is outside {low}-{high}")
    return broken


__all__ = ["BANDS", "outside", "simulate"]
