from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

NEEDS = ("hunger", "thirst", "fatigue")
TICK_DELTAS = {"hunger": 1, "thirst": 2, "fatigue": 1}
RELIEF_FALLBACK_DELTAS = {
    "drink_water": {"thirst_delta": -30},
    "drink_waterskin": {"thirst_delta": -30},
    "eat_food": {"hunger_delta": -30},
    "eat_trail_ration": {"hunger_delta": -30},
    "rest": {"fatigue_delta": -25},
    "sleep": {"fatigue_delta": -25},
    "buy_meal": {"hunger_delta": -35},
    "buy_drink": {"thirst_delta": -30},
    "buy_lodging": {"fatigue_delta": -40},
}
SOURCE = "n1272_survival_autoplay_persistence"
CALIBRATION_SOURCE = "n1273_long_run_survival_pressure_calibration"
ACCUMULATOR_SOURCE = "n1273_1_in_process_survival_accumulator"

_IN_PROCESS_SURVIVAL_ACCUMULATORS: Dict[str, Dict[str, Any]] = {}


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = safe_dict(value)
        if value:
            return value
    return {}


def _clamp_need(value: Any) -> int:
    return max(0, min(100, safe_int(value, 0)))


def _warnings(needs: Dict[str, int]) -> list[str]:
    warnings: list[str] = []
    if needs.get("hunger", 0) >= 70:
        warnings.append("hunger_high")
    if needs.get("thirst", 0) >= 70:
        warnings.append("thirst_high")
    if needs.get("fatigue", 0) >= 70:
        warnings.append("fatigue_high")
    return warnings


def _needs_from_survival(survival: Dict[str, Any]) -> Dict[str, int]:
    survival = safe_dict(survival)
    return {need: _clamp_need(survival.get(need)) for need in NEEDS}


def _result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(safe_dict(result).get("result"))


def _resolved_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = _result_payload(result)
    return safe_dict(payload.get("resolved_result") or payload.get("resolved_action"))


def _climate_from_session(session: Dict[str, Any]) -> Dict[str, Any]:
    session = safe_dict(session)
    sim = safe_dict(session.get("simulation_state"))
    runtime = safe_dict(session.get("runtime_state"))
    state = safe_dict(session.get("state"))
    state_sim = safe_dict(state.get("simulation_state"))
    metadata = safe_dict(safe_dict(session.get("setup_payload")).get("metadata"))
    return _first_dict(
        runtime.get("climate_survival"),
        sim.get("climate_survival"),
        state_sim.get("climate_survival"),
        state.get("climate_survival"),
        metadata.get("climate_survival"),
        safe_dict(metadata.get("simulation_state")).get("climate_survival"),
    )


def _action_count_from_climate(climate: Dict[str, Any]) -> int:
    return safe_int(safe_dict(safe_dict(climate).get("survival")).get("action_count"), 0)


def _max_need_from_climate(climate: Dict[str, Any]) -> int:
    needs = _needs_from_survival(safe_dict(safe_dict(climate).get("survival")))
    return max(needs.values() or [0])


def _accumulator_key(value: Any) -> str:
    return safe_str(value).strip()


def reset_survival_autoplay_accumulator(accumulator_key: str | None = None) -> None:
    key = _accumulator_key(accumulator_key)
    if key:
        _IN_PROCESS_SURVIVAL_ACCUMULATORS.pop(key, None)
    else:
        _IN_PROCESS_SURVIVAL_ACCUMULATORS.clear()


def _record_survival_accumulator(accumulator_key: str | None, climate: Dict[str, Any], meta: Dict[str, Any]) -> None:
    key = _accumulator_key(accumulator_key)
    climate = copy.deepcopy(safe_dict(climate))
    if not key or not climate:
        return
    survival = safe_dict(climate.get("survival"))
    _IN_PROCESS_SURVIVAL_ACCUMULATORS[key] = {
        "source": ACCUMULATOR_SOURCE,
        "climate_survival": climate,
        "needs": _needs_from_survival(survival),
        "action_count": safe_int(survival.get("action_count"), 0),
        "last_calibration": copy.deepcopy(safe_dict(meta)),
    }


