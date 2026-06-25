from __future__ import annotations


def test_semantic_prompt_warns_against_player_speaker_visible_response(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.npc_dialogue_repair_hook import install_npc_dialogue_repair_hook
    from app.rpg.ai import semantic_action_intelligence as semantic

    monkeypatch.delattr(runtime, "_omnix_npc_dialogue_repair_hook_installed", raising=False)
    install_npc_dialogue_repair_hook()

    prompt = semantic.build_semantic_action_prompt(
        "i ask bran how his day is going",
        {"scene": {"location": "Rusty Flagon Tavern"}},
        {},
        {"action_type": "social_activity", "target_id": "bran", "target_name": "Bran"},
    )

    assert "npc.speaker must be the NPC who answers" in prompt
    assert "never Player" in prompt


def test_malformed_player_speaker_visible_response_is_rejected(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.npc_dialogue_repair_hook import install_npc_dialogue_repair_hook
    from app.rpg.ai import semantic_action_intelligence as semantic

    monkeypatch.delattr(runtime, "_omnix_npc_dialogue_repair_hook_installed", raising=False)
    install_npc_dialogue_repair_hook()

    advisory = semantic.normalize_semantic_action_advisory(
        {
            "action_intent": {
                "action_type": "social_activity",
                "target_id": "bran",
                "target_name": "Bran",
                "stateful": False,
                "needs_runtime_resolution": False,
            },
            "semantic_advisory": {
                "semantic_family": "social",
                "interaction_mode": "direct",
                "utterance_mode": "wellbeing_inquiry",
                "risk_domain": "none",
                "intent_summary": "The player asks Bran about his day.",
                "evidence_spans": ["how his day is going"],
            },
            "dialogue_gate": {"safe_to_display_now": True, "reason": "safe small talk", "risk_flags": []},
            "final_narration_candidate": {
                "narration": "You ask Bran how his day is going.",
                "npc": {"speaker": "Player", "line": "Bran, how is your day going?"},
            },
        },
        {"action_type": "social_activity", "target_id": "bran", "target_name": "Bran"},
    )

    assert advisory["visible_response"] == {}
    assert advisory["final_narration_candidate"] == {}
    assert advisory["direct_response_gate"]["safe_to_display_now"] is False
    assert "invalid_npc_visible_response" in advisory["direct_response_gate"]["risk_flags"]


def test_generic_direct_question_fallback_answers_without_scenario_specific_hook(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.npc_dialogue_repair_hook import install_npc_dialogue_repair_hook

    monkeypatch.delattr(runtime, "_omnix_npc_dialogue_repair_hook_installed", raising=False)
    install_npc_dialogue_repair_hook()

    topic, line = runtime._safe_dialogue_fallback_line(
        speaker="Bran",
        profile={"role": "innkeeper"},
        player_input="i ask bran, any troubles lately?",
    )

    assert topic == "concern_inquiry"
    assert "ask that plainly again" not in line.lower()
    assert "bran" not in line.lower()
    assert "innkeeper" in line.lower()
