"""Environment-specific live feature matrix probes and validators."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

from app.rpg.session.environment_ecology_context import derive_ecology_context
from tests.rpg import interactive_intent_matrix as matrix

IntentFeatureScenario = matrix.IntentMatrixScenario
FeatureTurnExpectation = matrix.TurnExpectation

ENVIRONMENT_MATRIX_SCENARIO_IDS = frozenset(
    {
        "environment_snapshot_probe",
        "region_weather_switch_probe",
        "weather_travel_elapsed_probe",
        "terrain_memory_probe",
        "environment_narration_guardrail_probe",
        "ecology_resource_signal_probe",
    }
)


def environment_feature_matrix_scenarios() -> List[IntentFeatureScenario]:
    """Return environment-specific live-provider matrix probes."""

    E = FeatureTurnExpectation
    S = IntentFeatureScenario
    return [
        S(
            scenario_id="environment_snapshot_probe",
            title="Environment: inspect current snapshot",
            description="Asserts returned snapshot data and visible weather/time/terrain presentation.",
            commands=("I check the current weather, season, light, terrain, and travel conditions.",),
            expectations=(
                E(
                    1,
                    contains_any=("weather", "season", "terrain", "light", "temperature", "wind"),
                    provider_called=True,
                ),
            ),
        ),
        S(
            scenario_id="region_weather_switch_probe",
            title="Environment: travel toward a region and inspect weather",
            description="Asserts active-region snapshot data remains returned after travel-like input.",
            commands=(
                "I travel north toward the mountain pass.",
                "I check the weather and terrain in this area.",
            ),
            expectations=(
                E(
                    1,
                    contains_any=("travel", "north", "mountain", "pass", "road"),
                    final_action_type="travel",
                    final_requested_terms_contains_any=("north", "mountain", "pass"),
                    provider_called=True,
                ),
                E(
                    2,
                    contains_any=("weather", "terrain", "area", "condition", "wind", "light"),
                    provider_called=True,
                ),
            ),
        ),
        S(
            scenario_id="weather_travel_elapsed_probe",
            title="Environment: travel advances environment time",
            description="Asserts returned environment state advances absolute minutes after travel.",
            commands=(
                "I check the current time and weather.",
                "I travel north along the road for a while.",
                "I check the time and weather again.",
            ),
            expectations=(
                E(1, contains_any=("time", "weather", "season", "day"), provider_called=True),
                E(
                    2,
                    contains_any=("travel", "road", "north", "time", "weather"),
                    final_action_type="travel",
                    provider_called=True,
                ),
                E(3, contains_any=("time", "weather", "season", "day"), provider_called=True),
            ),
        ),
        S(
            scenario_id="terrain_memory_probe",
            title="Environment: terrain memory is returned",
            description="Asserts returned recent-condition memory and derived terrain are present.",
            commands=("I study the ground for mud, dust, snowpack, slush, tracks, and trail conditions.",),
            expectations=(
                E(
                    1,
                    contains_any=("ground", "terrain", "trail", "mud", "dust", "snow", "track", "condition"),
                    provider_called=True,
                ),
            ),
        ),
        S(
            scenario_id="environment_narration_guardrail_probe",
            title="Environment: narration guardrail contract is returned",
            description="Asserts the read-only environment narration contract is attached to live output.",
            commands=("Describe the current environment, but do not change the weather or time.",),
            expectations=(
                E(
                    1,
                    contains_any=("environment", "weather", "time", "current", "terrain", "condition"),
                    provider_called=True,
                ),
            ),
        ),
        S(
            scenario_id="ecology_resource_signal_probe",
            title="Environment: resource and ecology signals are derivable",
            description="Asserts returned resource signals can derive deterministic ecology context.",
            commands=("I look for water, forage, wildlife, fish, herbs, and signs of drought or snowpack.",),
            expectations=(
                E(
                    1,
                    contains_any=("water", "forage", "wildlife", "fish", "herb", "snow", "drought"),
                    provider_called=True,
                ),
            ),
        ),
    ]


def apply_environment_feature_validators(
    item: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> Dict[str, Any]:
    """Append environment-probe failures to a base matrix validation result."""

    scenario = item.get("scenario")
    scenario_id = getattr(scenario, "scenario_id", "") or str(validation.get("scenario_id") or "")
    extra_failures = _validate_environment_feature_scenario(
        scenario_id,
        matrix._safe_dict(item.get("result")),
    )
    adjusted = dict(validation)
    if extra_failures:
        failures = list(adjusted.get("failures") or [])
        failures.extend(extra_failures)
        adjusted["failures"] = failures
        adjusted["ok"] = False
    return adjusted


def _validate_environment_feature_scenario(scenario_id: str, result: Mapping[str, Any]) -> List[str]:
    if scenario_id not in ENVIRONMENT_MATRIX_SCENARIO_IDS:
        return []
    turns = [matrix._safe_dict(turn) for turn in list(result.get("turns") or [])]
    failures: List[str] = []
    snapshots = _all_turn_snapshots(result)
    if not snapshots:
        return [f"{scenario_id}: expected returned environment_snapshot data in turn JSON"]
    failures.extend(_validate_basic_snapshot(scenario_id, snapshots[-1]))
    visible = _environment_visible_blob(result)
    if "weather" not in visible and "terrain" not in visible:
        failures.append(f"{scenario_id}: expected weather or terrain to be visible in output")

    if scenario_id == "region_weather_switch_probe":
        region_ids = {str(snapshot.get("region_id") or "") for snapshot in snapshots}
        if "" in region_ids or not region_ids:
            failures.append("region_weather_switch_probe: expected returned snapshot region_id")
        if len(snapshots) < 2:
            failures.append("region_weather_switch_probe: expected snapshot after travel and follow-up")

    if scenario_id == "weather_travel_elapsed_probe":
        minutes = [
            _safe_int(state.get("absolute_minutes"), -1)
            for turn in turns
            if (state := _turn_environment_state(turn))
        ]
        if len(minutes) < 2:
            failures.append("weather_travel_elapsed_probe: expected returned environment time on multiple turns")
        elif minutes[-1] <= minutes[0]:
            failures.append(f"weather_travel_elapsed_probe: expected time to advance, got {minutes!r}")

    if scenario_id == "terrain_memory_probe":
        state = next((_turn_environment_state(turn) for turn in reversed(turns) if _turn_environment_state(turn)), {})
        recent = matrix._safe_dict(state.get("recent_conditions"))
        if not recent:
            failures.append("terrain_memory_probe: expected returned recent_conditions memory")
        if not snapshots[-1].get("terrain_condition"):
            failures.append("terrain_memory_probe: expected derived terrain_condition in snapshot")

    if scenario_id == "environment_narration_guardrail_probe":
        contract = next((_turn_narration_contract(turn) for turn in reversed(turns) if _turn_narration_contract(turn)), {})
        if contract.get("authority") != "read_only_environment_snapshot":
            failures.append("environment_narration_guardrail_probe: expected read-only environment authority")
        forbidden = list(contract.get("forbidden") or [])
        if "advance_time" not in forbidden or "invent_temperature" not in forbidden:
            failures.append("environment_narration_guardrail_probe: expected mutation guardrails")

    if scenario_id == "ecology_resource_signal_probe":
        ecology = derive_ecology_context(dict(snapshots[-1]))
        for key in ("wildlife_activity", "fish_activity", "plant_growth", "water_point_encounter_pressure"):
            if not ecology.get(key):
                failures.append(f"ecology_resource_signal_probe: missing derived ecology field {key}")

    return failures


def _validate_basic_snapshot(scenario_id: str, snapshot: Mapping[str, Any]) -> List[str]:
    failures: List[str] = []
    weather = matrix._safe_dict(snapshot.get("weather"))
    calendar = matrix._safe_dict(snapshot.get("calendar"))
    display = matrix._safe_dict(snapshot.get("display"))
    resources = matrix._safe_dict(snapshot.get("resources"))
    context = matrix._safe_dict(snapshot.get("context"))
    required = {
        "weather.condition": weather.get("condition"),
        "weather.intensity": weather.get("intensity"),
        "calendar.season_id": calendar.get("season_id"),
        "calendar.time_label": calendar.get("time_label"),
        "display.weather": display.get("weather"),
        "display.terrain": display.get("terrain"),
        "resources.water_availability": resources.get("water_availability"),
        "resources.forage_availability": resources.get("forage_availability"),
        "context.exposure": context.get("exposure"),
    }
    for name, value in required.items():
        if value in (None, ""):
            failures.append(f"{scenario_id}: missing returned environment snapshot field {name}")
    return failures


def _all_turn_snapshots(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [
        snapshot
        for turn in list(result.get("turns") or [])
        if (snapshot := _turn_environment_snapshot(matrix._safe_dict(turn)))
    ]


def _turn_environment_snapshot(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = matrix._safe_dict(turn.get("raw_result") or turn.get("result"))
    return _find_mapping_with_keys(raw, {"weather", "calendar", "display", "resources"})


def _turn_environment_state(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = matrix._safe_dict(turn.get("raw_result") or turn.get("result"))
    return _find_mapping_with_keys(raw, {"absolute_minutes", "active_events", "recent_conditions"})


def _turn_narration_contract(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = matrix._safe_dict(turn.get("raw_result") or turn.get("result"))
    return _find_mapping_with_keys(raw, {"authority", "allowed", "forbidden", "instruction"})


def _find_mapping_with_keys(value: Any, required_keys: set[str], *, max_depth: int = 7) -> Dict[str, Any]:
    if max_depth < 0:
        return {}
    if isinstance(value, dict):
        if required_keys.issubset(value.keys()):
            return dict(value)
        for nested in value.values():
            found = _find_mapping_with_keys(nested, required_keys, max_depth=max_depth - 1)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_mapping_with_keys(nested, required_keys, max_depth=max_depth - 1)
            if found:
                return found
    return {}


def _environment_visible_blob(result: Mapping[str, Any]) -> str:
    blobs: List[str] = []
    for turn in list(result.get("turns") or []):
        turn_dict = matrix._safe_dict(turn)
        blobs.append(matrix._visible_turn_blob(turn_dict))
        blobs.append(json.dumps(turn_dict, sort_keys=True, default=str))
    return "\n".join(blobs).lower()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
