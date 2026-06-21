from __future__ import annotations

from copy import deepcopy

from app.rpg.session.environment import build_initial_environment_seed_state
from app.rpg.session.environment_snapshot import derive_environment_snapshot


def _tavern_seed_state() -> dict[str, object]:
    return build_initial_environment_seed_state(
        campaign_seed=42,
        campaign_contract={"campaign_template": "classic_fantasy", "tone": "heroic adventure"},
        location_id="rusty_flagon_tavern",
        location={"time_label": "Day 1 • 08:00", "weather": "Rainy", "location": "Rusty Flagon Tavern"},
    )


def _mountain_seed_state() -> dict[str, object]:
    return build_initial_environment_seed_state(
        campaign_seed=140914,
        campaign_contract={"campaign_template": "classic_fantasy", "tone": "mountain mystery"},
        location_id="glimmerdeep_pass",
        location={"time_label": "Day 18 • 09:42", "weather": "Cold, Windy", "location": "Glimmerdeep Pass"},
    )


def test_environment_snapshot_is_deterministic_and_not_persisted() -> None:
    state = _tavern_seed_state()
    environment = deepcopy(state["environment"])
    scene_context = deepcopy(state["scene_environment_context"])

    first = derive_environment_snapshot(environment, scene_context)
    second = derive_environment_snapshot(environment, scene_context)

    assert first == second
    assert "snapshot" not in environment
    assert "environment_snapshot" not in environment
    assert environment == state["environment"]
    assert scene_context == state["scene_environment_context"]


def test_environment_snapshot_supports_indoor_tavern_during_outdoor_rain() -> None:
    state = _tavern_seed_state()
    snapshot = derive_environment_snapshot(state["environment"], state["scene_environment_context"])

    assert snapshot["region_id"] == "market_road"
    assert snapshot["weather"]["condition"] == "rain"
    assert snapshot["context"]["exposure"] == "indoor"
    assert snapshot["context"]["shelter"] == "sheltered"
    assert snapshot["visibility"] == "interior"
    assert snapshot["terrain_condition"] == "interior_floor"
    assert snapshot["light_level"] == "tavern_lit"
    assert snapshot["display"]["context"] == "Indoor • Sheltered"


def test_environment_snapshot_derives_mountain_weather_and_calendar() -> None:
    state = _mountain_seed_state()
    snapshot = derive_environment_snapshot(state["environment"], state["scene_environment_context"])

    assert snapshot["climate_profile_id"] == "northern_mountains"
    assert snapshot["calendar"]["day"] == 18
    assert snapshot["calendar"]["time_label"] == "Day 18 • 09:42"
    assert snapshot["weather"]["condition"] == "windy"
    assert snapshot["wind"] in {"moderate", "strong"}
    assert snapshot["visibility"] in {"clear", "dim", "reduced"}
    assert snapshot["terrain_condition"] == "dry"
    assert snapshot["resources"]["water_availability"] == 55


def test_environment_snapshot_temperature_stays_in_profile_season_range() -> None:
    state = _mountain_seed_state()
    snapshot = derive_environment_snapshot(state["environment"], state["scene_environment_context"])

    assert snapshot["calendar"]["season_id"] == "early_spring"
    assert -12 <= snapshot["temperature_c"] <= 2
    assert snapshot["temperature_label"].endswith("°C")


def test_environment_snapshot_prevents_invalid_indoor_weather_combinations() -> None:
    state = _tavern_seed_state()
    environment = deepcopy(state["environment"])
    environment["active_events"] = [
        {
            "id": "weather_test",
            "type": "weather",
            "condition": "storm",
            "intensity": "severe",
            "remaining_minutes": 120,
            "region_id": "market_road",
        }
    ]

    snapshot = derive_environment_snapshot(environment, state["scene_environment_context"])

    assert snapshot["weather"]["condition"] == "storm"
    assert snapshot["context"]["exposure"] == "indoor"
    assert snapshot["visibility"] == "interior"
    assert snapshot["terrain_condition"] == "interior_floor"


def test_environment_snapshot_uses_safe_weather_default_when_no_event_exists() -> None:
    state = _tavern_seed_state()
    environment = deepcopy(state["environment"])
    environment["active_events"] = []

    snapshot = derive_environment_snapshot(environment, state["scene_environment_context"])

    assert snapshot["weather"]["condition"] == "clear"
    assert snapshot["weather"]["intensity"] == "light"
    assert snapshot["display"]["weather"] == "Light Clear"
