"""Authoritative apply-turn bridge for the deterministic causal world runtime."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from app.rpg.world.causal_runtime import (
    advance_installed_causal_runtime,
    install_causal_runtime,
)
from app.rpg.world.causal_runtime_projection import (
    project_causal_runtime_to_subsystems,
)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _turn_value(payload: Mapping[str, Any]) -> int:
    source = _dict(payload)
    nested = _dict(source.get("result"))
    authoritative = _dict(source.get("authoritative"))
    contract = _dict(source.get("turn_contract") or authoritative.get("turn_contract"))
    for value in (
        source.get("turn"),
        source.get("turn_index"),
        nested.get("turn"),
        nested.get("turn_index"),
        authoritative.get("turn"),
        contract.get("turn_index"),
        contract.get("tick"),
    ):
        resolved = _int(value, -1)
        if resolved >= 0:
            return resolved
    return 0


def _turn_key(session_id: str, payload: Mapping[str, Any], turn: int) -> str:
    source = _dict(payload)
    nested = _dict(source.get("result"))
    authoritative = _dict(source.get("authoritative"))
    contract = _dict(source.get("turn_contract") or authoritative.get("turn_contract"))
    for value in (
        source.get("turn_id"),
        source.get("request_id"),
        nested.get("turn_id"),
        authoritative.get("turn_id"),
        contract.get("turn_id"),
        contract.get("contract_id"),
    ):
        rendered = str(value or "").strip()
        if rendered:
            return rendered
    return f"{session_id}:turn:{turn}"


def _bootstrap_from_session(session: Mapping[str, Any]) -> dict[str, Any]:
    public_state = _dict(session.get("state"))
    campaign_bible = _dict(public_state.get("campaign_bible"))
    manifest = _dict(campaign_bible.get("manifest"))
    bootstrap = manifest.get("causal_runtime_bootstrap")
    return deepcopy(dict(bootstrap)) if isinstance(bootstrap, Mapping) else {}


def _attach_receipt(payload: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["causal_world_runtime"] = dict(receipt)
    nested = _dict(result.get("result"))
    if nested:
        nested["causal_world_runtime"] = deepcopy(dict(receipt))
        result["result"] = nested
    return result


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
    session_raw = loader(session_id)
    if not isinstance(session_raw, Mapping):
        return result
    session = deepcopy(dict(session_raw))
    simulation = _dict(session.get("simulation_state"))
    runtime_state = _dict(session.get("runtime_state"))
    runtime = simulation.get("causal_world_runtime")
    if not isinstance(runtime, Mapping):
        bootstrap = _bootstrap_from_session(session)
        if not bootstrap:
            return result
        runtime = install_causal_runtime(simulation, bootstrap)

    turn = _turn_value(result)
    key = _turn_key(session_id, result, turn)
    applied = [str(value) for value in runtime_state.get("causal_applied_turn_keys") or ()]
    if key in applied:
        projection = _dict(simulation.get("causal_runtime_projection"))
        return _attach_receipt(
            result,
            {
                "applied": False,
                "reason": "turn_already_applied",
                "turn_key": key,
                "tick": int(_dict(runtime).get("last_tick") or 0),
                "projection": projection,
            },
        )

    last_tick = int(_dict(runtime).get("last_tick") or 0)
    target_tick = max(last_tick + 1, turn if turn > 0 else last_tick + 1)
    next_runtime, emitted = advance_installed_causal_runtime(
        simulation,
        tick=target_tick,
    )
    projection = project_causal_runtime_to_subsystems(
        simulation,
        next_runtime,
        tick=target_tick,
    )
    runtime_state["causal_applied_turn_keys"] = [*applied, key][-256:]
    runtime_state["causal_last_applied_turn_key"] = key
    runtime_state["causal_last_applied_tick"] = target_tick
    session["simulation_state"] = simulation
    session["runtime_state"] = runtime_state
    saver(session)
    return _attach_receipt(
        result,
        {
            "applied": True,
            "reason": "causal_runtime_advanced",
            "turn_key": key,
            "tick": target_tick,
            "event_ids": [event.event_id for event in emitted],
            "runtime_hash": str(next_runtime.get("runtime_hash") or ""),
            "projection": projection,
        },
    )


__all__ = ["advance_causal_runtime_for_turn"]
