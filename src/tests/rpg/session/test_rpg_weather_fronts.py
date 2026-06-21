from app.rpg.session.climate_profiles import CLIMATE_PROFILES
from app.rpg.session.environment_weather import generate_weather_event


def test_weather_front_generation_is_deterministic() -> None:
    first = generate_weather_event(
        environment_seed=123,
        region_id="market_road",
        climate_profile_id="temperate_hills",
        absolute_minutes=480,
    )
    second = generate_weather_event(
        environment_seed=123,
        region_id="market_road",
        climate_profile_id="temperate_hills",
        absolute_minutes=480,
    )

    assert first == second
    assert first["type"] == "weather"
    assert first["remaining_minutes"] >= 360


def test_weather_front_uses_climate_profile_season_weights() -> None:
    event = generate_weather_event(
        environment_seed=345,
        region_id="mountain_pass",
        climate_profile_id="northern_mountains",
        absolute_minutes=(300 * 1440),
    )

    winter_weights = CLIMATE_PROFILES["northern_mountains"]["weather_weights"]["winter"]
    assert event["condition"] in winter_weights
    assert event["season_id"] == "winter"
    assert event["climate_profile_id"] == "northern_mountains"


def test_weather_front_supports_required_conditions_with_overrides() -> None:
    required_conditions = {"rain", "snow", "fog", "clear", "windy", "storm"}
    for index, condition in enumerate(sorted(required_conditions)):
        event = generate_weather_event(
            environment_seed=900 + index,
            region_id="market_road",
            climate_profile_id="temperate_hills",
            absolute_minutes=480,
            sequence=index,
            condition_override=condition,
        )
        assert event["condition"] == condition
        assert event["remaining_minutes"] >= 360
