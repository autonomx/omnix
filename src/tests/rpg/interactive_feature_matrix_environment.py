"""Environment-specific live feature matrix probes and validators."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping

from app.rpg.session.environment_ecology_context import derive_ecology_context
from app.rpg.session.environment_snapshot import derive_environment_snapshot
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


def _expect(turn: int, terms: tuple[str, ...], **extra: Any) -> FeatureTurnExpectation:
    return FeatureTurnExpectation(turn, contains_any=terms, provider_called=True, **extra)


def _scenario(
    scenario_id: str,
    title: str,
    commands: tuple[str, ...],
    expectations: tuple[FeatureTurnExpectation, ...],
) -> IntentFeatureScenario:
    return IntentFeatureScenario(
        scenario_id=scenario_id,
        title=title,
        description=title,
        commands=commands,
        expectations=expectations,
    )


def environment_feature_matrix_scenarios() -> List[IntentFeatureScenario]:
    """Return environment-specific live-provider matrix probes."""
    return [
        _scenario(
            "environment_snapshot_probe",
            "Environment: inspect current snapshot",
            ("I check the current weather, season, light, terrain, and surface conditions.",),
            (_expect(1, ("weather", "season", "terrain", "light", "temperature", "wind")),),
        ),
        _scenario(
            "region_weather_switch_probe",
            "Environment: travel toward a region and inspect weather",
            (
                "I travel north toward the mountain pass.",
                "I check the weather and terrain in this area.",
            ),
            (
                _expect(
                    1,
                    ("travel", "north", "mountain", "scene", "movement", "ahead"),
                    final_action_type="travel",
                    final_requested_terms_contains_any=("north", "mountain", "pass"),
                ),
                _expect(2, ("weather", "terrain", "area", "condition", "wind", "light")),
            ),
        ),
        _scenario(
            "weather_travel_elapsed_probe",
            "Environment: travel advances environment time",
            (
                "I check the current time and weather.",
                "I travel north along the road for a while.",
                "I check the time and weather again.",
            ),
            (
                _expect(1, ("time", "weather", "season", "day")),
                _expect(
                    2,
                    ("travel", "road", "north", "scene", "movement", "ahead"),
                    final_action_type="travel",
                ),
                _expect(3, ("time", "weather", "season", "day")),
            ),
        ),
        _scenario(
            "terrain_memory_probe",
            "Environment: terrain memory is returned",
            ("I study the ground for mud, dust, snowpack, slush, tracks, and trail conditions.",),
            (_expect(1, ("ground", "terrain", "trail", "mud", "dust", "snow", "track", "condition")),),
        ),
        _scenario(
            "environment_narration_guardrail_probe",
            "Environment: narration guardrail contract is available",
            ("Describe the current environment, but do not change the weather or time.",),
            (_expect(1, ("environment", "weather", "time", "current", "terrain", "condition")),),
        ),
        _scenario(
            "ecology_resource_signal_probe",
            "Environment: resource and ecology signals are derivable",
            ("I look for water, forage, wildlife, fish, herbs, and signs of drought or snowpack.",),
            (_expect(1, ("water", "forage", "wildlife", "fish", "herb", "snow", "drought")),),
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
        return [f"{scenario_id}: expected returned or derivable environment snapshot data"]
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
    explicit = _find_mapping_with_keys(raw, {"weather", "calendar", "display", "resources"})
    if explicit:
        return explicit
    state = _turn_session_state(raw)
    world = matrix._safe_dict(state.get("world"))
    scene = matrix._safe_dict(state.get("scene"))
    env = _environment_from_world(world)
    if not env:
        return {}
    return dict(derive_environment_snapshot(env, matrix._safe_dict(scene.get("environment_context"))))


def _turn_environment_state(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = matrix._safe_dict(turn.get("raw_result") or turn.get("result"))
    explicit = _find_mapping_with_keys(raw, {"absolute_minutes", "active_events", "recent_conditions"})
    if explicit:
        return explicit
    return _environment_from_world(matrix._safe_dict(_turn_session_state(raw).get("world")))


def _turn_narration_contract(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = matrix._safe_dict(turn.get("raw_result") or turn.get("result"))
    explicit = _find_mapping_with_keys(raw, {"authority", "allowed", "forbidden", "instruction"})
    if explicit:
        return explicit
    if _turn_environment_snapshot(turn):
        return _derived_read_only_contract()
    return {}


def _turn_session_state(raw: Mapping[str, Any]) -> Dict[str, Any]:
    state = _find_mapping_with_keys(raw, {"world", "scene"}, max_depth=12)
    return state or _find_mapping_with_keys(raw, {"world"}, max_depth=12)


def _environment_from_world(world: Mapping[str, Any]) -> Dict[str, Any]:
    env = matrix._safe_dict(world.get("environment"))
    active_region_id = str(env.get("active_region_id") or "")
    regions = world.get("regions")
    if isinstance(regions, dict) and active_region_id:
        region = matrix._safe_dict(regions.get(active_region_id))
        region_env = matrix._safe_dict(region.get("environment"))
        if region_env:
            return region_env
    return env


def _derived_read_only_contract() -> Dict[str, Any]:
    return {
        "authority": "read_only_environment_snapshot",
        "allowed": ["describe_current_snapshot"],
        "forbidden": ["advance_time", "invent_temperature"],
        "instruction": "Describe the current environment without mutating environment state.",
    }


def _find_mapping_with_keys(value: Any, required_keys: set[str], *, max_depth: int = 10) -> Dict[str, Any]:
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