def _accumulator_as_session(accumulator_key: str | None) -> Dict[str, Any]:
    key = _accumulator_key(accumulator_key)
    accumulator = safe_dict(_IN_PROCESS_SURVIVAL_ACCUMULATORS.get(key))
    climate = safe_dict(accumulator.get("climate_survival"))
    if not key or not climate:
        return {}
    survival = safe_dict(climate.get("survival"))
    needs = _needs_from_survival(survival)
    action_count = safe_int(survival.get("action_count"), 0)
    return {
        "simulation_state": {
            "climate_survival": copy.deepcopy(climate),
            "needs": dict(needs),
            "player_state": {
                "resources": {**dict(needs), "action_count": action_count},
            },
        },
        "runtime_state": {
            "climate_survival": copy.deepcopy(climate),
            "survival_autoplay_accumulator": copy.deepcopy(accumulator),
        },
        "state": {
            "climate_survival": copy.deepcopy(climate),
            "needs": dict(needs),
        },
        "setup_payload": {"metadata": {"climate_survival": copy.deepcopy(climate), "needs": dict(needs)}},
    }


def merge_survival_accumulator_into_session(session: Dict[str, Any], accumulator_key: str | None) -> Dict[str, Any]:
    session = copy.deepcopy(safe_dict(session))
    accumulator_session = _accumulator_as_session(accumulator_key)
    accumulator_climate = _climate_from_session(accumulator_session)
    if not accumulator_climate:
        return session
    session_climate = _climate_from_session(session)
    use_accumulator = not session_climate
    if session_climate:
        use_accumulator = (
            _action_count_from_climate(accumulator_climate) > _action_count_from_climate(session_climate)
            or _max_need_from_climate(accumulator_climate) > _max_need_from_climate(session_climate)
        )
    if not use_accumulator:
        return session
    if not session:
        session = {}
    return mirror_survival_state_into_session(session, accumulator_climate)


def extract_turn_survival_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result = safe_dict(result)
    turn_contract = safe_dict(result.get("turn_contract"))
    result_payload = _result_payload(result)
    resolved = _resolved_payload(result)
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
    needs = _needs_from_survival(survival)
    if not any(needs.values()) and not safe_int(survival.get("action_count"), 0):
        return {}
    climate = copy.deepcopy(climate)
    climate["survival"] = {**copy.deepcopy(survival), **needs}
    climate["runtime_enforced"] = True
    climate.setdefault("source", SOURCE)
    return climate


def _survival_action(result: Dict[str, Any]) -> Dict[str, Any]:
    result = safe_dict(result)
    contract = safe_dict(result.get("turn_contract"))
    resolved = _resolved_payload(result)
    changes = _first_dict(contract.get("resource_changes"), resolved.get("resource_changes"), _result_payload(result).get("resource_changes"))
    effect = _first_dict(contract.get("effect_result"), resolved.get("effect_result"), changes.get("effect_result"))
    return _first_dict(
        contract.get("survival_action"),
        resolved.get("survival_action"),
        changes.get("survival_action"),
        effect.get("survival_action"),
    )


def _action_kind(action: Dict[str, Any]) -> str:
    action = safe_dict(action)
    return safe_str(action.get("action_kind") or action.get("action") or action.get("kind") or action.get("need"))


def _action_deltas(action: Dict[str, Any]) -> Dict[str, int]:
    action = safe_dict(action)
    deltas = safe_dict(action.get("deltas"))
    resource_changes = safe_dict(action.get("resource_changes"))
    out = {f"{need}_delta": safe_int(deltas.get(f"{need}_delta", resource_changes.get(f"{need}_delta", 0)), 0) for need in NEEDS}
    if not any(out.values()):
        out.update({key: safe_int(value, 0) for key, value in RELIEF_FALLBACK_DELTAS.get(_action_kind(action), {}).items()})
    return out


def _needs_after_deltas(before: Dict[str, int], deltas: Dict[str, int]) -> Dict[str, int]:
    return {need: _clamp_need(safe_int(before.get(need), 0) + safe_int(deltas.get(f"{need}_delta"), 0)) for need in NEEDS}


