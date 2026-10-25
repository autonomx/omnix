"""The world's pressures, and what the hero does to them (RQ-5.4; docs/rpg/design/quests.md).

A pressure (the causal runtime's: danger on the roads, a failing ward) rises by itself each tick. Its ``levers`` say
what pushes it back: ``defeat:<creature id>`` for each such creature felled, ``quest:<quest id>`` when that quest is
completed; each moves the severity by its amount (``lower`` or ``raise``). When a pressure runs high (at least
``PRESSURE_QUEST_SEVERITY``), a person whose work fits (a guard, a captain, a guild's) who is with the hero offers a
quest against it, one at a time (the hero's own region's first): defeat its creatures, then report back. And a
dangerous road is dangerous: a journey to a place where no one lives, in a region whose pressure has creatures, may
meet one of them (``road_encounter``; encounters.md). Pure: it returns the changes.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable, Mapping, Sequence

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import PressuresMoved, QuestOffered, QuestStatusChanged, StateChange
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.combat.campaign_mechanics import campaign_creature_definition
from app.apps.rpg.rules.quest.progress import victories
from app.apps.rpg.foundation.state import access as _sections

# The causal runtime's pull: (the runtime, each pressure's pull) -> (the runtime as it leaves it, its event or None).
Pull = Callable[[Mapping[str, Any], Mapping[str, float]], tuple[dict[str, Any], Any]]
PRESSURE_QUEST_SEVERITY = 60.0
PRESSURE_QUEST_REWARD = "10 silver"
PRESSURE_QUEST_EVERY = 24 * 60  # the world's troubles raise a new side quest at most once a day (on its clock)
HUNT_EASES = 20.0  # a pressure quest's hunt pushes its pressure back by at least this much
_UNIQUE = {"boss", "legendary", "mythic", "extreme", "deadly"}  # a world's boss is no side quest's quarry
_FITTING = re.compile(r"\b(guard|guards|captain|watch|warden|guild|registrar|elder|mayor|sheriff|ranger|marshal)\b")
_OPEN = {"available", "active"}
ENCOUNTER_FLOOR = 40.0  # above this severity a region's roads hold danger: the chance is the severity above it, in %


def _runtime(simulation: Mapping[str, Any]) -> dict[str, Any]:
    return _d(simulation.get("causal_world_runtime"))


def _pressures(runtime: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_d(row) for row in _l(_d(runtime.get("pressure_plan")).get("pressures")) if _s(_d(row).get("pressure_id"))]


def _severity(runtime: Mapping[str, Any], pressure_id: str) -> float:
    cell = _d(_d(_d(runtime.get("state")).get("cells")).get(pressure_id))
    return float(_d(cell.get("values")).get("pressure_severity") or 0)


def _amount(lever: Mapping[str, Any]) -> float:
    return float(lever.get("amount") or 0) * (1 if _s(lever.get("effect")) == "raise" else -1)


def lever_pulls(simulation: Mapping[str, Any], applied: Sequence[StateChange], *, pull: Pull
                ) -> tuple[list[StateChange], list[str]]:
    """The pressures this turn's deeds moved, and how to say it: creatures felled push back the pressure of the region
    they fell in (a wolf killed in one march does not make another's roads safe), a quest completed its own.
    ``pull(runtime, pulls)`` moves them in the causal runtime (``world.causal_runtime.pull_levers``, the turn's to
    give: the rules read the world's state, they do not run it)."""
    runtime = _runtime(simulation)
    pressures = _pressures(runtime)
    if not pressures:
        return [], []
    world_model = _d(_sections.world_model_of(simulation))
    here = _region(world_model, routines.hero_location(simulation))
    felled = victories(applied)
    completed = {change.quest_id for change in applied
                 if isinstance(change, QuestStatusChanged) and change.status == "completed"}
    pulls: dict[str, float] = {}
    for pressure in pressures:
        for lever in map(_d, _l(pressure.get("levers"))):
            kind, _, subject = _s(lever.get("action")).partition(":")
            local = _pressure_region(world_model, pressure) in {here, ""}
            times = (felled.get(subject, 0) if kind == "defeat" and local
                     else int(subject in completed) if kind == "quest" else 0)
            if times:
                key = _s(pressure["pressure_id"])
                pulls[key] = pulls.get(key, 0.0) + _amount(lever) * times
    moved, event = pull(runtime, pulls)
    if event is None:
        return [], []
    names = {_s(row["pressure_id"]): _s(row.get("name")) or _s(row["pressure_id"]) for row in pressures}
    thresholds = {_s(row["pressure_id"]): float(row.get("resolution_threshold") or 15) for row in pressures}
    moves, lines = [], []
    for pressure_id, delta in sorted(pulls.items()):
        before, after = _severity(runtime, pressure_id), _severity(moved, pressure_id)
        moves.append({"pressure_id": pressure_id, "severity_before": before, "severity_after": after})
        name = names[pressure_id]
        lines.append(f"{name}: it is nearly over." if after <= thresholds[pressure_id] and delta < 0
                     else f"{name}: it eases." if delta < 0 else f"{name}: it grows worse.")
    return [PressuresMoved(moves=moves, runtime=moved, cause=event.event_id)], lines


def _plural(name: str) -> str:
    if name.endswith("f"):
        return name[:-1] + "ves"
    return name + ("es" if name.endswith(("s", "x", "ch", "sh")) else "s")


def _region(world_model: Mapping[str, Any], location_id: str) -> str:
    return _s(_d(_d(world_model.get("locations")).get(location_id)).get("region_id"))


def _pressure_region(world_model: Mapping[str, Any], pressure: Mapping[str, Any]) -> str:
    authored = {_s(_d(row).get("pressure_id")): _s(_d(row).get("region_id")) for row in _l(world_model.get("pressures"))}
    return authored.get(_s(pressure.get("pressure_id"))) or _s(_d(pressure.get("next_tick_delta")).get("target_id"))


def pressure_offers(simulation: Mapping[str, Any]) -> tuple[list[StateChange], list[str]]:
    """A side quest a high pressure raises: offered by a fitting person who is with the hero, one from the world's
    pressures open at a time and at most one a day, the pressure of the hero's region first, else the most severe
    elsewhere."""
    runtime = _runtime(simulation)
    world_model = _d(_sections.world_model_of(simulation))
    location = routines.hero_location(simulation)
    here = _region(world_model, location)
    if not here or not _pressures(runtime):
        return [], []
    quests = [_d(row) for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))]
    statuses = _d(runtime.get("pressure_statuses"))
    people = _d(world_model.get("npcs"))
    companions = set(routines.companions(simulation))
    present = sorted(set(routines.present_at(simulation, location, routines.clock(simulation))) - companions)
    fitting = [npc_id for npc_id in present if _FITTING.search(_s(_d(people.get(npc_id)).get("role")).casefold())]
    if not fitting or any(_s(quest.get("pressure_id")) and _s(quest.get("status")) in _OPEN for quest in quests):
        return [], []
    now = routines.clock(simulation)
    last = max((int(quest.get("offered_at_minute") or 0) for quest in quests if _s(quest.get("pressure_id"))), default=None)
    if last is not None and now - last < PRESSURE_QUEST_EVERY:
        return [], []
    ordered = sorted(_pressures(runtime), key=lambda row: (_pressure_region(world_model, row) != here,
                                                           -_severity(runtime, _s(row["pressure_id"]))))
    for pressure in ordered:
        pressure_id = _s(pressure["pressure_id"])
        if (_s(statuses.get(pressure_id)) or "active") == "resolved" or _severity(runtime, pressure_id) < PRESSURE_QUEST_SEVERITY:
            continue
        hunts = [(lever, campaign_creature_definition(simulation, _s(lever.get("action")).partition(":")[2]))
                 for lever in map(_d, _l(pressure.get("levers")))
                 if _s(lever.get("action")).startswith("defeat:") and _amount(lever) < 0]
        # The hunt fits the hero: the strongest of its creatures below their level, else one of it (none: no offer
        # yet); never the world's boss.
        level = int(_d(_sections.player_state_of(simulation)).get("level") or 1)
        hunts = sorted(((lever, creature) for lever, creature in hunts if creature
                        and _s(creature.get("threat")).casefold() not in _UNIQUE
                        and int(creature.get("level") or 1) <= level), key=lambda hunt: int(hunt[1].get("level") or 1))
        weaker = [hunt for hunt in hunts if int(hunt[1].get("level") or 1) < level]
        if not hunts:
            continue
        giver = fitting[0]
        lever, creature = (weaker or hunts)[-1]
        creature_id = _s(lever["action"]).partition(":")[2]
        count = min(3, max(1, math.ceil(HUNT_EASES / abs(_amount(lever)))))
        creature_name = _s(creature.get("name")) or creature_id
        hunted = creature_name if count == 1 else f"{count} {_plural(creature_name)}"
        giver_name = _s(_d(people.get(giver)).get("name")) or giver
        title = _s(pressure.get("name")) or pressure_id
        number = 1 + sum(1 for quest in quests if _s(quest.get("pressure_id")) == pressure_id)
        quest_id = f"quest:pressure:{pressure_id.removeprefix('pressure:')}:{number}"
        steps = [{"id": "hunt", "summary": f"Defeat {hunted}", "all_of": [{"defeat": creature_id, "count": count}]},
                 {"id": "report", "summary": f"Tell {giver_name} it is done", "all_of": [{"talk": giver}]}]
        offer = QuestOffered(quest_id=quest_id, npc_id=giver, quest={
            "id": quest_id, "quest_id": quest_id, "title": title, "status": "available", "tier": "side",
            "objective": steps[0]["summary"], "hook": _s(pressure.get("summary")), "rewards": [PRESSURE_QUEST_REWARD],
            "locations": [], "visited_locations": [], "steps": steps, "giver_id": giver, "pressure_id": pressure_id,
            "offered_at_minute": now, "source": "pressure"})
        return [offer], [f'{giver_name} asks for your help: "{title}". {steps[0]["summary"]}.']
    return [], []


