from app.rpg.presentation.current_turn_prompt_contract import build_runtime_current_turn_prompt_contract


def test_current_turn_prompt_contract_marks_short_why_followup_reference():
    contract = build_runtime_current_turn_prompt_contract(
        scene={"title": "The Rusty Flagon Tavern"},
        narration_context={
            "player_input": "but do you know why?",
            "turn_contract": {
                "interpreted_action": {
                    "intent": "ask",
                    "target_id": "npc:Bran",
                    "target_name": "Bran",
                    "followup_reference": {
                        "target_id": "npc:Bran",
                        "target_name": "Bran",
                        "topic": "i ask bran what is going on with Elara and Mira",
                        "source": "recent_dialogue_followup",
                    },
                },
            },
        },
    )

    required = contract["required_response"]

    assert required["must_resolve_short_followup"] is True
    assert required["followup_reference"]["target_name"] == "Bran"
    assert "resolve_short_followup_against_immediately_previous_topic" in contract["required_focus"]
    assert "answer_causal_why_or_state_unknown_cause_with_grounded_lead" in contract["required_focus"]
