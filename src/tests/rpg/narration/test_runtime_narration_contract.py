from app.rpg.narration.runtime_narration_contract import (
    NARRATION_FORMAT_VERSION,
    build_deterministic_narration_payload,
    build_runtime_narration_payload,
    is_echo_narration,
    repair_provider_narration_payload,
    validate_narration_payload,
)


class FakeProvider:
    def chat(self, messages, max_tokens=320):
        return {
            "content": (
                '{"format_version":"rpg_narration_v2",'
                '"narration":"Bran studies the question before lowering his voice.",'
                '"action":"The question draws a guarded answer.",'
                '"npc":{"speaker":"Bran","line":"Tell me exactly what you found."},'
                '"reward":"",'
                '"followup_hooks":[]}'
            )
        }


class EchoProvider:
    def chat(self, messages, max_tokens=320):
        return {
            "content": (
                '{"format_version":"rpg_narration_v2",'
                '"narration":"I ask Bran about the witness.",'
                '"action":"",'
                '"npc":{"speaker":"Bran","line":"Ok."},'
                '"reward":"",'
                '"followup_hooks":[]}'
            )
        }


class GenerateResponseProvider:
    def generate_response(self, prompt, max_tokens=320):
        return {
            "text": (
                '{"format_version":"rpg_narration_v2",'
                '"narration":"Bran answers with a guarded glance toward the room.",'
                '"action":"The question receives a cautious answer.",'
                '"npc":{"speaker":"Bran","line":"I heard enough to worry about the road."},'
                '"reward":"",'
                '"followup_hooks":[]}'
            )
        }


class NoSupportedMethodProvider:
    def unsupported(self, prompt):
        return "nope"


class ChildClient:
    def generate_response(self, prompt, max_tokens=320):
        return {
            "response": (
                '{"format_version":"rpg_narration_v2",'
                '"narration":"Bran gives a careful answer from behind the bar.",'
                '"action":"The question receives a useful but cautious answer.",'
                '"npc":{"speaker":"Bran","line":"The road has been wrong since dusk."},'
                '"reward":"",'
                '"followup_hooks":[]}'
            )
        }


class WrapperProvider:
    def __init__(self):
        self.client = ChildClient()


class ChatCompletionToDictProvider:
    def chat_completion(self, messages, max_tokens=320):
        # Simulate LMStudioProvider-style wrappers that expect message objects.
        rendered = [message.to_dict() for message in messages]
        assert rendered[0]["role"] == "system"
        assert rendered[1]["role"] == "user"
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"format_version":"rpg_narration_v2",'
                            '"narration":"Bran answers after checking who is listening.",'
                            '"action":"The question receives a cautious answer.",'
                            '"npc":{"speaker":"Bran","line":"The traveler was not moving like a casual guest."},'
                            '"reward":"",'
                            '"followup_hooks":[]}'
                        )
                    }
                }
            ]
        }


def test_deterministic_narration_payload_for_social_turn_has_npc_line():
    payload = build_deterministic_narration_payload(
        player_action="I ask Bran about the witness.",
        simulation_state={},
        turn_contract={},
    )

    assert payload["format_version"] == NARRATION_FORMAT_VERSION
    assert payload["npc"]["speaker"] == "Bran"
    assert payload["npc"]["line"]
    assert payload["reward"] == ""
    assert payload["followup_hooks"] == []
    assert payload["authoritative_changes"] is False


def test_validate_narration_payload_rejects_echo_and_rewards():
    result = validate_narration_payload(
        {
            "format_version": "rpg_narration_v2",
            "narration": "I ask Bran about the witness.",
            "action": "",
            "npc": {},
            "reward": "100 gold",
            "followup_hooks": [],
        },
        player_action="I ask Bran about the witness.",
    )

    assert result["ok"] is False
    assert "echoed_player_action" in result["errors"]
    assert "reward_not_empty" in result["errors"]


def test_provider_runtime_narration_payload_accepts_valid_provider_json():
    payload = build_runtime_narration_payload(
        provider=FakeProvider(),
        player_action="I ask Bran about the witness.",
        simulation_state={},
        turn_contract={},
        prefer_provider=True,
    )

    assert payload["source"] == "provider_runtime_narration"
    assert payload["npc"]["speaker"] == "Bran"
    assert payload["npc"]["line"] == "Tell me exactly what you found."


def test_runtime_narration_falls_back_when_provider_echoes_player_action():
    payload = build_runtime_narration_payload(
        provider=EchoProvider(),
        player_action="I ask Bran about the witness.",
        simulation_state={},
        turn_contract={},
        prefer_provider=True,
    )

    assert payload["source"] == "deterministic_runtime_narration_fallback"
    assert not is_echo_narration(
        player_action="I ask Bran about the witness.",
        narration=payload["narration"],
    )
    assert payload["runtime_narration_diagnostics"]["provider_attempted"] is True
    assert payload["runtime_narration_diagnostics"]["fallback_used"] is True


