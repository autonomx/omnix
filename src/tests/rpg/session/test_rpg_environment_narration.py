from app.rpg.session.environment_narration import build_environment_narration_contract


def test_environment_narration_contract_is_read_only() -> None:
    contract = build_environment_narration_contract({"weather": {"condition": "rain"}})

    assert contract["authority"] == "read_only_environment_snapshot"
    assert "create_new_weather" in contract["forbidden"]
