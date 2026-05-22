from __future__ import annotations

import copy
from typing import Any, Dict

NEEDS = ("hunger", "thirst", "fatigue")
SOURCE = "n1272_survival_autoplay_persistence"


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = safe_dict(value)
        if value:
            return value
    return {}


def _clamp_need(value: Any) -> int:
    return max(0, min(100, safe_int(value, 0)))


def extract_turn_survival_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result = safe_dict(result)
    turn_contract = safe_dict(result.get("turn_contract"))
    result_payload = safe_dict(result.get("result"))
    resolved = safe_dict(result_payload.get("resolved_result") or result_payload.get("resolved_action"))
    session = safe_dict(result.get("session"))
    simulation_state = safe_dict(result.get("simulation_state") or safe_dict(session.get("simulation_state")))

    climate = _first_dict(
        turn_contract.get("climate_survival"),
        resolved.get("climate_survival"),
        result_payload.get("climate_survival"),
        simulation_state.get("climate_survival"),
    )
    if not climate:
        return {}
    survival = safe_dict(climate.get("survival"))
    if not survival:
        return {}
    needs = {need: _clamp_need(survival.get(need)) for need in NEEDS}
    if not any(needs.values()) and not safe_int(survival.get("action_count"), 0):
        return {}
    climate = copy.deepcopy(climate)
    climate["survival"] = {**copy.deepcopy(survival), **needs}
    climate["runtime_enforced"] = True
    climate.setdefault("source", SOURCE)
    return climate


def mirror_survival_state_into_session(session: Dict[str, Any], climate_survival: Dict[str, Any]) -> Dict[str, Any]:
    session = copy.deepcopy(safe_dict(session))
    climate_survival = copy.deepcopy(safe_dict(climate_survival))
    survival = safe_dict(climate_survival.get("survival"))
    if not session or not climate_survival or not survival:
        return session
    needs = {need: _clamp_need(survival.get(need)) for need in NEEDS}

    simulation_state = safe_dict(session.get("simulation_state"))
    player_state = safe_dict(simulation_state.get("player_state"))
    resources = safe_dict(player_state.get("resources"))
    resources.update(needs)
    if safe_int(survival.get("action_count"), 0):
        resources["action_count"] = safe_int(survival.get("action_count"), 0)
    player_state["resources"] = resources
    player_state["climate_survival"] = copy.deepcopy(climate_survival)
    simulation_state["player_state"] = player_state
    simulation_state["climate_survival"] = copy.deepcopy(climate_survival)
    simulation_state["needs"] = dict(needs)
    session["simulation_state"] = simulation_state

    state = safe_dict(session.get("state"))
    if state:
        state["simulation_state"] = copy.deepcopy(simulation_state)
        state["player_state"] = copy.deepcopy(player_state)
        state["climate_survival"] = copy.deepcopy(climate_survival)
        state["needs"] = dict(needs)
        session["state"] = state

    setup_payload = safe_dict(session.get("setup_payload"))
    metadata = safe_dict(setup_payload.get("metadata"))
    if metadata:
        metadata["simulation_state"] = copy.deepcopy(simulation_state)
        metadata["player_state"] = copy.deepcopy(player_state)
        metadata["climate_survival"] = copy.deepcopy(climate_survival)
        metadata["needs"] = dict(needs)
        setup_payload["metadata"] = metadata
        session["setup_payload"] = setup_payload

    runtime_state = safe_dict(session.get("runtime_state"))
    runtime_state["climate_survival"] = copy.deepcopy(climate_survival)
    runtime_state["last_survival_autoplay_persisted_needs"] = dict(needs)
    runtime_state["last_survival_autoplay_persistence_source"] = SOURCE
    session["runtime_state"] = runtime_state
    return session


def persist_result_survival_state(result: Dict[str, Any], *, save: bool = True) -> Dict[str, Any]:
    result = dict(safe_dict(result))
    climate = extract_turn_survival_state(result)
    session = safe_dict(result.get("session"))
    if not climate or not session:
        result["survival_autoplay_persistence"] = {
            "applied": False,
            "reason": "missing_climate_or_session",
            "source": SOURCE,
        }
        return result

    session = mirror_survival_state_into_session(session, climate)
    result["session"] = session
    result["simulation_state"] = safe_dict(session.get("simulation_state"))
    result["survival_autoplay_persistence"] = {
        "applied": True,
        "needs": dict(safe_dict(climate.get("survival"))),
        "source": SOURCE,
    }

    if save:
        try:
            from app.rpg.session.service import save_session

            save_session(session)
        except Exception as exc:  # pragma: no cover - defensive live path
            result["survival_autoplay_persistence"]["save_error"] = repr(exc)
    return result
