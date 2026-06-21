from app.rpg.session.environment import build_initial_environment_seed_state
from app.rpg.session.environment_time import DEFAULT_TURN_MINUTES, advance_environment_time


def _seed_environment() -> dict[str, object]:
    return build_initial_environment_seed_state(
        campaign_seed=42,
        campaign_contract={"campaign_template": "classic_fantasy"},
        location_id="rusty_flagon_tavern",
        location={"time_label": "Day 1 • 08:00", "weather": "Rainy", "location": "Rusty Flagon Tavern"},
    )["environment"]


def test_clock_default_step_is_ten_minutes() -> None:
    assert DEFAULT_TURN_MINUTES == 10


def test_ten_default_steps_advance_one_hundred_minutes() -> None:
    environment = _seed_environment()
    initial_remaining = environment["active_events"][0]["remaining_minutes"]

    for _ in range(10):
        environment = advance_environment_time(environment)

    assert environment["absolute_minutes"] == 580
    assert environment["calendar"] == {"year": 1, "day_of_year": 1, "days_per_year": 360}
    assert environment["active_events"][0]["remaining_minutes"] == initial_remaining - 100
    assert environment["recent_conditions"]["rain_minutes_24h"] == 100
