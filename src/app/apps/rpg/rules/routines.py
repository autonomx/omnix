"""Where the world's people are through the day (RQ-2.7, roadmap §4.5).

A world authors each named person's day (``canon.routines``: from which hour to which, where, doing what), and the
launch compiles it into the world model. The day moves people on the campaign's one clock. Away from the hero, a
person is where their day puts them at the hour. Someone in the scene with the hero stays until their day turns to
its next part (the clock crosses into another step of it, or a whole day goes by), and the hero sees them go; so
an opening, a conversation or a story keeps the people in it. A person with no routine stays where they are (the
``npcs`` section's index, or where the world put them), and the hero's companions are wherever the hero is. Who is
present at a place is who is there. Pure: the world tick records the whereabouts as changes.

People act on their goals (evolution roadmap EV-4). A goal the routines author may hold **beats**, steps toward it
taken in order: each, once its condition holds (facts, a place the hero has been, the campaign's day), is reached
with its chance on each day the clock crosses, at most ``BEATS_PER_DAY`` a day, by a roll seeded by the campaign, the
day and the beat (``daily_beats``); the game master may bring one forward (``fold_beat``). A beat reached is
``BeatAdvanced``: the facts it sets (not yet known to the hero), the place it takes its person to (they keep to it
from then on, or are gone), and the word that goes about (``rules/rumours.py``), told at once when the hero is there.
A beat never takes a protected person away (a companion, the giver of an open quest, anyone its steps need): it waits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import FactLearned, StateChange
from app.apps.rpg.rules.consequences import moved_people

MINUTES_PER_DAY = 24 * 60
BEATS_PER_DAY = 3
GAME_MASTER_GOAL = "game-master"  # where a person the game master moves is kept, as a beat's move is
DAYS_AT_ONCE = 3  # the days of beats one stretch of time away rolls (a week's sleep is not a week of story)


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
    party = _d(_sections.party_state_of(_d(_sections.player_state_of(simulation))))
    return [npc for npc in (_s(_d(companion).get("npc_id")) for companion in _l(party.get("companions"))) if npc]


def visited(simulation: Mapping[str, Any]) -> list[str]:
    """The places the hero has been."""
    return [_s(place) for place in _l(simulation.get("visited_locations")) if _s(place)]


def hero_location(simulation: Mapping[str, Any]) -> str:
    return _s(_d(_sections.player_state_of(simulation)).get("location_id")) or _s(simulation.get("location_id"))


def is_wild(simulation: Mapping[str, Any], location_id: str = "") -> bool:
    """Whether no one lives at the place (the hero's, by default): where the world's creatures are met (encounters.md)."""
    here = location_id or hero_location(simulation)
    people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
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
    world = _d(_sections.world_model_of(simulation))
    people, index = _d(world.get("npcs")), _d(_sections.npc_index_of(simulation))
    if not people:
        return {}
    since = int(minute) if since is None else int(since)
    schedules = _schedules(world)
    listed = {_s(_d(npc).get("id")): place_id for place_id, place in _d(world.get("locations")).items()
              for npc in _l(_d(place).get("present_npcs")) if _s(_d(npc).get("id"))}  # where the world put them
    party = set(companions(simulation))
    moved = {**moved_people(simulation),  # a day the world's facts replaced (rules/consequences.py, EV-1)
             **beat_moves(simulation)}  # and one a beat of their goals did (EV-4)
    here = hero_at or hero_location(simulation)
    scene_at, scene = present_now(simulation)
    with_hero = set(scene) if scene_at and scene_at == here else set()
    found: dict[str, Whereabouts] = {}
    for npc_id, person in people.items():
        kept = _d(index.get(npc_id))
        if npc_id in party:
            found[npc_id] = Whereabouts(here)
            continue
        if npc_id in moved:  # where the world's facts put them; gone, nowhere
            found[npc_id] = Whereabouts(*moved[npc_id])
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


def fold_move(document: Mapping[str, Any], payload: Mapping[str, Any]):
    """A person the game master moves (EV-0): one of the world's, to one of its places; never a protected person (a
    companion, the giver of an open quest, anyone an open quest's step needs), within the day's limit."""
    from app.apps.rpg.foundation.state.changes import BeatAdvanced, PersonWhereabouts, WhereaboutsChanged
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.direction import allows, counted, protected

    simulation = _d(_sections.simulation_state_of(document))
    world = _d(_sections.world_model_of(simulation))
    npc_id, place = _s(payload.get("npc_id")), _s(payload.get("location_id"))
    if npc_id not in _d(world.get("npcs")) or place not in _d(world.get("locations")):
        return refused("no such person or place in this world")
    if npc_id in protected(simulation):
        return refused("a protected person moves only with the hero")
    limit = allows(simulation, "move")
    if limit:
        return refused(limit)
    # Kept as a beat's move is (``beat_moves``), so the person's day does not take them back at the next hour.
    now = clock(simulation)
    return Folded([WhereaboutsChanged(people=(PersonWhereabouts(npc_id=npc_id, location_id=place,
                                                                activity=_s(payload.get("activity"))),)),
                   BeatAdvanced(person_id=npc_id, goal_id=GAME_MASTER_GOAL, beat=f"moved:{now}", location_id=place,
                                activity=_s(payload.get("activity")), source="game_master", at_minute=now),
                   counted(simulation, "move")])


def goals(simulation: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Each person's goals with beats, as the routines author them: (person, goal), in the routines' order."""
    world = _d(_sections.world_model_of(simulation))
    people = _d(world.get("npcs"))
    return [(_s(_d(routine).get("npc_id")), _d(goal)) for routine in _l(world.get("routines"))
            if _s(_d(routine).get("npc_id")) in people
            for goal in _l(_d(routine).get("goals")) if _s(_d(goal).get("goal_id")) and _l(_d(goal).get("beats"))]


def beat_address(npc_id: str, goal_id: str, beat_id: str) -> str:
    return f"beat:{npc_id}:{goal_id}:{beat_id}"


def beat_by_address(simulation: Mapping[str, Any], address: str) -> dict[str, Any]:
    """The authored beat an address names ({} when none does)."""
    for npc_id, goal in goals(simulation):
        for beat in map(_d, _l(goal.get("beats"))):
            if beat_address(npc_id, _s(goal.get("goal_id")), _s(beat.get("id"))) == address:
                return beat
    return {}


def reached(simulation: Mapping[str, Any], npc_id: str, goal_id: str) -> list[str]:
    """The beats of a person's goal reached so far, in order."""
    held = _d(_d(_d(_sections.goal_state_of(simulation)).get(npc_id)).get(goal_id))
    return [_s(beat) for beat in _l(held.get("beats")) if _s(beat)]


def beat_moves(simulation: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """Where beats (and the game master) have taken people, the latest by when: (place, activity); gone, ("", "")."""
    found: dict[str, tuple[int, str, str]] = {}
    for npc_id, row in _d(_sections.goal_state_of(simulation)).items():
        for held in map(_d, _d(row).values()):
            if _s(held.get("location_id")) or held.get("gone") is True:
                at = int(held.get("at") if held.get("at") is not None else int(held.get("day") or 0) * MINUTES_PER_DAY)
                if str(npc_id) not in found or at >= found[str(npc_id)][0]:
                    found[str(npc_id)] = (at, _s(held.get("location_id")), _s(held.get("activity")))
    return {npc_id: (place, activity) for npc_id, (_, place, activity) in found.items()}


def next_beat(simulation: Mapping[str, Any], npc_id: str, goal: Mapping[str, Any], *,
              also: Iterable[str] = ()) -> dict[str, Any]:
    """The beat a person's goal comes to next ({} when all are reached; ``also``: beats reached since)."""
    done = {*reached(simulation, npc_id, _s(goal.get("goal_id"))), *also}
    return next((_d(beat) for beat in _l(goal.get("beats")) if _s(_d(beat).get("id")) not in done), {})


def _ready(simulation: Mapping[str, Any], npc_id: str, beat: Mapping[str, Any], day: int, *,
           since: Mapping[str, Any] | None = None) -> bool:
    """Whether a beat's condition holds on ``day`` (``since``: facts set since, by id and value)."""
    from app.apps.rpg.rules.consequences import world_facts
    from app.apps.rpg.rules.direction import protected

    facts = {**world_facts(simulation), **{fact: {"value": value} for fact, value in _d(since).items()}}
    if day < int(beat.get("after_day") or 0):
        return False
    if any(fact not in facts or facts[fact].get("value") != value for fact, value in _d(beat.get("when")).items()):
        return False
    if _s(beat.get("visited")) and _s(beat.get("visited")) not in visited(simulation):
        return False
    return not (isinstance(beat.get("move"), Mapping) and npc_id in protected(simulation))


def _home(simulation: Mapping[str, Any], npc_id: str) -> str:
    where = whereabouts(simulation, clock(simulation)).get(npc_id)
    return where.location_id if where else ""


def advance(simulation: Mapping[str, Any], npc_id: str, goal: Mapping[str, Any], beat: Mapping[str, Any], *,
            source: str, at_minute: int | None = None) -> tuple[list[StateChange], list[str]]:
    """A person reaches ``beat``: its changes, and what the hero sees of it when they are where it is told (the word
    heard, and the facts it set known)."""
    from app.apps.rpg.foundation.state.changes import BeatAdvanced, FactSet, RumourHeard
    from app.apps.rpg.rules.rumours import spread

    goal_id, beat_id = _s(goal.get("goal_id")), _s(beat.get("id"))
    move = _d(beat.get("move")) if isinstance(beat.get("move"), Mapping) else None
    places = [_s(place) for place in _l(beat.get("told_at"))] or [_home(simulation, npc_id), _s(goal.get("location_id"))]
    changes: list[StateChange] = [BeatAdvanced(
        person_id=npc_id, goal_id=goal_id, beat=beat_id, source=source, at_minute=at_minute,
        **({"location_id": _s(move.get("location")), "activity": _s(move.get("activity")),
            "gone": not _s(move.get("location"))} if move is not None else {}))]
    from app.apps.rpg.rules.consequences import world_facts

    held = world_facts(simulation)
    facts = [FactSet(fact_id=_s(fact.get("fact")), value=fact.get("value", True), source=source, known=False,
                     told=_s(fact.get("told")))
             for fact in map(_d, _l(beat.get("sets"))) if _s(fact.get("fact"))
             and _d(held.get(_s(fact.get("fact")))).get("value", object()) != fact.get("value", True)]  # not again
    changes += facts
    address = beat_address(npc_id, goal_id, beat_id)
    word = spread(address, _s(beat.get("rumour")), places, text_id=address, source=source) if _s(beat.get("rumour")) else []
    changes += word
    if not any(rumour.place_id == hero_location(simulation) for rumour in word):
        return changes, []
    # The hero is there when it happens: they hear it (every place's copy), and know what it set.
    changes += [RumourHeard(rumour_id=rumour.rumour_id, source="seen") for rumour in word]
    changes += [FactLearned(fact_id=fact.fact_id, source="seen") for fact in facts]
    return changes, [word[0].text]


def daily_beats(simulation: Mapping[str, Any], *, before: int, after: int) -> tuple[list[StateChange], list[str]]:
    """The beats people reach on the days the clock crosses from minute ``before`` to ``after`` (the last
    ``DAYS_AT_ONCE`` of them, ``BEATS_PER_DAY`` a day): each goal's next beat that is ready, by its chance, rolled once
    a day by a stream seeded by the campaign, the day and the beat."""
    from app.apps.rpg.foundation.core.determinism import rng_for, stable_sub_index
    from app.apps.rpg.foundation.state.changes import FactSet

    first, last = before // MINUTES_PER_DAY + 1, after // MINUTES_PER_DAY
    seed = int(_sections.rng_seed_of(simulation) or 0) % 2**64
    changes: list[StateChange] = []
    lines: list[str] = []
    since: dict[str, Any] = {}  # the facts the beats of earlier days set: a later beat may wait on them
    done: dict[tuple[str, str], list[str]] = {}
    for day in range(max(first, last - DAYS_AT_ONCE + 1), last + 1):
        taken = 0
        for npc_id, goal in goals(simulation):
            if taken >= BEATS_PER_DAY:
                break
            key = (npc_id, _s(goal.get("goal_id")))
            if done.get(key) and done[key][-1].startswith(f"{day}:"):
                continue  # one beat of a goal a day
            beat = next_beat(simulation, npc_id, goal, also=[beat_id.partition(":")[2] for beat_id in done.get(key, ())])
            if not beat or not _ready(simulation, npc_id, beat, day, since=since):
                continue
            address = beat_address(npc_id, _s(goal.get("goal_id")), _s(beat.get("id")))
            chance = float(beat["chance"]) if beat.get("chance") is not None else 0.5
            if rng_for(seed, day, "goal_beat", stable_sub_index(address)).random() >= chance:
                continue
            made, said = advance(simulation, npc_id, goal, beat, source=f"day:{day}", at_minute=day * MINUTES_PER_DAY)
            since.update({change.fact_id: change.value for change in made if isinstance(change, FactSet)})
            done.setdefault(key, []).append(f"{day}:{_s(beat.get('id'))}")
            changes += made
            lines += said
            taken += 1
    return changes, lines


def fold_beat(document: Mapping[str, Any], payload: Mapping[str, Any]):
    """A beat the game master brings forward (EV-0, EV-4): the next of a person's goal, when it is ready (its chance
    is the game master's choice); never one that takes a protected person away; within the day's limit."""
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.direction import allows, counted

    simulation = _d(_sections.simulation_state_of(document))
    npc_id, goal_id = _s(payload.get("npc_id")), _s(payload.get("goal_id"))
    goal = next((row for person, row in goals(simulation) if person == npc_id and _s(row.get("goal_id")) == goal_id),
                None)
    if goal is None:
        return refused("no such goal with beats")
    beat = next_beat(simulation, npc_id, goal)
    if not beat:
        return refused("every beat of that goal is reached")
    if not _ready(simulation, npc_id, beat, clock(simulation) // MINUTES_PER_DAY):
        return refused(f"{_s(beat.get('id'))} is not ready (its condition, or a protected person)")
    limit = allows(simulation, "beat")
    if limit:
        return refused(limit)
    made, _ = advance(simulation, npc_id, goal, beat, source="game_master")
    return Folded([*made, counted(simulation, "beat")])


def present_at(simulation: Mapping[str, Any], location_id: str, minute: int, *, since: int | None = None) -> list[str]:
    """Who is at a place at ``minute`` when the hero is there: the people there, then the hero's companions."""
    found = whereabouts(simulation, minute, since=since, hero_at=location_id)
    party = companions(simulation)
    there = [npc_id for npc_id, where in found.items() if where.location_id == location_id and npc_id not in party]
    return there + [npc_id for npc_id in party if npc_id in found]


def described(simulation: Mapping[str, Any], npc_ids: list[str], minute: int, *, since: int | None = None,
              hero_at: str = "") -> list[str]:
    """The people named as the hero sees them: "the innkeeper (keeping the inn)"."""
    people = {**_d(_sections.npc_index_of(simulation)), **_d(_d(_sections.world_model_of(simulation)).get("npcs"))}
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
    index = _d(_sections.npc_index_of(simulation))
    return {npc_id: where for npc_id, where in whereabouts(simulation, minute, since=since).items()
            if where.location_id and (where.location_id, where.activity)
            != (_s(_d(index.get(npc_id)).get("location_id")), _s(_d(index.get(npc_id)).get("activity")))}


def present_now(simulation: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Where the presence last recorded is (an older campaign's names no place: the hero's), and who it names."""
    presence = _d(_sections.present_npc_state_of(simulation))
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


__all__ = ["BEATS_PER_DAY", "MINUTES_PER_DAY", "Whereabouts", "advance", "beat_address", "beat_by_address", "beat_moves",
           "clock", "comings_and_goings", "companions", "daily_beats", "described", "fold_beat", "fold_move", "goals",
           "hero_location", "is_wild", "moves", "next_beat", "present_at", "present_now", "reached", "whereabouts"]