def road_encounter(simulation: Mapping[str, Any], *, turn_key: str) -> str:
    """The creature that bars the hero's way where they have just arrived (its id), or "": only where no one lives,
    in a region whose pressure is above ``ENCOUNTER_FLOOR``, on a seeded chance of the severity above it; one of the
    pressure's creatures no stronger than a level above the hero, never the world's boss."""
    from app.apps.rpg.rules.combat.runtime_core import deterministic_roll

    world_model = _d(_sections.world_model_of(simulation))
    here = routines.hero_location(simulation)
    region = _region(world_model, here)
    if not region or not routines.is_wild(simulation, here):
        return ""
    runtime = _runtime(simulation)
    level = int(_d(_sections.player_state_of(simulation)).get("level") or 1)
    for pressure in _pressures(runtime):
        pressure_id = _s(pressure["pressure_id"])
        severity = _severity(runtime, pressure_id)
        if _pressure_region(world_model, pressure) != region or severity <= ENCOUNTER_FLOOR:
            continue
        if deterministic_roll(f"encounter|{pressure_id}|{here}|{turn_key}", 1, 100) > severity - ENCOUNTER_FLOOR:
            continue
        foes = sorted(subject for kind, _, subject in (_s(_d(lever).get("action")).partition(":")
                                                       for lever in _l(pressure.get("levers")))
                      if kind == "defeat" and (creature := campaign_creature_definition(simulation, subject))
                      and _s(creature.get("threat")).casefold() not in _UNIQUE
                      and int(creature.get("level") or 1) <= level + 1)
        if foes:
            return foes[deterministic_roll(f"encounter.foe|{pressure_id}|{turn_key}", 1, len(foes)) - 1]
    return ""


__all__ = ["ENCOUNTER_FLOOR", "HUNT_EASES", "PRESSURE_QUEST_REWARD", "PRESSURE_QUEST_SEVERITY", "lever_pulls",
           "pressure_offers", "road_encounter"]
