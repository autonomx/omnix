from app.rpg.session.environment_route_context import build_route_environment_context


def test_mud_affects_route_estimate() -> None:
    context = build_route_environment_context(
        {"terrain_condition": "muddy", "visibility": "normal", "light_level": "daylight"},
        base_minutes=40,
    )

    assert context["source"] == "environment_snapshot"
    assert context["estimated_minutes"] > context["base_minutes"]
    assert "soft_ground_slows_route" in context["notes"]


def test_deep_snow_affects_route_estimate() -> None:
    context = build_route_environment_context(
        {"terrain_condition": "deep_snow", "visibility": "normal", "light_level": "daylight"},
        base_minutes=40,
    )

    assert context["estimated_minutes"] == 60
    assert "deep_snow_slows_route" in context["notes"]
