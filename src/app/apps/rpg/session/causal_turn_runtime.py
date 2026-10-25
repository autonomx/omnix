"""Authoritative apply-turn bridge for the deterministic causal world runtime."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.apps.rpg.world.causal_runtime import (
    advance_installed_causal_runtime,
    initialize_causal_runtime,
)
from app.apps.rpg.world.causal_runtime_projection import (
    project_causal_runtime_to_subsystems,
)
from app.apps.rpg.foundation.safe_values import copy_state
from app.apps.rpg.foundation.state import access as _sections


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _bootstrap_from_session(session: Mapping[str, Any]) -> dict[str, Any]:
    simulation = _dict(_sections.simulation_state_of(session))
    public_state = _dict(session.get("state"))
    for candidate in (
        simulation.get("campaign_bible"),
        public_state.get("campaign_bible"),
        session.get("campaign_bible"),
    ):
        campaign_bible = _dict(candidate)
        manifest = _dict(campaign_bible.get("manifest"))
        bootstrap = manifest.get("causal_runtime_bootstrap")
        if isinstance(bootstrap, Mapping):
            return deepcopy(dict(bootstrap))
    return {}


def causal_tick(session: Mapping[str, Any], *, turn_key: str, turn: int) -> dict[str, Any] | None:
    """One causal tick of the world for a turn, on a copy: the sections it changed and its receipt.

    ``None`` when the world has no causal runtime; ``{"applied": False, ...}`` when this turn already ticked it.
    The world tick (RQ-1.4 step 6) turns the sections into a ``WorldTicked`` change.
    """
    session = copy_state(dict(session))
    simulation = _dict(_sections.simulation_state_of(session))
    runtime_state = _dict(_sections.runtime_state_of(session))
    runtime = simulation.get("causal_world_runtime")
    if not isinstance(runtime, Mapping):
        bootstrap = _bootstrap_from_session(session)
        if not bootstrap:
            return None
        runtime = initialize_causal_runtime(simulation, bootstrap)
    applied = [str(value) for value in runtime_state.get("causal_applied_turn_keys") or ()]
    if turn_key in applied:
        return {"applied": False, "reason": "turn_already_applied", "turn_key": turn_key,
                "tick": int(_dict(runtime).get("last_tick") or 0),
                "projection": _dict(simulation.get("causal_runtime_projection")), "simulation": {}, "runtime": {}}
    before = copy_state(simulation)
    last_tick = int(_dict(runtime).get("last_tick") or 0)
    target_tick = max(last_tick + 1, turn if turn > 0 else last_tick + 1)
    next_runtime, emitted = advance_installed_causal_runtime(simulation, tick=target_tick)
    projection = project_causal_runtime_to_subsystems(simulation, next_runtime, tick=target_tick)
    return {
        "applied": True,
        "reason": "causal_runtime_advanced",
        "turn_key": turn_key,
        "tick": target_tick,
        "event_ids": [event.event_id for event in emitted],
        "runtime_hash": str(next_runtime.get("runtime_hash") or ""),
        "projection": projection,
        "simulation": {key: value for key, value in simulation.items() if before.get(key) != value},
        "runtime": {
            "causal_applied_turn_keys": [*applied, turn_key][-256:],
            "causal_last_applied_turn_key": turn_key,
            "causal_last_applied_tick": target_tick,
        },
    }


__all__ = ["causal_tick"]
