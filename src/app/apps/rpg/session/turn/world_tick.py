"""Step 6: the world moves on for the time the turn took (roadmap §4.1, §4.5), as changes.

Needs rise with the time that passed, and the world's causal runtime ticks (its pressures and the subsystems
they push on). Routines and events join here as their mechanics move onto the pipeline (RQ-2.7).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d
from app.apps.rpg.foundation.state.changes import NeedsChanged, StateChange, WorldTicked
from app.apps.rpg.rules.survival import SURVIVAL_MAX
from app.apps.rpg.rules.survival_tick_runtime import SURVIVAL_TICK_RATE_PROFILES
from app.apps.rpg.session.causal_turn_runtime import causal_tick

# How hard each mechanic's time presses on the hero's needs (the survival tick profiles).
NEED_PROFILE = {"look": "wait", "wait": "wait"}


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
    ticks: int,
    turn_key: str,
    turn: int,
) -> tuple[list[StateChange], dict[str, Any]]:
    """The world's changes for this turn, and the causal runtime's receipt ({} for a world without one)."""
    changes: list[StateChange] = []
    needs = _needs(document, ticks=ticks, profile=NEED_PROFILE.get(mechanic, "standard_turn"))
    if needs is not None:
        changes.append(needs)
    receipt = causal_tick(document, turn_key=turn_key, turn=turn) or {}
    if receipt.get("applied"):
        changes.append(WorldTicked(
            simulation=receipt.pop("simulation"), runtime=receipt.pop("runtime"),
            summary={"tick": receipt.get("tick"), "event_ids": list(receipt.get("event_ids") or ())},
        ))
    receipt.pop("simulation", None)
    receipt.pop("runtime", None)
    return changes, receipt


__all__ = ["NEED_PROFILE", "world_tick"]
