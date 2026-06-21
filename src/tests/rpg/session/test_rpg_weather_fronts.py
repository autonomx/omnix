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
