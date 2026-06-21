from app.rpg.session.environment_tactics import build_tactical_environment_context


def test_indoor_context_marks_weather_as_indirect() -> None:
    context = build_tactical_environment_context(
        {"weather": {"condition": "rain"}, "wind": "strong", "context": {"exposure": "indoor"}}
    )

    assert "outdoor_weather_indirect_only" in context["combat"]["notes"]
    assert "ranged_wind_context" not in context["combat"]["notes"]
