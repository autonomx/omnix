from app.rpg.session.environment_narration import validate_environment_narration


def _snapshot() -> dict[str, object]:
    return {
        "weather": {"condition": "rain"},
        "display": {"weather": "Moderate Rain", "terrain": "Muddy", "context": "Indoor • Sheltered"},
    }


def test_narration_soft_check_rejects_new_front() -> None:
    phrase = "sudden " + "storm"

    result = validate_environment_narration(phrase, _snapshot())

    assert result["ok"] is False
    assert "invented_storm" in result["violations"]
    assert "Moderate Rain" in result["corrected_narration"]


def test_narration_detects_weather_contradiction() -> None:
    result = validate_environment_narration("The clear sky opens over sunny and dry stones.", _snapshot())

    assert result["ok"] is False
    assert "contradicts_weather" in result["violations"]


def test_narration_detects_time_or_season_mutation() -> None:
    result = validate_environment_narration("Hours pass and the season changes before you.", _snapshot())

    assert result["ok"] is False
    assert "mutates_time_or_season" in result["violations"]


def test_grounded_narration_passes_soft_check() -> None:
    result = validate_environment_narration("Rain taps the shutters while mud clings outside.", _snapshot())

    assert result["ok"] is True
    assert result["violations"] == []