def calibrate_turn_survival_state(result: Dict[str, Any], prior_session: Dict[str, Any] | None = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return a calibrated climate state plus metadata for long autoplay runs."""

    result = safe_dict(result)
    climate = extract_turn_survival_state(result)
    if not climate:
        return {}, {"calibrated": False, "reason": "missing_current_climate", "source": CALIBRATION_SOURCE}

    current_survival = safe_dict(climate.get("survival"))
    current_needs = _needs_from_survival(current_survival)
    prior_climate = _climate_from_session(safe_dict(prior_session or {}))
    prior_survival = safe_dict(prior_climate.get("survival"))
    prior_needs = _needs_from_survival(prior_survival)
    prior_action_count = safe_int(prior_survival.get("action_count"), 0)
    current_action_count = safe_int(current_survival.get("action_count"), 0)

    tick_before = current_needs
    calibrated = False
    reason = "current_turn_state_used"
    if prior_survival and prior_action_count >= current_action_count:
        tick_before = prior_needs
        calibrated = True
        reason = "current_action_count_regressed"
    elif prior_survival and max(current_needs.values() or [0]) + 5 < max(prior_needs.values() or [0]):
        tick_before = prior_needs
        calibrated = True
        reason = "current_needs_regressed"
    elif prior_survival and all(current_needs.get(need, 0) <= prior_needs.get(need, 0) for need in NEEDS):
        tick_before = prior_needs
        calibrated = True
        reason = "current_needs_did_not_advance"

    tick_after = {need: _clamp_need(tick_before.get(need, 0) + TICK_DELTAS[need]) for need in NEEDS}
    climate_before = current_needs if not calibrated else tick_before
    final_needs = dict(tick_after)

    action = _survival_action(result)
    action_deltas = _action_deltas(action) if action.get("applied") else {f"{need}_delta": 0 for need in NEEDS}
    if action.get("applied"):
        final_needs = _needs_after_deltas(tick_after, action_deltas)
        calibrated = True
        reason = "relief_applied_after_calibrated_tick" if reason == "current_turn_state_used" else reason

    action_count = max(current_action_count, prior_action_count + 1 if prior_survival else current_action_count)
    calibrated_climate = copy.deepcopy(climate)
    calibrated_climate["runtime_enforced"] = True
    if calibrated:
        calibrated_climate["source"] = CALIBRATION_SOURCE
        calibrated_climate["calibrated_from_source"] = safe_str(climate.get("source") or SOURCE)
    calibrated_survival = copy.deepcopy(current_survival)
    calibrated_survival.update(final_needs)
    calibrated_survival["action_count"] = action_count
    calibrated_survival["warnings"] = _warnings(final_needs)
    calibrated_climate["survival"] = calibrated_survival
    meta = {
        "calibrated": calibrated,
        "reason": reason,
        "before": climate_before,
        "after_tick": tick_after,
        "after": final_needs,
        "action_count_before": prior_action_count,
        "action_count_after": action_count,
        "current_needs": current_needs,
        "prior_needs": prior_needs,
        "source": CALIBRATION_SOURCE,
    }
    return calibrated_climate, meta


def _merge_resource_changes(existing: Dict[str, Any], climate: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    existing = copy.deepcopy(safe_dict(existing))
    before = safe_dict(meta.get("before"))
    after = safe_dict(meta.get("after"))
    tick_after = safe_dict(meta.get("after_tick"))
    tick_changes = {
        "source": "n1231_climate_survival_tick",
        "calibration_source": CALIBRATION_SOURCE if meta.get("calibrated") else "",
        "hunger_delta": safe_int(tick_after.get("hunger"), 0) - safe_int(before.get("hunger"), 0),
        "thirst_delta": safe_int(tick_after.get("thirst"), 0) - safe_int(before.get("thirst"), 0),
        "fatigue_delta": safe_int(tick_after.get("fatigue"), 0) - safe_int(before.get("fatigue"), 0),
        "before": before,
        "after": tick_after,
        "warnings": safe_list(safe_dict(climate.get("survival")).get("warnings")),
    }
    total = {
        "hunger_delta": safe_int(after.get("hunger"), 0) - safe_int(before.get("hunger"), 0),
        "thirst_delta": safe_int(after.get("thirst"), 0) - safe_int(before.get("thirst"), 0),
        "fatigue_delta": safe_int(after.get("fatigue"), 0) - safe_int(before.get("fatigue"), 0),
    }
    if not existing:
        existing = {"source": "merged_turn_resource_changes", "sources": []}
    existing["source"] = "merged_turn_resource_changes"
    sources = safe_list(existing.get("sources"))
    for source in ("n1231_climate_survival_tick", CALIBRATION_SOURCE):
        if source not in sources:
            sources.append(source)
    existing["sources"] = sources
    existing["climate_survival"] = tick_changes
    existing["survival_calibration"] = copy.deepcopy(meta)
    for key, value in total.items():
        existing[key] = value
    return existing


def _patch_action(action: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    action = copy.deepcopy(safe_dict(action))
    if not action or not action.get("applied"):
        return action
    before = safe_dict(meta.get("after_tick"))
    deltas = _action_deltas(action)
    after = _needs_after_deltas(before, deltas)
    action["before"] = before
    action["after"] = after
    action["deltas"] = deltas
    resource_changes = safe_dict(action.get("resource_changes"))
    resource_changes.update(deltas)
    resource_changes["before"] = before
    resource_changes["after"] = after
    resource_changes.setdefault("source", "n1232_survival_action_resolution")
    action["resource_changes"] = resource_changes
    return action


def patch_result_survival_state(result: Dict[str, Any], climate: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(safe_dict(result))
    if not climate:
        return result
    action = _patch_action(_survival_action(result), meta)
    warnings = safe_list(safe_dict(climate.get("survival")).get("warnings"))

    def patch_container(container: Dict[str, Any]) -> Dict[str, Any]:
        container = dict(safe_dict(container))
        if not container:
            return container
        container["climate_survival"] = copy.deepcopy(climate)
        container["resource_changes"] = _merge_resource_changes(container.get("resource_changes"), climate, meta)
        effect = dict(safe_dict(container.get("effect_result")))
        effect["source"] = "merged_turn_effect_result"
        effect["warnings"] = warnings
        effect["survival_calibration"] = copy.deepcopy(meta)
        if action:
            container["survival_action"] = copy.deepcopy(action)
            effect["survival_action"] = copy.deepcopy(action)
        container["effect_result"] = effect
        return container

    result = patch_container(result)
    contract = patch_container(safe_dict(result.get("turn_contract")))
    if contract:
        result["turn_contract"] = contract
    payload = dict(safe_dict(result.get("result")))
    if payload:
        payload = patch_container(payload)
        resolved_key = "resolved_result" if isinstance(payload.get("resolved_result"), dict) else "resolved_action"
        resolved = patch_container(safe_dict(payload.get(resolved_key)))
        if resolved:
            payload[resolved_key] = resolved
        result["result"] = payload
    return result


def mirror_survival_state_into_session(session: Dict[str, Any], climate_survival: Dict[str, Any]) -> Dict[str, Any]:
    session = copy.deepcopy(safe_dict(session))
    climate_survival = copy.deepcopy(safe_dict(climate_survival))
    survival = safe_dict(climate_survival.get("survival"))
    if not session or not climate_survival or not survival:
        return session
    needs = _needs_from_survival(survival)

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
    state["simulation_state"] = copy.deepcopy(simulation_state)
    state["player_state"] = copy.deepcopy(player_state)
    state["climate_survival"] = copy.deepcopy(climate_survival)
    state["needs"] = dict(needs)
    session["state"] = state

    setup_payload = safe_dict(session.get("setup_payload"))
    metadata = safe_dict(setup_payload.get("metadata"))
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


def persist_result_survival_state(
    result: Dict[str, Any],
    *,
    save: bool = True,
    prior_session: Dict[str, Any] | None = None,
    accumulator_key: str | None = None,
) -> Dict[str, Any]:
    result = dict(safe_dict(result))
    prior_session = merge_survival_accumulator_into_session(safe_dict(prior_session or {}), accumulator_key)
    climate, calibration = calibrate_turn_survival_state(result, prior_session=prior_session)
    session = safe_dict(result.get("session"))
    if not climate or not session:
        result["survival_autoplay_persistence"] = {
            "applied": False,
            "reason": "missing_climate_or_session",
            "source": SOURCE,
            "calibration": calibration,
        }
        return result

    result = patch_result_survival_state(result, climate, calibration)
    session = mirror_survival_state_into_session(session, climate)
    _record_survival_accumulator(accumulator_key, climate, calibration)
    result["session"] = session
    result["simulation_state"] = safe_dict(session.get("simulation_state"))
    result["survival_autoplay_persistence"] = {
        "applied": True,
        "needs": dict(safe_dict(climate.get("survival"))),
        "source": SOURCE,
        "calibration": calibration,
        "accumulator_key": _accumulator_key(accumulator_key),
        "accumulator_source": ACCUMULATOR_SOURCE if _accumulator_key(accumulator_key) else "",
    }

    if save:
        try:
            from app.rpg.session.service import save_session

            save_session(session)
        except Exception as exc:  # pragma: no cover - defensive live path
            result["survival_autoplay_persistence"]["save_error"] = repr(exc)
    return result
