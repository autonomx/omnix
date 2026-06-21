from app.rpg.session.environment_route_context import (
    advance_environment_for_route,
    build_route_environment_context,
)


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


def test_low_visibility_and_light_add_route_risk_notes() -> None:
    context = build_route_environment_context(
        {"terrain_condition": "firm_ground", "visibility": "reduced", "light_level": "night"},
        base_minutes=30,
    )

    assert "low_visibility_risk" in context["notes"]
    assert "low_light_risk" in context["notes"]


def test_route_elapsed_time_advances_environment_through_helper() -> None:
    environment = {
        "absolute_minutes": 100,
        "calendar": {"year": 1, "day_of_year": 1, "days_per_year": 360},
        "active_events": [],
        "recent_conditions": {},
        "event_history": [],
    }

    advanced = advance_environment_for_route(environment, elapsed_minutes=45)

    assert advanced["absolute_minutes"] == 145
    assert environment["absolute_minutes"] == 100
