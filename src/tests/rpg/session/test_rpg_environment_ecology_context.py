from __future__ import annotations

from copy import deepcopy

from app.rpg.session.environment_ecology_context import derive_ecology_context


def _snapshot(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "calendar": {"season_id": "spring"},
        "weather": {"condition": "clear", "intensity": "light"},
        "temperature_c": 14,
        "resources": {
            "water_availability": 60,
            "vegetation": 60,
            "forage_availability": 60,
            "snowpack": 0,
            "drought_pressure": 0,
            "frost_pressure": 0,
        },
    }
    base.update(overrides)
    return base


def test_winter_snow_raises_predator_and_migration_pressure() -> None:
    context = derive_ecology_context(
        _snapshot(
            calendar={"season_id": "winter"},
            weather={"condition": "snow", "intensity": "heavy"},
            temperature_c=-12,
            resources={
                "water_availability": 35,
                "vegetation": 20,
                "forage_availability": 15,
                "snowpack": 85,
                "drought_pressure": 0,
                "frost_pressure": 80,
            },
        )
    )

    assert context["predator_pressure"] in {"high", "severe"}
    assert context["migration_pressure"] in {"high", "severe"}
    assert context["wildlife_activity"] in {"scarce", "dormant"}


def test_drought_lowers_forage_and_raises_water_point_pressure() -> None:
    context = derive_ecology_context(
        _snapshot(
            calendar={"season_id": "summer"},
            temperature_c=33,
            resources={
                "water_availability": 15,
                "vegetation": 25,
                "forage_availability": 20,
                "snowpack": 0,
                "drought_pressure": 90,
                "frost_pressure": 0,
            },
        )
    )

    assert context["water_point_encounter_pressure"] in {"high", "severe"}
    assert context["migration_pressure"] in {"high", "severe"}
    assert context["plant_growth"] in {"scarce", "dormant"}


def test_spring_rain_supports_fish_and_plants() -> None:
    context = derive_ecology_context(
        _snapshot(
            weather={"condition": "rain", "intensity": "moderate"},
            resources={
                "water_availability": 80,
                "vegetation": 75,
                "forage_availability": 70,
                "snowpack": 0,
                "drought_pressure": 0,
                "frost_pressure": 0,
            },
        )
    )

    assert context["fish_activity"] in {"active", "abundant"}
    assert context["plant_growth"] in {"active", "abundant"}
    assert context["herb_availability"] in {"active", "abundant"}


def test_ecology_context_does_not_mutate_snapshot() -> None:
    snapshot = _snapshot()
    original = deepcopy(snapshot)

    context = derive_ecology_context(snapshot)

    assert context["inputs"]["season_id"] == "spring"
    assert snapshot == original
