from app.rpg.session.environment_memory import (
    advance_environment_memory,
    derive_terrain_condition,
    normalize_recent_conditions,
)
from app.rpg.session.environment_snapshot import derive_environment_snapshot


def test_ground_memory_defaults_are_available() -> None:
    memory = normalize_recent_conditions(None)

    assert memory["rain_minutes_24h"] == 0
    assert memory["mud_minutes_72h"] == 0
    assert memory["snowpack_minutes_72h"] == 0
    assert memory["drought_minutes_7d"] == 0


def test_sustained_rain_creates_muddy_ground() -> None:
    memory = advance_environment_memory(None, condition="rain", elapsed_minutes=180)

    assert memory["rain_minutes_24h"] == 180
    assert memory["mud_minutes_72h"] == 180
    assert derive_terrain_condition(condition="rain", recent_conditions=memory) == "muddy"


def test_sustained_dry_weather_creates_dust_and_drought_pressure() -> None:
    memory = advance_environment_memory(None, condition="clear", elapsed_minutes=780)

    assert memory["dry_minutes_72h"] == 780
    assert memory["dust_minutes_72h"] == 780
    assert memory["drought_minutes_7d"] == 780
    assert derive_terrain_condition(condition="clear", recent_conditions=memory) == "dusty"


def test_snow_and_freezing_create_deep_snow() -> None:
    memory = advance_environment_memory(None, condition="snow", elapsed_minutes=120)

    assert memory["snow_minutes_24h"] == 120
    assert memory["freezing_minutes_24h"] == 120
    assert memory["snowpack_minutes_72h"] == 120
    assert derive_terrain_condition(condition="snow", recent_conditions=memory) == "deep_snow"


def test_warm_rain_after_snow_creates_slush() -> None:
    memory = advance_environment_memory(None, condition="snow", elapsed_minutes=120)
    memory = advance_environment_memory(memory, condition="rain", elapsed_minutes=60)

    assert memory["thaw_minutes_24h"] == 60
    assert derive_terrain_condition(condition="rain", recent_conditions=memory) == "slush"


def test_indoor_and_underground_contexts_override_regional_ground() -> None:
    wet_memory = advance_environment_memory(None, condition="rain", elapsed_minutes=180)

    assert (
        derive_terrain_condition(
            condition="rain",
            recent_conditions=wet_memory,
            scene_context={"exposure": "indoor"},
        )
        == "interior_floor"
    )
    assert (
        derive_terrain_condition(
            condition="rain",
            recent_conditions=wet_memory,
            scene_context={"exposure": "underground"},
        )
        == "underground_floor"
    )


def test_snapshot_uses_memory_derived_terrain() -> None:
    memory = advance_environment_memory(None, condition="rain", elapsed_minutes=180)
    snapshot = derive_environment_snapshot(
        {
            "environment_version": 1,
            "region_id": "market_road",
            "climate_profile_id": "temperate_hills",
            "environment_seed": 42,
            "absolute_minutes": 480,
            "calendar": {"year": 1, "day_of_year": 1, "days_per_year": 360},
            "active_events": [
                {
                    "id": "weather_test",
                    "type": "weather",
                    "condition": "rain",
                    "intensity": "moderate",
                    "remaining_minutes": 600,
                    "started_at_minute": 480,
                    "region_id": "market_road",
                }
            ],
            "recent_conditions": memory,
            "event_history": [],
        },
        {"exposure": "outdoor", "shelter": "exposed"},
    )

    assert snapshot["terrain_condition"] == "muddy"
    assert snapshot["display"]["terrain"] == "Muddy"
