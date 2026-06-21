from __future__ import annotations

from app.rpg.session.environment_calendar import (
    DEFAULT_DAYS_PER_YEAR,
    SEASON_ORDER,
    absolute_minutes_for_calendar_day,
    absolute_minutes_for_day_of_year,
    derive_calendar_state,
    derive_initial_day_of_year,
    season_id_for_day,
)


def test_calendar_state_is_deterministic_for_same_absolute_minute_and_config() -> None:
    calendar = {"days_per_year": 360}
    absolute_minutes = absolute_minutes_for_day_of_year(2, 61, 9 * 60 + 5)

    first = derive_calendar_state(absolute_minutes, calendar)
    second = derive_calendar_state(absolute_minutes, calendar)

    assert first == second
    assert first["year"] == 2
    assert first["day_of_year"] == 61
    assert first["minute_of_day"] == 545
    assert first["season_id"] == "spring"
    assert first["season_label"] == "Spring"
    assert first["time_label"].endswith("09:05")


def test_season_id_is_derived_from_boundaries() -> None:
    boundary_days = {
        1: "early_spring",
        60: "early_spring",
        61: "spring",
        120: "spring",
        121: "summer",
        180: "summer",
        181: "early_autumn",
        240: "early_autumn",
        241: "late_autumn",
        300: "late_autumn",
        301: "winter",
        360: "winter",
        361: "early_spring",
    }

    for day_of_year, season_id in boundary_days.items():
        assert season_id_for_day(day_of_year) == season_id
        state = derive_calendar_state(absolute_minutes_for_day_of_year(1, day_of_year))
        assert state["season_id"] == season_id


def test_absolute_minutes_for_campaign_day_preserves_minute_of_day() -> None:
    absolute_minutes = absolute_minutes_for_calendar_day(3, 23 * 60 + 59)
    state = derive_calendar_state(absolute_minutes)

    assert state["day"] == 3
    assert state["minute_of_day"] == 1439
    assert state["time_label"] == "Day 3 • 23:59"


def test_initial_day_of_year_can_be_set_by_contract_day() -> None:
    result = derive_initial_day_of_year(
        campaign_contract={"initial_day_of_year": 242},
        campaign_seed=10,
        region_id="mountain_pass",
    )

    assert result == {"day_of_year": 242, "source": "contract_day_of_year", "season_id": "late_autumn"}


def test_initial_day_of_year_can_be_influenced_by_contract_season() -> None:
    first = derive_initial_day_of_year(
        campaign_contract={"world_options": {"initial_season": "summer"}},
        campaign_seed=12,
        region_id="market_road",
    )
    second = derive_initial_day_of_year(
        campaign_contract={"world_options": {"initial_season": "summer"}},
        campaign_seed=12,
        region_id="market_road",
    )

    assert first == second
    assert first["source"] == "contract_season"
    assert first["season_id"] == "summer"
    assert season_id_for_day(first["day_of_year"]) == "summer"


def test_initial_day_of_year_can_be_influenced_by_region_bias() -> None:
    mountain = derive_initial_day_of_year(
        campaign_contract={},
        campaign_seed=77,
        region_id="mountain_pass",
    )
    town = derive_initial_day_of_year(
        campaign_contract={},
        campaign_seed=77,
        region_id="market_road",
    )

    assert mountain["source"] == "region_bias"
    assert mountain["season_id"] == "winter"
    assert season_id_for_day(mountain["day_of_year"]) == "winter"
    assert town["source"] == "region_bias"
    assert town["season_id"] == "spring"
    assert season_id_for_day(town["day_of_year"]) == "spring"
    assert mountain["day_of_year"] != town["day_of_year"]


def test_seed_default_initial_day_of_year_is_bounded_and_deterministic() -> None:
    first = derive_initial_day_of_year(
        campaign_contract={},
        campaign_seed=5,
        region_id="unknown_region",
    )
    second = derive_initial_day_of_year(
        campaign_contract={},
        campaign_seed=5,
        region_id="unknown_region",
    )

    assert first == second
    assert first["source"] == "seed_default"
    assert 1 <= first["day_of_year"] <= DEFAULT_DAYS_PER_YEAR
    assert first["season_id"] in SEASON_ORDER
