from app.rpg.ai.grounding_soft_audit import run_grounding_soft_audit


class FakeChatProvider:
    def __init__(self):
        self.called = False

    def chat_completion(self, *, messages, temperature=None, max_tokens=None):
        self.called = True
        assert messages
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"correction_needed": false, "reason": "grounded", "correction": null}'
                    }
                }
            ]
        }


def test_grounding_soft_audit_supports_chat_completion_provider():
    provider = FakeChatProvider()

    result = run_grounding_soft_audit(
        displayed_payload={
            "format_version": "rpg_narration_v2",
            "narration": "Bran refuses the claim.",
            "action": "No coin changes hands.",
            "npc": {"speaker": "Bran", "line": "No coin changes hands."},
            "reward": None,
            "followup_hooks": [],
        },
        turn_contract={
            "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
            "current_location": "location:rusty_flagon_tavern",
        },
        state_snapshot={},
        llm_gateway=provider,
        grounding_settings={"background_soft_audit": True},
    )

    assert provider.called is True
    assert result["ok"] is True
    assert result["correction_needed"] is False