"""Where the world's people are through the day (RQ-2.7, roadmap §4.5).

A world authors each named person's day (``canon.routines``: from which hour to which, where, doing what), and the
launch compiles it into the world model. The day moves people on the campaign's one clock. Away from the hero, a
person is where their day puts them at the hour. Someone in the scene with the hero stays until their day turns to
its next part (the clock crosses into another step of it, or a whole day goes by), and the hero sees them go; so
an opening, a conversation or a story keeps the people in it. A person with no routine stays where they are (the
``npcs`` section's index, or where the world put them), and the hero's companions are wherever the hero is. Who is
present at a place is who is there. Pure: the world tick records the whereabouts as changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s

MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True)
class Whereabouts:
    location_id: str
    activity: str = ""


def _covers(step: Mapping[str, Any], hour: float) -> bool:
    start, end = float(step.get("from_hour") or 0), float(step.get("to_hour") or 24)
    return start <= hour < end if start < end else hour >= start or hour < end  # a step past midnight wraps


def _step(schedule: list[Any], minute: int) -> int | None:
    """The part of the day a schedule is in at ``minute``."""
    hour = (int(minute) % MINUTES_PER_DAY) / 60
    return next((index for index, step in enumerate(schedule) if _covers(_d(step), hour)), None)


def _schedules(world_model: Mapping[str, Any]) -> dict[str, list[Any]]:
    places = _d(world_model.get("locations"))
    return {_s(_d(routine).get("npc_id")): [step for step in _l(_d(routine).get("schedule"))
                                            if _s(_d(step).get("location_id")) in places]
            for routine in _l(world_model.get("routines")) if _s(_d(routine).get("npc_id"))}


def companions(simulation: Mapping[str, Any]) -> list[str]:
    party = _d(_d(simulation.get("player_state")).get("party_state"))
    return [npc for npc in (_s(_d(companion).get("npc_id")) for companion in _l(party.get("companions"))) if npc]


def visited(simulation: Mapping[str, Any]) -> list[str]:
    """The places the hero has been."""
    return [_s(place) for place in _l(simulation.get("visited_locations")) if _s(place)]


def hero_location(simulation: Mapping[str, Any]) -> str:
    return _s(_d(simulation.get("player_state")).get("location_id")) or _s(simulation.get("location_id"))


def is_wild(simulation: Mapping[str, Any], location_id: str = "") -> bool:
    """Whether no one lives at the place (the hero's, by default): where the world's creatures are met (encounters.md)."""
    here = location_id or hero_location(simulation)
    people = _d(_d(simulation.get("world_model")).get("npcs"))
    return bool(here) and not any(_s(_d(person).get("location_id")) == here for person in people.values())


def clock(simulation: Mapping[str, Any]) -> int:
    """The campaign clock's absolute minutes (the simulation's environment)."""
    return int(_d(simulation.get("environment")).get("absolute_minutes") or 0)


def whereabouts(simulation: Mapping[str, Any], minute: int, *, since: int | None = None,
                hero_at: str = "") -> dict[str, Whereabouts]:
    """Where each of the world's people is at ``minute``, the clock having moved there from ``since`` (by default it
    has not moved), with the hero at ``hero_at`` (by default where they stand). Empty for a campaign whose world
    names no one.

    Away from the hero, a person is where their day puts them. Someone in the scene with the hero (the presence
    recorded where the hero is) stays there until their day turns to its next part, and then goes. The hero's
    companions are with the hero.
    """
    world = _d(simulation.get("world_model"))
    people, index = _d(world.get("npcs")), _d(simulation.get("npc_index"))
    if not people:
        return {}
    since = int(minute) if since is None else int(since)
    schedules = _schedules(world)
    listed = {_s(_d(npc).get("id")): place_id for place_id, place in _d(world.get("locations")).items()
              for npc in _l(_d(place).get("present_npcs")) if _s(_d(npc).get("id"))}  # where the world put them
    party = set(companions(simulation))
    here = hero_at or hero_location(simulation)
    scene_at, scene = present_now(simulation)
    with_hero = set(scene) if scene_at and scene_at == here else set()
    found: dict[str, Whereabouts] = {}
    for npc_id, person in people.items():
        kept = _d(index.get(npc_id))
        if npc_id in party:
            found[npc_id] = Whereabouts(here)
            continue
        schedule = schedules.get(npc_id) or []
        now = _step(schedule, minute)
        step = _d(schedule[now]) if now is not None else {}
        turned = now is not None and (minute - since >= MINUTES_PER_DAY or now != _step(schedule, since))
        if npc_id in with_hero and not turned:
            # In the scene with the hero: they stay, doing what their day says if this is where it has them.
            activity = _s(step.get("activity")) if _s(step.get("location_id")) == here else _s(kept.get("activity"))
            found[npc_id] = Whereabouts(here, activity)
        elif step:
            found[npc_id] = Whereabouts(_s(step.get("location_id")), _s(step.get("activity")))
        else:
            found[npc_id] = Whereabouts(_s(kept.get("location_id")) or _s(_d(person).get("location_id"))
                                        or listed.get(npc_id, ""), _s(kept.get("activity")))
    return found


def present_at(simulation: Mapping[str, Any], location_id: str, minute: int, *, since: int | None = None) -> list[str]:
    """Who is at a place at ``minute`` when the hero is there: the people there, then the hero's companions."""
    found = whereabouts(simulation, minute, since=since, hero_at=location_id)
    party = companions(simulation)
    there = [npc_id for npc_id, where in found.items() if where.location_id == location_id and npc_id not in party]
    return there + [npc_id for npc_id in party if npc_id in found]


