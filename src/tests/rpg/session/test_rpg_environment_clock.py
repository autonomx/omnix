from copy import deepcopy

from app.rpg.session import durable_store
from app.rpg.session.environment import build_initial_environment_seed_state
from app.rpg.session.environment_time import DEFAULT_TURN_MINUTES, advance_environment_time
from app.rpg.session.service import load_session, save_session


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


def test_same_elapsed_sequence_replays_same_clock_state() -> None:
    first = _seed_environment()
    second = _seed_environment()

    for elapsed_minutes in (10, 10, 20, 5, 45):
        first = advance_environment_time(first, elapsed_minutes=elapsed_minutes)
        second = advance_environment_time(second, elapsed_minutes=elapsed_minutes)

    assert first == second


def test_completed_weather_timer_gets_replacement_and_history() -> None:
    environment = _seed_environment()
    original_event = dict(environment["active_events"][0])
    environment["active_events"][0]["remaining_minutes"] = 10
    environment["event_history_limit"] = 2
    environment["event_history"] = [{"id": "old_weather", "type": "weather"}]

    advanced = advance_environment_time(environment, elapsed_minutes=10)

    assert advanced["absolute_minutes"] == 490
    assert len(advanced["event_history"]) == 2
    assert advanced["event_history"][-1]["id"] == original_event["id"]
    assert advanced["event_history"][-1]["ended_at_minute"] == 490
    assert advanced["active_events"][0]["type"] == "weather"
    assert advanced["active_events"][0]["started_at_minute"] == 490
    assert advanced["active_events"][0]["id"] != original_event["id"]
    assert advanced["active_events"][0]["remaining_minutes"] > 0


def test_completed_weather_timer_replacement_is_deterministic() -> None:
    environment = _seed_environment()
    environment["active_events"][0]["remaining_minutes"] = 10

    first = advance_environment_time(deepcopy(environment), elapsed_minutes=10)
    second = advance_environment_time(deepcopy(environment), elapsed_minutes=10)

    assert first == second


def test_clock_state_survives_session_save_load(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    environment = _seed_environment()
    advanced = advance_environment_time(environment, elapsed_minutes=10)
    session = {
        "session_id": "environment-clock-save-load",
        "state": {"world": {"environment": advanced}, "scene": {"environment_context": {"region_id": "market_road"}}},
        "manifest": {},
        "installed_packs": [],
        "simulation_state": {},
    }

    save_session(session)
    loaded = load_session("environment-clock-save-load")

    assert loaded["state"]["world"]["environment"] == advanced
