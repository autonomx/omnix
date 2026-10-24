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

MINUTES_PER_TICK = 10  # docs/rpg/design/time.md
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


def world_tick(
    document: Mapping[str, Any],
    *,
    needs: str | None,
    minutes: int,
    turn_key: str,
    turn: int,
) -> tuple[list[StateChange], dict[str, Any], list[str]]:
    """The world's changes for this turn, the causal runtime's receipt ({} for a world without one), and what the
    hero sees of it (people coming and going).

    ``needs`` is the turn's survival profile: the hero's needs rise by it once per turn, as the profiles are tuned;
    ``None`` presses on no one (time away, a trade).
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
    ticking = {**dict(document), "simulation_state": {**_d(document.get("simulation_state")), **sections}}
    receipt = causal_tick(ticking, turn_key=turn_key, turn=turn) or {}
    runtime: dict[str, Any] = {}
    if receipt.get("applied"):
        sections.update(receipt.pop("simulation"))
        runtime = receipt.pop("runtime")
    receipt.pop("simulation", None)
    receipt.pop("runtime", None)
    if sections or runtime:
        changes.append(WorldTicked(simulation=sections, runtime=runtime, summary={
            "minutes": minutes, "tick": receipt.get("tick"), "event_ids": list(receipt.get("event_ids") or ())}))
    return changes, receipt, seen


__all__ = ["MINUTES_PER_TICK", "clock_minute", "world_tick"]
