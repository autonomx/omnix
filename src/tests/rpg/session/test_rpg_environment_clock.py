from app.rpg.session.environment_time import DEFAULT_TURN_MINUTES


def test_clock_default_step_is_ten_minutes() -> None:
    assert DEFAULT_TURN_MINUTES == 10