def described(simulation: Mapping[str, Any], npc_ids: list[str], minute: int, *, since: int | None = None,
              hero_at: str = "") -> list[str]:
    """The people named as the hero sees them: "Bran (keeping the tavern)"."""
    people = {**_d(simulation.get("npc_index")), **_d(_d(simulation.get("world_model")).get("npcs"))}
    found = whereabouts(simulation, minute, since=since, hero_at=hero_at)
    seen = []
    for npc_id in npc_ids:
        name = _s(_d(people.get(npc_id)).get("name"))
        activity = found[npc_id].activity if npc_id in found else ""
        if name:
            seen.append(f"{name} ({activity})" if activity else name)
    return seen


def moves(simulation: Mapping[str, Any], minute: int, *, since: int) -> dict[str, Whereabouts]:
    """The people whose whereabouts at ``minute`` differ from what the index last recorded."""
    index = _d(simulation.get("npc_index"))
    return {npc_id: where for npc_id, where in whereabouts(simulation, minute, since=since).items()
            if where.location_id and (where.location_id, where.activity)
            != (_s(_d(index.get(npc_id)).get("location_id")), _s(_d(index.get(npc_id)).get("activity")))}


def present_now(simulation: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Where the presence last recorded is (an older campaign's names no place: the hero's), and who it names."""
    presence = _d(simulation.get("present_npc_state"))
    return (_s(presence.get("location_id")) or hero_location(simulation),
            [_s(npc) for npc in _l(presence.get("present_npc_ids")) if _s(npc)])


def comings_and_goings(world_model: Mapping[str, Any], before: list[str], after: list[str],
                       moved_to: Mapping[str, Whereabouts]) -> list[str]:
    """What the hero sees of the people around them as time passes: who leaves (and for where), who arrives."""
    people, places = _d(world_model.get("npcs")), _d(world_model.get("locations"))

    def name(npc_id: str) -> str:
        return _s(_d(people.get(npc_id)).get("name")) or npc_id

    lines = []
    for npc_id in before:
        if npc_id not in after:
            where = moved_to.get(npc_id)
            place = _s(_d(places.get(where.location_id)).get("name")) if where else ""
            lines.append(f"{name(npc_id)} leaves for {place}." if place else f"{name(npc_id)} leaves.")
    for npc_id in after:
        if npc_id not in before:
            activity = moved_to[npc_id].activity if npc_id in moved_to else ""
            lines.append(f"{name(npc_id)} arrives, {activity}." if activity else f"{name(npc_id)} arrives.")
    return lines


__all__ = ["MINUTES_PER_DAY", "Whereabouts", "clock", "comings_and_goings", "companions", "described", "hero_location", "is_wild",
           "moves", "present_at", "present_now", "whereabouts"]
