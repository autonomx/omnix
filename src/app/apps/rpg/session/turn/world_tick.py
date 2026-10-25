"""Step 6: the world moves on for the time the turn took (roadmap §4.1, §4.5), as changes.

The one clock, the simulation's environment, advances by the turn's minutes (its weather with it); the world's
people go where their day takes them at the new hour, and who is present where the hero stands follows; the hero's
needs rise for the turn; and the world's causal runtime ticks (its pressures and the subsystems they push on).
Events join here as their mechanics move onto the pipeline (RQ-4.3, RQ-4.4).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d
from app.apps.rpg.foundation.state.changes import (
    NeedsChanged,
    PersonWhereabouts,
    PresenceChanged,
    StateChange,
    WhereaboutsChanged,
    WorldTicked,
)
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.survival import SURVIVAL_MAX
from app.apps.rpg.rules.survival_tick_runtime import SURVIVAL_TICK_RATE_PROFILES
from app.apps.rpg.session.causal_turn_runtime import causal_tick
from app.apps.rpg.world.environment_time import advance_environment_time

DEFAULT_START_MINUTE = 9 * 60


def _environment(document: Mapping[str, Any]) -> dict[str, Any]:
    """The clock: the simulation's environment, or the play screen's copy a campaign started with."""
    simulation = _d(document.get("simulation_state"))
    return dict(_d(simulation.get("environment")) or _d(_d(_d(document.get("state")).get("world")).get("environment"))
                or {"absolute_minutes": DEFAULT_START_MINUTE, "active_events": []})


def clock_minute(document: Mapping[str, Any]) -> int:
    """The campaign clock's absolute minutes now."""
    return int(_environment(document).get("absolute_minutes") or 0)


def _needs(document: Mapping[str, Any], *, ticks: int, profile: str) -> NeedsChanged | None:
    survival = _d(_d(document.get("simulation_state")).get("survival"))
    if survival.get("enabled") is False or ticks <= 0:
        return None
    rates = SURVIVAL_TICK_RATE_PROFILES.get(profile, SURVIVAL_TICK_RATE_PROFILES["standard_turn"])
    def rise(need: str) -> int:
        now = int(survival.get(need) or 0)
        return max(0, min(SURVIVAL_MAX, now + int(rates.get(need, 0)) * ticks) - now)

    hunger, thirst, fatigue = rise("hunger"), rise("thirst"), rise("fatigue")
    return NeedsChanged(hunger=hunger, thirst=thirst, fatigue=fatigue) if hunger or thirst or fatigue else None


def _people(document: Mapping[str, Any], environment: Mapping[str, Any]) -> tuple[list[StateChange], list[str]]:
    """Where the world's people are at the clock's new time, who is present where the hero stands, and what the hero
    sees of the comings and goings."""
    simulation = _d(document.get("simulation_state"))
    minute, since = int(environment.get("absolute_minutes") or 0), clock_minute(document)
    moved = routines.moves(simulation, minute, since=since)
    changes: list[StateChange] = []
    if moved:
        changes.append(WhereaboutsChanged(people=tuple(
            PersonWhereabouts(npc_id=npc_id, location_id=where.location_id, activity=where.activity)
            for npc_id, where in moved.items())))
    here = routines.hero_location(simulation)
    last_at, before = routines.present_now(simulation)
    after = routines.present_at(simulation, here, minute, since=since) if here else []
    if not here or (last_at == here and after == before):
        return changes, []
    changes.append(PresenceChanged(location_id=here, present_npc_ids=tuple(after)))
    seen = routines.comings_and_goings(_d(simulation.get("world_model")), before, after, moved) if last_at == here else []
    return changes, seen


MAX_PRESSURE_TICKS = 12  # the pressures move once for each hour the clock crosses, at most half a day's at once
SURFACED_PER_TURN = 2  # how many of the world's turns of fortune reach the hero in one turn (living world, RQ-4.4)
_WORD = {"pressure_escalated": "grows worse", "pressure_contained": "is held in check",
         "pressure_resolved": "is at an end", "pressure_reactivated": "stirs again"}


def _word(event_ids: list[str], runtime: Mapping[str, Any], region: str) -> list[str]:
    """What reaches the hero of the world's pressures turning (escalated, contained, resolved, stirring again): word of
    it, the hero's region first, at most ``SURFACED_PER_TURN``."""
    plan = {_d(row).get("pressure_id"): _d(row) for row in _d(runtime.get("pressure_plan")).get("pressures") or ()}
    heard = []
    for event_id in event_ids:
        for pressure_id, row in plan.items():
            kind = event_id.rsplit(":", 1)[-1]
            if f":{pressure_id}:" in event_id and kind in _WORD:
                local = _d(row.get("next_tick_delta")).get("target_id") == region
                heard.append((not local, f"Word comes: {row.get('name') or pressure_id} {_WORD[kind]}."))
    return [line for _, line in sorted(heard, key=lambda item: item[0])][:SURFACED_PER_TURN]


def world_tick(
    document: Mapping[str, Any],
    *,
    needs: str | None,
    minutes: int,
    turn_key: str,
) -> tuple[list[StateChange], dict[str, Any], list[str]]:
    """The world's changes for this turn, the causal runtime's receipt ({} for a world without one), and what the
    hero sees of it (people coming and going, and word of the world's pressures turning).

    ``needs`` is the turn's survival profile: the hero's needs rise by it once per turn, as the profiles are tuned;
    ``None`` presses on no one (time away, a trade). The world's pressures move by its time, not its turns: once for
    each hour the clock crosses (a blow in a fight, none; a night's sleep, eight), at most ``MAX_PRESSURE_TICKS``.
    """
    changes: list[StateChange] = []
    if needs:
        risen = _needs(document, ticks=1, profile=needs)
        if risen is not None:
            changes.append(risen)
    sections: dict[str, Any] = {}
    seen: list[str] = []
    if minutes > 0:
        sections["environment"] = advance_environment_time(_environment(document), elapsed_minutes=minutes)
        people, seen = _people(document, sections["environment"])
        changes.extend(people)
    before = clock_minute(document)
    after = int(_d(sections.get("environment")).get("absolute_minutes") or before)
    receipt: dict[str, Any] = {}
    runtime: dict[str, Any] = {}
    events: list[str] = []
    for hour in range(min(MAX_PRESSURE_TICKS, max(0, after // 60 - before // 60))):
        ticking = {**dict(document), "runtime_state": {**_d(document.get("runtime_state")), **runtime},
                   "simulation_state": {**_d(document.get("simulation_state")), **sections}}
        receipt = causal_tick(ticking, turn_key=turn_key if hour == 0 else f"{turn_key}:{hour}", turn=0) or {}
        if not receipt.get("applied"):
            break
        sections.update(receipt.pop("simulation"))
        runtime.update(receipt.pop("runtime"))
        events += [str(event) for event in receipt.get("event_ids") or ()]
    if events:
        simulation = _d(document.get("simulation_state"))
        place = _d(_d(_d(simulation.get("world_model")).get("locations")).get(routines.hero_location(simulation)))
        seen = [*seen, *_word(events, _d(sections.get("causal_world_runtime")), str(place.get("region_id") or ""))]
    receipt.pop("simulation", None)
    receipt.pop("runtime", None)
    if receipt:
        receipt["event_ids"] = events
    if sections or runtime:
        changes.append(WorldTicked(simulation=sections, runtime=runtime, summary={
            "minutes": minutes, "tick": receipt.get("tick"), "event_ids": events}))
    return changes, receipt, seen


__all__ = ["MAX_PRESSURE_TICKS", "clock_minute", "world_tick"]
