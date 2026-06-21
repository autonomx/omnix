from app.rpg.session.environment_memory import normalize_recent_conditions


def test_ground_memory_defaults_are_available() -> None:
    assert normalize_recent_conditions(None)["rain_minutes_24h"] == 0
