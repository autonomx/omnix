from __future__ import annotations


class _OpenAiStyleGateway:
    def complete(self, prompt: str) -> dict:
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "```json\n{\n  \"action_intent\": {\n    \"action_type\": \"social_activity\",\n    \"target_id\": \"bran\",\n    \"target_name\": \"Bran\",\n    \"stateful\": false,\n    \"needs_runtime_resolution\": false\n  },\n  \"semantic_advisory\": {\n    \"semantic_family\": \"social\",\n    \"interaction_mode\": \"direct\",\n    \"activity_label\": \"querying_rumors\",\n    \"utterance_mode\": \"casual_conversation\",\n    \"literal_action_requested\": false,\n    \"state_mutation_requested\": false,\n    \"risk_domain\": \"none\",\n    \"intent_summary\": \"The player asks Bran about recent rumors.\",\n    \"evidence_spans\": [\"I ask Bran, any rumors lately?\"]\n  },\n  \"dialogue_gate\": {\n    \"safe_to_display_now\": true,\n    \"reason\": \"non-mutating NPC question\",\n    \"risk_flags\": [\"none\"]\n  },\n  \"final_narration_candidate\": {\n    \"narration\": \"\",\n    \"npc\": {\n      \"speaker\": \"Bran\",\n      \"line\": \"Rumors? Ask plain what kind you want.\"\n    }\n  },\n  \"reason\": \"direct non-mutating social inquiry\"\n}\n```",
                        "tool_calls": [],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }


def test_semantic_runtime_hook_reads_choices_content_not_tool_calls() -> None:
    from app.rpg.session.visible_response_runtime_hook import install_visible_response_runtime_guard

    install_visible_response_runtime_guard()

    from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory

    advisory = get_semantic_action_advisory(
        llm_gateway=_OpenAiStyleGateway(),
        player_input="I ask Bran, any rumors lately?",
        simulation_state={},
        runtime_state={},
        candidate_action={},
    )

    diagnostics = advisory["first_call_grounding_diagnostics"]
    assert diagnostics["provider_parse_ok"] is True
    assert diagnostics["provider_status"] == "valid_json"
    assert diagnostics["raw_text"] != "[]"
    assert diagnostics["raw_text"].startswith("```json")
    assert advisory["target_name"] == "Bran"
    assert advisory["visible_response"]["npc"]["line"] == "Rumors? Ask plain what kind you want."


def test_first_call_selection_rejects_bracket_container_visible_line() -> None:
    from app.rpg.session.visible_response_runtime_hook import install_visible_response_runtime_guard

    install_visible_response_runtime_guard()

    from app.rpg.session import first_call_dialogue

    selected = first_call_dialogue.choose_first_call_visible_response(
        semantic_advisory={
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "stateful": False,
            "needs_runtime_resolution": False,
            "target_id": "bran",
            "target_name": "Bran",
            "direct_response_gate": {"safe_to_display_now": True, "reason": "safe"},
            "visible_response": {"narration": "", "npc": {"speaker": "Bran", "line": "[]"}},
        }
    )

    assert selected["consumable"] is False
    assert selected["source"] == "visible_response_contract_guard_v1"
    assert selected["rejection_reasons"] == ["semantic_advisory:invalid_visible_response_text"]
