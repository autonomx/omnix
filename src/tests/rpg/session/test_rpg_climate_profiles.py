from __future__ import annotations

from app.rpg.session.climate_profiles import (
    CLIMATE_PROFILES,
    LOCATION_CLIMATE_PROFILE_IDS,
    SEASON_IDS,
    climate_profile_for_location,
    resolve_climate_profile,
    validate_climate_profile,
)


def test_every_starting_location_resolves_to_registered_climate_profile() -> None:
    expected_locations = {
        "rusty_flagon_tavern",
        "market_district",
        "northern_road",
        "glimmerdeep_pass",
        "old_quarry",
    }

    assert expected_locations.issubset(LOCATION_CLIMATE_PROFILE_IDS)
    for location_id in expected_locations:
        profile_id = climate_profile_for_location(location_id)
        assert profile_id in CLIMATE_PROFILES
        assert resolve_climate_profile(profile_id)["profile"]["id"] == profile_id


def test_climate_profile_lookup_returns_a_copy_and_is_deterministic() -> None:
    first = resolve_climate_profile("northern_mountains")
    second = resolve_climate_profile("northern_mountains")

    assert first == second
    assert first["metadata"] == {"requested_profile_id": "northern_mountains", "fallback_used": False}
    first["profile"]["temperature_ranges_c"]["winter"] = [99, 100]
    assert resolve_climate_profile("northern_mountains")["profile"]["temperature_ranges_c"]["winter"] == [-28, -8]


def test_missing_climate_profile_falls_back_with_warning_metadata() -> None:
    resolution = resolve_climate_profile("unknown_badlands")

    assert resolution["profile_id"] == "temperate_hills"
    assert resolution["profile"]["id"] == "temperate_hills"
    assert resolution["metadata"] == {
        "requested_profile_id": "unknown_badlands",
        "fallback_used": True,
        "warning": "unknown_climate_profile:unknown_badlands",
    }


def test_climate_profiles_cover_required_seasonal_ranges_and_weights() -> None:
    for profile_id, profile in CLIMATE_PROFILES.items():
        assert validate_climate_profile(profile) == []
        assert profile["id"] == profile_id
        assert profile["base_wind"] in {"calm", "light", "moderate", "strong"}
        assert isinstance(profile["hazard_weights"], dict)
        assert isinstance(profile["resource_baselines"], dict)
        for season_id in SEASON_IDS:
            low, high = profile["temperature_ranges_c"][season_id]
            assert low <= high
            assert season_id in profile["sunrise_minutes"]
            assert season_id in profile["sunset_minutes"]
            assert profile["sunrise_minutes"][season_id] < profile["sunset_minutes"][season_id]
            weights = profile["weather_weights"][season_id]
            assert weights
            assert all(weight > 0 for weight in weights.values())


def test_location_profile_lookup_normalizes_labels() -> None:
    assert climate_profile_for_location("Glimmerdeep Pass") == "northern_mountains"
    assert climate_profile_for_location("northern-road") == "road_lowlands"
    assert climate_profile_for_location("unknown location") == "temperate_hills"
