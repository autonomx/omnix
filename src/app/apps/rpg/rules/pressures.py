"""The world's pressures, and what the hero does to them (RQ-5.4; docs/rpg/design/quests.md).

A pressure (the causal runtime's: danger on the roads, a failing ward) rises by itself each tick. Its ``levers`` say
what pushes it back: ``defeat:<creature id>`` for each such creature felled, ``quest:<quest id>`` when that quest is
completed; each moves the severity by its amount (``lower`` or ``raise``). When the pressure of the hero's region runs high (at least
``PRESSURE_QUEST_SEVERITY``) and no open quest answers it, a person whose work fits (a guard, a captain, a guild's)
who is with the hero offers one: defeat its creatures, then report back. Pure: it returns the changes.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import PressuresMoved, QuestOffered, QuestStatusChanged, StateChange
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.combat.campaign_mechanics import campaign_creature_definition
from app.apps.rpg.rules.quest.progress import victories
from app.apps.rpg.world.causal_runtime import pull_levers

PRESSURE_QUEST_SEVERITY = 60.0
PRESSURE_QUEST_REWARD = "10 silver"
HUNT_EASES = 20.0  # a pressure quest's hunt pushes its pressure back by at least this much
_FITTING = re.compile(r"\b(guard|guards|captain|watch|warden|guild|registrar|elder|mayor|sheriff|ranger|marshal)\b")
_OPEN = {"available", "active"}


def _runtime(simulation: Mapping[str, Any]) -> dict[str, Any]:
    return _d(simulation.get("causal_world_runtime"))


def _pressures(runtime: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_d(row) for row in _l(_d(runtime.get("pressure_plan")).get("pressures")) if _s(_d(row).get("pressure_id"))]


def _severity(runtime: Mapping[str, Any], pressure_id: str) -> float:
    cell = _d(_d(_d(runtime.get("state")).get("cells")).get(pressure_id))
    return float(_d(cell.get("values")).get("pressure_severity") or 0)


def _amount(lever: Mapping[str, Any]) -> float:
    return float(lever.get("amount") or 0) * (1 if _s(lever.get("effect")) == "raise" else -1)


def lever_pulls(simulation: Mapping[str, Any], applied: Sequence[StateChange]) -> tuple[list[StateChange], list[str]]:
    """The pressures this turn's deeds moved (creatures felled, quests completed), and how to say it."""
    runtime = _runtime(simulation)
    pressures = _pressures(runtime)
    if not pressures:
        return [], []
    felled = victories(applied)
    completed = {change.quest_id for change in applied
                 if isinstance(change, QuestStatusChanged) and change.status == "completed"}
    pulls: dict[str, float] = {}
    for pressure in pressures:
        for lever in map(_d, _l(pressure.get("levers"))):
            kind, _, subject = _s(lever.get("action")).partition(":")
            times = felled.get(subject, 0) if kind == "defeat" else int(subject in completed) if kind == "quest" else 0
            if times:
                key = _s(pressure["pressure_id"])
                pulls[key] = pulls.get(key, 0.0) + _amount(lever) * times
    moved, event = pull_levers(runtime, pulls, cause="hero")
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
    """A side quest a high pressure of the hero's region raises: offered by a fitting person who is with the hero,
    one open for each pressure."""
    runtime = _runtime(simulation)
    world_model = _d(simulation.get("world_model"))
    location = routines.hero_location(simulation)
    here = _region(world_model, location)
    if not here or not _pressures(runtime):
        return [], []
    quests = [_d(row) for row in _l(_d(simulation.get("quest_state")).get("quests"))]
    statuses = _d(runtime.get("pressure_statuses"))
    people = _d(world_model.get("npcs"))
    companions = set(routines.companions(simulation))
    present = sorted(set(routines.present_at(simulation, location, routines.clock(simulation))) - companions)
    fitting = [npc_id for npc_id in present if _FITTING.search(_s(_d(people.get(npc_id)).get("role")).casefold())]
    if not fitting:
        return [], []
    for pressure in (row for row in _pressures(runtime) if _pressure_region(world_model, row) == here):
        pressure_id = _s(pressure["pressure_id"])
        if (_s(statuses.get(pressure_id)) or "active") == "resolved" or _severity(runtime, pressure_id) < PRESSURE_QUEST_SEVERITY:
            continue
        if any(_s(quest.get("pressure_id")) == pressure_id and _s(quest.get("status")) in _OPEN for quest in quests):
            continue
        hunts = [(lever, campaign_creature_definition(simulation, _s(lever.get("action")).partition(":")[2]))
                 for lever in map(_d, _l(pressure.get("levers")))
                 if _s(lever.get("action")).startswith("defeat:") and _amount(lever) < 0]
        hunts = [(lever, creature) for lever, creature in hunts if creature]
        if not hunts:
            continue
        giver = fitting[0]
        # The hunt fits the hero: the strongest of its creatures up to two levels above theirs, else the weakest.
        level = int(_d(simulation.get("player_state")).get("level") or 1)
        ranked = sorted(hunts, key=lambda hunt: int(hunt[1].get("level") or 1))
        lever, creature = next((hunt for hunt in reversed(ranked) if int(hunt[1].get("level") or 1) <= level + 2),
                               ranked[0])
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
            "source": "pressure"})
        return [offer], [f'{giver_name} asks for your help: "{title}". {steps[0]["summary"]}.']
    return [], []


__all__ = ["HUNT_EASES", "PRESSURE_QUEST_REWARD", "PRESSURE_QUEST_SEVERITY", "lever_pulls", "pressure_offers"]
