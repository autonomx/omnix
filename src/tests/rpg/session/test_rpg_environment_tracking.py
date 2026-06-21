from app.rpg.session.environment_tracking import build_tracking_environment_context


def test_mud_improves_footprint_visibility() -> None:
    context = build_tracking_environment_context(
        {"terrain_condition": "muddy", "visibility": "normal", "light_level": "daylight"}
    )

    assert context["source"] == "environment_snapshot"
    assert context["footprint_visibility"] == "strong"
    assert "terrain_preserves_tracks" in context["notes"]


def test_snow_improves_footprint_visibility_and_persistence() -> None:
    context = build_tracking_environment_context(
        {"terrain_condition": "deep_snow", "visibility": "normal", "light_level": "daylight"}
    )

    assert context["footprint_visibility"] == "strong"
    assert context["evidence_persistence"] == "long"


def test_rain_reduces_evidence_persistence() -> None:
    context = build_tracking_environment_context(
        {"terrain_condition": "firm_ground", "weather": {"condition": "rain"}}
    )

    assert context["evidence_persistence"] == "short"
    assert "weather_reduces_evidence" in context["notes"]


def test_low_visibility_or_light_reduces_long_distance_perception() -> None:
    fog = build_tracking_environment_context({"visibility": "reduced", "light_level": "daylight"})
    night = build_tracking_environment_context({"visibility": "normal", "light_level": "night"})

    assert fog["long_distance_perception"] == "reduced"
    assert night["long_distance_perception"] == "reduced"
    assert "low_visibility_limits_perception" in fog["notes"]
    assert "low_light_limits_perception" in night["notes"]
