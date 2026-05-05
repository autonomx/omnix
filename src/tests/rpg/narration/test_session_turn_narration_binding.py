from tests.rpg.manual import turn_execution


def test_manual_turn_preserves_real_runtime_narration_payload(monkeypatch):
    def fake_apply_turn(*, session_id, player_input):
        return {
            "ok": True,
            "narration": "Bran studies the question before lowering his voice.",
            "narration_payload": {
                "format_version": "rpg_narration_v2",
                "narration": "Bran studies the question before lowering his voice.",
                "action": "The question draws a guarded answer.",
                "npc": {
                    "speaker": "Bran",
                    "line": "Tell me exactly what you found.",
                },
                "reward": "",
                "followup_hooks": [],
                "source": "provider_runtime_narration",
                "authoritative_changes": False,
            },
            "npc": {
                "speaker": "Bran",
                "line": "Tell me exactly what you found.",
            },
            "turn_contract": {"player_action": player_input},
            "llm_called": True,
        }

    monkeypatch.setattr(turn_execution, "_get_apply_turn", lambda: fake_apply_turn)
    monkeypatch.setattr(turn_execution, "_record_token_usage", lambda **kwargs: None)
    monkeypatch.setattr(turn_execution.output_artifacts, "_emit", lambda *args, **kwargs: None)

    result = turn_execution._run_one_manual_turn(
        session_id="runtime_narration_binding_test",
        turn="I ask Bran about the witness.",
        turn_index=1,
        scenario_name="runtime_narration_binding_test",
        target_channel="test",
        console_llm=False,
        console_llm_raw=False,
        include_raw_result=True,
    )

    assert result["raw_narration_payload"]["format_version"] == "rpg_narration_v2"
    assert result["raw_narration_payload"]["source"] == "provider_runtime_narration"
    assert result["raw_npc"]["speaker"] == "Bran"
    assert result["raw_npc"]["line"] == "Tell me exactly what you found."
    assert result["llm_called"] is True