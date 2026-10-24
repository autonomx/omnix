"""Step 6: the world moves on for the time the turn took (roadmap §4.1, §4.5), as changes.

The one clock, the simulation's environment, advances by the turn's minutes (its weather with it); the hero's
needs rise for the turn; and the world's causal runtime ticks (its pressures and the subsystems they push on).
Routines and events join here as their mechanics move onto the pipeline (RQ-2.7, RQ-4.3).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d
from app.apps.rpg.foundation.state.changes import NeedsChanged, StateChange, WorldTicked
from app.apps.rpg.rules.survival import SURVIVAL_MAX
from app.apps.rpg.rules.survival_tick_runtime import SURVIVAL_TICK_RATE_PROFILES
from app.apps.rpg.session.causal_turn_runtime import causal_tick
from app.apps.rpg.world.environment_time import advance_environment_time

# How hard each mechanic's turn presses on the hero's needs (the survival tick profiles); time away presses none.
NEED_PROFILE = {"look": "wait", "wait": "wait", "travel": "travel"}
MINUTES_PER_TICK = 10  # docs/rpg/design/time.md
DEFAULT_START_MINUTE = 9 * 60


def _environment(document: Mapping[str, Any]) -> dict[str, Any]:
    """The clock: the simulation's environment, or the play screen's copy a campaign started with."""
    simulation = _d(document.get("simulation_state"))
    return dict(_d(simulation.get("environment")) or _d(_d(_d(document.get("state")).get("world")).get("environment"))
                or {"absolute_minutes": DEFAULT_START_MINUTE, "active_events": []})


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


def world_tick(
    document: Mapping[str, Any],
    *,
    mechanic: str,
    minutes: int,
    turn_key: str,
    turn: int,
) -> tuple[list[StateChange], dict[str, Any]]:
    """The world's changes for this turn, and the causal runtime's receipt ({} for a world without one)."""
    changes: list[StateChange] = []
    if mechanic in NEED_PROFILE:  # once per turn, as the profiles are tuned; time away presses on no one
        needs = _needs(document, ticks=1, profile=NEED_PROFILE[mechanic])
        if needs is not None:
            changes.append(needs)
    sections: dict[str, Any] = {}
    if minutes > 0:
        sections["environment"] = advance_environment_time(_environment(document), elapsed_minutes=minutes)
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
    return changes, receipt


__all__ = ["MINUTES_PER_TICK", "NEED_PROFILE", "world_tick"]
