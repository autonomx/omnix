from app.rpg.session.environment_narration import validate_environment_narration


def test_narration_soft_check_rejects_new_front() -> None:
    snapshot = {"weather": {"condition": "rain"}, "display": {"weather": "Moderate Rain"}}
    phrase = "sudden " + "storm"

    result = validate_environment_narration(phrase, snapshot)

    assert result["ok"] is False
    assert "invented_storm" in result["violations"]
