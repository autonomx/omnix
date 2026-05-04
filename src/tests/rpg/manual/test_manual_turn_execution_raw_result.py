from tests.rpg.manual import turn_execution


def test_run_one_manual_turn_can_preserve_raw_result(monkeypatch):
    def fake_apply_turn(*, session_id, player_input):
        return {
            "ok": True,
            "narration": "You inspect the tavern.",
            "turn_contract": {"player_action": player_input},
            "simulation_state": {"advanced": True},
        }

    monkeypatch.setattr(turn_execution, "_get_apply_turn", lambda: fake_apply_turn)
    monkeypatch.setattr(turn_execution, "_record_token_usage", lambda **kwargs: None)
    monkeypatch.setattr(turn_execution.output_artifacts, "_emit", lambda *args, **kwargs: None)

    result = turn_execution._run_one_manual_turn(
        session_id="raw_result_test",
        turn="I inspect the tavern.",
        turn_index=1,
        scenario_name="raw_result_test",
        target_channel="test",
        console_llm=False,
        console_llm_raw=False,
        include_raw_result=True,
    )

    assert result["raw_result"]["simulation_state"] == {"advanced": True}
    assert result["raw_narration"] == "You inspect the tavern."
    assert result["raw_turn_contract"]["player_action"] == "I inspect the tavern."


def test_run_one_manual_turn_does_not_preserve_raw_result_by_default(monkeypatch):
    def fake_apply_turn(*, session_id, player_input):
        return {
            "ok": True,
            "narration": "You inspect the tavern.",
            "turn_contract": {"player_action": player_input},
            "simulation_state": {"advanced": True},
        }

    monkeypatch.setattr(turn_execution, "_get_apply_turn", lambda: fake_apply_turn)
    monkeypatch.setattr(turn_execution, "_record_token_usage", lambda **kwargs: None)
    monkeypatch.setattr(turn_execution.output_artifacts, "_emit", lambda *args, **kwargs: None)

    result = turn_execution._run_one_manual_turn(
        session_id="raw_result_test",
        turn="I inspect the tavern.",
        turn_index=1,
        scenario_name="raw_result_test",
        target_channel="test",
        console_llm=False,
        console_llm_raw=False,
    )

    assert "raw_result" not in result
    assert "raw_narration" not in result
    assert "raw_turn_contract" not in result