def test_runtime_narration_records_provider_not_available():
    payload = build_runtime_narration_payload(
        provider=None,
        player_action="I ask Bran about the witness.",
        simulation_state={},
        turn_contract={},
        prefer_provider=True,
    )

    diagnostics = payload["runtime_narration_diagnostics"]
    assert diagnostics["provider_requested"] is True
    assert diagnostics["provider_present"] is False
    assert diagnostics["fallback_used"] is True
    assert "provider_not_available" in diagnostics["provider_errors"]


def test_runtime_narration_supports_generate_response_provider_wrapper():
    payload = build_runtime_narration_payload(
        provider=GenerateResponseProvider(),
        player_action="I ask Bran about the road.",
        simulation_state={},
        turn_contract={},
        prefer_provider=True,
    )

    diagnostics = payload["runtime_narration_diagnostics"]
    assert payload["source"] == "provider_runtime_narration"
    assert payload["npc"]["speaker"] == "Bran"
    assert payload["npc"]["line"] == "I heard enough to worry about the road."
    assert diagnostics["provider_valid"] is True
    assert diagnostics["provider_call_diagnostics"]["selected_method"] == "root.generate_response"


def test_runtime_narration_reports_no_supported_provider_method():
    payload = build_runtime_narration_payload(
        provider=NoSupportedMethodProvider(),
        player_action="I ask Bran about the road.",
        simulation_state={},
        turn_contract={},
        prefer_provider=True,
    )

    diagnostics = payload["runtime_narration_diagnostics"]
    assert payload["source"] == "deterministic_runtime_narration_fallback"
    assert "provider_has_no_supported_call_method" in diagnostics["provider_errors"]
    assert diagnostics["fallback_used"] is True


def test_runtime_narration_resolves_child_client_provider_method():
    payload = build_runtime_narration_payload(
        provider=WrapperProvider(),
        player_action="I ask Bran about the road.",
        simulation_state={},
        turn_contract={},
        prefer_provider=True,
    )

    diagnostics = payload["runtime_narration_diagnostics"]
    assert payload["source"] == "provider_runtime_narration"
    assert payload["npc"]["speaker"] == "Bran"
    assert payload["npc"]["line"] == "The road has been wrong since dusk."
    assert diagnostics["provider_valid"] is True
    assert diagnostics["provider_call_diagnostics"]["selected_method"] == "client.generate_response"


def test_runtime_narration_supports_chat_completion_message_objects():
    payload = build_runtime_narration_payload(
        provider=ChatCompletionToDictProvider(),
        player_action="I ask Bran about the traveler.",
        simulation_state={},
        turn_contract={},
        prefer_provider=True,
    )

    diagnostics = payload["runtime_narration_diagnostics"]
    assert payload["source"] == "provider_runtime_narration"
    assert payload["npc"]["speaker"] == "Bran"
    assert payload["npc"]["line"] == "The traveler was not moving like a casual guest."
    assert diagnostics["provider_valid"] is True
    assert diagnostics["provider_call_diagnostics"]["selected_method"] == "root.chat_completion"


def test_repair_provider_payload_clears_authoritative_fields():
    repaired = repair_provider_narration_payload(
        {
            "format_version": "rpg_narration_v2",
            "narration": "Bran answers carefully.",
            "action": "Persuasion attempt succeeded partially (Roll: 6 vs DC: 10)",
            "npc": {"speaker": "Bran", "line": "Tell me more."},
            "reward": "100 gold",
            "followup_hooks": ["Invented hook"],
            "authoritative_changes": True,
        },
        player_action="I ask Bran about the witness.",
        turn_contract={"summary": "Bran considers the question."},
    )

    result = validate_narration_payload(
        repaired,
        player_action="I ask Bran about the witness.",
    )

    assert result["ok"] is True
    assert repaired["reward"] == ""
    assert repaired["followup_hooks"] == []
    assert repaired["authoritative_changes"] is False
    assert repaired["action"] == "Bran considers the question."
    assert "cleared_reward" in repaired["_repair_actions"]
    assert "cleared_followup_hooks" in repaired["_repair_actions"]
    assert "replaced_action" in repaired["_repair_actions"]


def test_runtime_narration_accepts_repaired_provider_payload():
    class HookyProvider:
        def chat_completion(self, messages, max_tokens=320):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"format_version":"rpg_narration_v2",'
                                '"narration":"Bran answers carefully.",'
                                '"action":"Persuasion attempt succeeded partially (Roll: 6 vs DC: 10)",'
                                '"npc":{"speaker":"Bran","line":"Tell me more."},'
                                '"reward":"",'  # Note: empty string is ok, but hooks are not
                                '"followup_hooks":["Invented hook"]}'
                            )
                        }
                    }
                ]
            }

    payload = build_runtime_narration_payload(
        provider=HookyProvider(),
        player_action="I ask Bran about the witness.",
        simulation_state={},
        turn_contract={"summary": "Bran considers the question."},
        prefer_provider=True,
    )

    diagnostics = payload["runtime_narration_diagnostics"]
    assert payload["source"] == "provider_runtime_narration"
    assert payload["followup_hooks"] == []
    assert payload["action"] == "Bran considers the question."
    assert diagnostics["provider_valid"] is True
    assert diagnostics["provider_repaired"] is True
    assert "cleared_followup_hooks" in diagnostics["provider_repair_actions"]