from __future__ import annotations

from app.rpg.session import durable_store
from app.rpg.session.environment import build_initial_environment_seed_state
from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session, start_rpg_preset


RECENT_CONDITION_DEFAULTS = {
    "rain_minutes_24h": 0,
    "snow_minutes_24h": 0,
    "dry_minutes_72h": 0,
    "freezing_minutes_24h": 0,
}

DERIVED_ENVIRONMENT_FIELDS = {
    "temperature",
    "temperature_c",
    "visibility",
    "light",
    "light_level",
    "terrain",
    "terrain_condition",
    "season",
    "season_id",
}


def _request(seed: int, starting_location: str = "rusty_flagon_tavern") -> RpgNewGameRequest:
    return RpgNewGameRequest(
        campaign_template="classic_fantasy",
        tone="heroic adventure",
        starting_location=starting_location,
        seed=seed,
    )


def _tavern_location() -> dict[str, object]:
    return {"time_label": "Day 1 • 08:00", "weather": "Rainy", "location": "Rusty Flagon Tavern"}


def _environment_from_created_game(seed: int, starting_location: str, tmp_path, monkeypatch) -> dict[str, object]:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = create_new_game_session(_request(seed, starting_location))
    assert result["ok"] is True
    return result["game"]


def test_environment_seed_state_is_deterministic_for_same_contract() -> None:
    request = _request(42)
    contract = request.model_dump(mode="json")
    first = build_initial_environment_seed_state(
        campaign_seed=42,
        campaign_contract=contract,
        location_id=request.starting_location,
        location=_tavern_location(),
    )
    second = build_initial_environment_seed_state(
        campaign_seed=42,
        campaign_contract=contract,
        location_id=request.starting_location,
        location=_tavern_location(),
    )

    assert first["environment"] == second["environment"]
    assert first["scene_environment_context"] == second["scene_environment_context"]


def test_environment_seed_state_varies_initial_weather_event_by_seed_within_profile() -> None:
    first_request = _request(41)
    second_request = _request(42)
    first = build_initial_environment_seed_state(
        campaign_seed=41,
        campaign_contract=first_request.model_dump(mode="json"),
        location_id=first_request.starting_location,
        location=_tavern_location(),
    )
    second = build_initial_environment_seed_state(
        campaign_seed=42,
        campaign_contract=second_request.model_dump(mode="json"),
        location_id=second_request.starting_location,
        location=_tavern_location(),
    )

    assert first["environment"]["climate_profile_id"] == second["environment"]["climate_profile_id"]
    assert first["environment"]["active_events"] != second["environment"]["active_events"]


def test_classic_fantasy_tavern_new_game_persists_authoritative_environment(monkeypatch, tmp_path) -> None:
    state = _environment_from_created_game(42, "rusty_flagon_tavern", tmp_path, monkeypatch)
    environment = state["world"]["environment"]
    scene_context = state["scene"]["environment_context"]

    assert environment["environment_version"] == 1
    assert environment["region_id"] == "market_road"
    assert environment["climate_profile_id"] == "temperate_hills"
    assert isinstance(environment["environment_seed"], int)
    assert environment["absolute_minutes"] == 480
    assert environment["calendar"] == {"year": 1, "day_of_year": 1, "days_per_year": 360}
    assert environment["event_history"] == []
    assert environment["recent_conditions"] == RECENT_CONDITION_DEFAULTS
    assert environment["active_events"] == [
        {
            **environment["active_events"][0],
            "type": "weather",
            "condition": "rain",
            "started_at_minute": 480,
            "region_id": "market_road",
        }
    ]
    assert DERIVED_ENVIRONMENT_FIELDS.isdisjoint(environment)

    assert state["world"]["time"] == "Day 1 • 08:00"
    assert state["world"]["weather"] == "Rainy"
    assert scene_context["exposure"] == "indoor"
    assert scene_context["shelter"] == "sheltered"
    assert scene_context["light_override"] == "tavern_lit"
    assert scene_context["region_id"] == environment["region_id"]


def test_mountain_pass_new_game_persists_outdoor_scene_context(monkeypatch, tmp_path) -> None:
    state = _environment_from_created_game(140914, "glimmerdeep_pass", tmp_path, monkeypatch)
    environment = state["world"]["environment"]
    scene_context = state["scene"]["environment_context"]

    assert environment["environment_version"] == 1
    assert environment["region_id"] == "mountain_pass"
    assert environment["climate_profile_id"] == "northern_mountains"
    assert environment["absolute_minutes"] == 582
    assert environment["active_events"][0]["type"] == "weather"
    assert environment["active_events"][0]["condition"] == "windy"
    assert environment["active_events"][0]["region_id"] == "mountain_pass"
    assert DERIVED_ENVIRONMENT_FIELDS.isdisjoint(environment)

    assert state["world"]["time"] == "Day 1 • 09:42"
    assert state["world"]["temperature"] == -12
    assert scene_context["exposure"] == "outdoor"
    assert scene_context["shelter"] == "exposed"
    assert scene_context["region_id"] == environment["region_id"]


def test_demo_preset_normalization_gets_environment_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)

    result = start_rpg_preset("demo_glimmerdeep_pass_lvl14")

    assert result["ok"] is True
    state = result["game"]
    environment = state["world"]["environment"]
    assert environment["region_id"] == "mountain_pass"
    assert environment["climate_profile_id"] == "northern_mountains"
    assert state["scene"]["environment_context"]["exposure"] == "outdoor"
