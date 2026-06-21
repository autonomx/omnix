from __future__ import annotations

from copy import deepcopy

from app.rpg.session.climate_profiles import resolve_climate_profile
from app.rpg.session.environment import build_initial_environment_seed_state
from app.rpg.session.environment_signals import derive_environment_signals
from app.rpg.session.environment_snapshot import derive_environment_snapshot


def _profile(profile_id: str) -> dict[str, object]:
    return resolve_climate_profile(profile_id)["profile"]


def test_environment_signals_apply_season_weather_and_memory() -> None:
    profile = _profile("temperate_hills")
    calendar = {"season_id": "summer"}
    event = {"condition": "clear", "intensity": "moderate"}
    recent = {"dry_minutes_72h": 900, "drought_minutes_7d": 720, "dust_minutes_72h": 240}

    signals = derive_environment_signals(profile, calendar, event, recent)

    assert signals["drought_pressure"] > 10
    assert signals["soil_moisture"] < profile["resource_baselines"]["soil_moisture"]
    assert signals["forage_availability"] < profile["resource_baselines"]["forage_availability"]


def test_environment_signals_apply_snow_memory() -> None:
    profile = _profile("northern_mountains")
    calendar = {"season_id": "winter"}
    event = {"condition": "snow", "intensity": "heavy"}
    recent = {"snowpack_minutes_72h": 360, "freezing_minutes_24h": 240}

    signals = derive_environment_signals(profile, calendar, event, recent)

    assert signals["snowpack"] >= 35
    assert signals["frost_pressure"] >= 35
    assert signals["forage_availability"] < profile["resource_baselines"]["forage_availability"]


def test_environment_signals_are_bounded() -> None:
    profile = {"resource_baselines": {key: 150 for key in ("water_availability", "vegetation", "soil_moisture", "forage_availability")}}
    signals = derive_environment_signals(
        profile,
        {"season_id": "winter"},
        {"condition": "snow", "intensity": "severe"},
        {"snowpack_minutes_72h": 9999, "freezing_minutes_24h": 9999},
    )

    assert set(signals) == {
        "water_availability",
        "vegetation",
        "soil_moisture",
        "forage_availability",
        "snowpack",
        "drought_pressure",
        "flood_pressure",
        "frost_pressure",
    }
    assert all(0 <= value <= 100 for value in signals.values())


def test_snapshot_resources_use_environment_signals_without_persisting_them() -> None:
    state = build_initial_environment_seed_state(
        campaign_seed=42,
        campaign_contract={"campaign_template": "classic_fantasy", "tone": "heroic adventure"},
        location_id="rusty_flagon_tavern",
        location={"time_label": "Day 1 • 08:00", "weather": "Rainy", "location": "Rusty Flagon Tavern"},
    )
    environment = deepcopy(state["environment"])
    environment["recent_conditions"] = {"rain_minutes_24h": 300, "mud_minutes_72h": 180}

    snapshot = derive_environment_snapshot(environment, state["scene_environment_context"])

    assert snapshot["resources"]["soil_moisture"] > 55
    assert snapshot["resources"]["flood_pressure"] > 0
    assert "resources" not in environment
    assert "environment_snapshot" not in environment
