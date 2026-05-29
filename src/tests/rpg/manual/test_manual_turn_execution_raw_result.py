from tests.rpg.manual import turn_execution
from tests.rpg.manual.summary_sanitizer import sanitize_turn_for_summary


def test_run_one_manual_turn_can_preserve_raw_result(monkeypatch):
    def fake_apply_turn(*, session_id, player_input, **kwargs):
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
    def fake_apply_turn(*, session_id, player_input, **kwargs):
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


def test_run_one_manual_turn_preserves_raw_npc_payload_when_requested(monkeypatch):
    def fake_apply_turn(*, session_id, player_input, **kwargs):
        return {
            "ok": True,
            "narration_payload": {
                "narration": "Bran leans in.",
                "npc": {"speaker": "Bran", "line": "The witness went outside."},
            },
            "npc": {"speaker": "Bran", "line": "The witness went outside."},
            "turn_contract": {"player_action": player_input},
        }

    monkeypatch.setattr(turn_execution, "_get_apply_turn", lambda: fake_apply_turn)
    monkeypatch.setattr(turn_execution, "_record_token_usage", lambda **kwargs: None)
    monkeypatch.setattr(turn_execution.output_artifacts, "_emit", lambda *args, **kwargs: None)

    result = turn_execution._run_one_manual_turn(
        session_id="raw_npc_test",
        turn="I ask Bran about the witness.",
        turn_index=1,
        scenario_name="raw_npc_test",
        target_channel="test",
        console_llm=False,
        console_llm_raw=False,
        include_raw_result=True,
    )

    assert result["raw_npc"]["speaker"] == "Bran"
    assert result["raw_narration_payload"]["npc"]["line"] == "The witness went outside."


def test_console_log_surfaces_first_call_visible_npc_line(capsys):
    turn_execution._log_llm_response(
        scope="service",
        label="bran_opinion",
        turn=1,
        player_input="Bran, what do you think about sword combat styles?",
        result={
            "narration": "Bran answers carefully.",
            "visible_response": {
                "narration": "Bran answers carefully.",
                "npc": {
                    "speaker": "Bran",
                    "line": "Styles have their place, but keep your feet under you.",
                },
            },
            "llm_called": True,
            "llm_purpose": "first_call_safe_dialogue_fallback",
        },
        raw=False,
    )

    output = capsys.readouterr().out

    assert "FINAL RESPONSE:" in output
    assert "Bran answers carefully." in output
    assert 'Bran: "Styles have their place, but keep your feet under you."' in output


def test_summary_debug_extracts_first_call_visible_npc_line():
    summary = sanitize_turn_for_summary(
        {
            "turn_index": 1,
            "player_input": "Bran, what do you think about sword combat styles?",
            "result": {
                "narration": "Bran answers carefully.",
                "visible_response": {
                    "narration": "Bran answers carefully.",
                    "npc": {
                        "speaker": "Bran",
                        "line": "Styles have their place, but keep your feet under you.",
                    },
                },
            },
        },
        detail="debug",
    )

    assert summary["extracted"]["npc_speaker"] == "Bran"
    assert summary["extracted"]["npc_line"] == "Styles have their place, but keep your feet under you."
