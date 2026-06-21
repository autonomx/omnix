from app.rpg.session.environment_tactics import build_tactical_environment_context


def test_ranged_context_includes_wind_and_visibility() -> None:
    context = build_tactical_environment_context(
        {"wind": "strong", "visibility": "reduced", "terrain_condition": "firm_ground", "context": {"exposure": "outdoor"}}
    )

    assert "ranged_wind_context" in context["combat"]["notes"]
    assert "limited_visibility_context" in context["combat"]["notes"]


def test_stealth_context_includes_darkness_and_weather_noise() -> None:
    context = build_tactical_environment_context(
        {"light_level": "night", "weather": {"condition": "rain"}, "terrain_condition": "firm_ground"}
    )

    assert "darkness_aids_stealth" in context["stealth"]["notes"]
    assert "weather_noise_context" in context["stealth"]["notes"]


def test_difficult_terrain_remains_deterministic_context() -> None:
    first = build_tactical_environment_context({"terrain_condition": "muddy"})
    second = build_tactical_environment_context({"terrain_condition": "muddy"})

    assert first == second
    assert "difficult_terrain_context" in first["combat"]["notes"]
    assert "terrain_leaves_tracks" in first["stealth"]["notes"]
