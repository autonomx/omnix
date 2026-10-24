"""Authoritative apply-turn bridge for the deterministic causal world runtime."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from app.apps.rpg.world.causal_runtime import (
    advance_installed_causal_runtime,
    initialize_causal_runtime,
)
from app.apps.rpg.world.causal_runtime_projection import (
    project_causal_runtime_to_subsystems,
)
from app.apps.rpg.foundation.safe_values import copy_state


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _turn_contract(payload: Mapping[str, Any], session: Mapping[str, Any]) -> dict[str, Any]:
    source = _dict(payload)
    nested = _dict(source.get("result"))
    authoritative = _dict(source.get("authoritative"))
    runtime_state = _dict(session.get("runtime_state"))
    return _dict(
        source.get("turn_contract")
        or nested.get("turn_contract")
        or authoritative.get("turn_contract")
        or runtime_state.get("last_turn_contract")
    )


def _turn_value(payload: Mapping[str, Any], session: Mapping[str, Any]) -> int:
    source = _dict(payload)
    nested = _dict(source.get("result"))
    authoritative = _dict(source.get("authoritative"))
    runtime_state = _dict(session.get("runtime_state"))
    contract = _turn_contract(source, session)
    for value in (
        source.get("turn"),
        source.get("turn_index"),
        nested.get("turn"),
        nested.get("turn_index"),
        authoritative.get("turn"),
        authoritative.get("turn_index"),
        contract.get("turn_index"),
        contract.get("tick"),
        runtime_state.get("tick"),
    ):
        resolved = _int(value, -1)
        if resolved >= 0:
            return resolved
    return 0


def _turn_key(
    session_id: str,
    payload: Mapping[str, Any],
    session: Mapping[str, Any],
    turn: int,
) -> str:
    source = _dict(payload)
    nested = _dict(source.get("result"))
    authoritative = _dict(source.get("authoritative"))
    contract = _turn_contract(source, session)
    for value in (
        source.get("turn_id"),
        source.get("request_id"),
        nested.get("turn_id"),
        nested.get("request_id"),
        authoritative.get("turn_id"),
        contract.get("turn_id"),
        contract.get("contract_id"),
    ):
        rendered = str(value or "").strip()
        if rendered:
            return rendered
    return f"{session_id}:turn:{turn}"


def _bootstrap_from_session(session: Mapping[str, Any]) -> dict[str, Any]:
    simulation = _dict(session.get("simulation_state"))
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


def _attach_receipt(payload: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["causal_world_runtime"] = dict(receipt)
    nested = _dict(result.get("result"))
    if nested:
        nested["causal_world_runtime"] = deepcopy(dict(receipt))
        result["result"] = nested
    authoritative = _dict(result.get("authoritative"))
    if authoritative:
        authoritative["causal_world_runtime"] = deepcopy(dict(receipt))
        result["authoritative"] = authoritative
    return result


def _attach_session_state(
    payload: Mapping[str, Any],
    session: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(payload)
    session_copy = deepcopy(dict(session))
    simulation = deepcopy(_dict(session_copy.get("simulation_state")))
    result["session"] = session_copy
    result["simulation_state"] = simulation
    nested = _dict(result.get("result"))
    if nested:
        nested["session"] = deepcopy(session_copy)
        nested["simulation_state"] = deepcopy(simulation)
        result["result"] = nested
    return result


def _turn_session(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The session a turn's result carries (top level, or its nested result), if it has one."""
    for source in (payload, _dict(payload.get("result"))):
        session = source.get("session")
        if isinstance(session, Mapping) and isinstance(session.get("simulation_state"), Mapping):
            return session
    return None


def causal_tick(session: Mapping[str, Any], *, turn_key: str, turn: int) -> dict[str, Any] | None:
    """One causal tick of the world for a turn, on a copy: the sections it changed and its receipt.

    ``None`` when the world has no causal runtime; ``{"applied": False, ...}`` when this turn already ticked it.
    The world tick (RQ-1.4 step 6) turns the sections into a ``WorldTicked`` change.
    """
    session = copy_state(dict(session))
    simulation = _dict(session.get("simulation_state"))
    runtime_state = _dict(session.get("runtime_state"))
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


def advance_causal_runtime_for_turn(
    session_id: str,
    payload: Mapping[str, Any],
    *,
    loader: Callable[[str], Mapping[str, Any] | None],
    saver: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    """Advance once for a successful authoritative turn; legacy worlds are no-ops."""

    result = dict(payload)
    if result.get("success") is False or result.get("ok") is False:
        return result
    # Advance the session this turn produced. Inside a turn every load returns the turn-start session
    # (saves are deferred to the commit), so reloading here and saving it would undo the turn's changes:
    # its travel, its party, its purchases.
    session_raw = _turn_session(result) or loader(session_id)
    if not isinstance(session_raw, Mapping):
        return result
    session = copy_state(dict(session_raw))
    turn = _turn_value(result, session)
    key = _turn_key(session_id, result, session, turn)
    tick = causal_tick(session, turn_key=key, turn=turn)
    if tick is None:
        return result
    sections, runtime_keys = tick.pop("simulation"), tick.pop("runtime")
    if tick["applied"]:
        session["simulation_state"] = {**_dict(session.get("simulation_state")), **sections}
        session["runtime_state"] = {**_dict(session.get("runtime_state")), **runtime_keys}
        saver(session)
    result = _attach_session_state(result, session)
    return _attach_receipt(result, tick)


__all__ = ["advance_causal_runtime_for_turn", "causal_tick"]
