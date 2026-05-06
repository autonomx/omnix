from tests.rpg.autoplay.parallel_pipeline import (
     _combined_payload_has_useful_content,
     _combined_background_llm_job,
     _extract_json_object_from_text,
     _extract_nested_combined_payload,
     _has_expected_combined_provider_keys,
     _salvage_combined_narration_from_text,
 )


class _FakeCombinedProvider:
    provider_name = "fake"
    provider_display_name = "Fake"

    def chat_completion(self, messages, stream=False):
        class Response:
            content = """{
              "narration": "The room settles after the question.",
              "action": "The question is acknowledged.",
              "npc": {"speaker": "Bran", "line": "What do you want to know?"},
              "reward": "",
              "followup_hooks": [],
              "semantic_intent_candidates": [{"intent": "ask", "summary": "The player asks Bran."}],
              "relationship_delta_candidates": [],
              "memory_candidates": [],
              "world_signal_candidates": [],
              "future_hook_candidates": [{"summary": "Bran may answer a follow-up."}]
            }"""
        return Response()


def test_extract_nested_combined_payload_accepts_exact_shape():
    parsed = _extract_json_object_from_text(
        """
        {
          "narration": "Bran watches the room settle.",
          "action": "The question lands.",
          "npc": {"speaker": "Bran", "line": "Keep your voice down."},
          "semantic_intent_candidates": [{"intent": "ask"}],
          "future_hook_candidates": [{"summary": "Bran may answer later."}]
        }
        """
    )
    normalized = _extract_nested_combined_payload(parsed)

    assert normalized["narration"] == "Bran watches the room settle."
    assert normalized["npc"]["speaker"] == "Bran"
    assert normalized["semantic_intent_candidates"][0]["intent"] == "ask"
    assert _combined_payload_has_useful_content(normalized) is True


def test_extract_nested_combined_payload_accepts_narration_payload_and_advisory_wrapper():
    parsed = {
        "narration_payload": {
            "narration": "The tavern quiets.",
            "action": "The player observes the room.",
            "npc": {"speaker": "", "line": ""},
        },
        "advisory": {
            "memory_candidates": [
                {"owner": "bran", "summary": "The player watched the exits."}
            ],
            "future_hook_candidates": [
                {"summary": "Someone may notice the player studying the door."}
            ],
        },
    }

    normalized = _extract_nested_combined_payload(parsed)

    assert normalized["narration"] == "The tavern quiets."
    assert normalized["memory_candidates"][0]["owner"] == "bran"
    assert normalized["future_hook_candidates"][0]["summary"].startswith("Someone may notice")
    assert _combined_payload_has_useful_content(normalized) is True


def test_extract_nested_combined_payload_accepts_result_wrapper():
    parsed = {
        "result": {
            "narration": {
                "narration": "The mill creaks in the wind.",
                "action": "The inspection reveals old tracks.",
            },
            "candidates": [
                {
                    "kind": "semantic_intent",
                    "payload": {"intent": "inspect", "summary": "The player inspects."},
                }
            ],
        }
    }

    normalized = _extract_nested_combined_payload(parsed)

    assert normalized["narration"] == "The mill creaks in the wind."
    assert normalized["candidates"][0]["kind"] == "semantic_intent"
    assert _combined_payload_has_useful_content(normalized) is True


def test_combined_payload_missing_useful_content_is_false():
    assert _combined_payload_has_useful_content({"ok": True}) is False


def test_combined_payload_accepts_latest_lmstudio_shape():
    parsed = {
        "narration": "You address Bran directly.",
        "action": "Bran acknowledges your address and prepares to respond.",
        "npc": {
            "speaker": "Bran",
            "line": "What is it?",
        },
        "reward": "",
        "followup_hooks": [
            {
                "hook_type": "conversation_prompt",
                "description": "Wait for Bran's response or press further.",
            }
        ],
        "semantic_intent_candidates": [
            {"intent": "InquireKnowledge", "confidence": 0.9}
        ],
        "relationship_delta_candidates": [
            {"type": "Trust", "magnitude": 0.1, "target": "Bran"}
        ],
        "memory_candidates": [],
        "world_signal_candidates": [],
        "future_hook_candidates": [],
    }

    normalized = _extract_nested_combined_payload(parsed)

    assert _has_expected_combined_provider_keys(parsed) is True
    assert _combined_payload_has_useful_content(normalized) is True
    assert normalized["narration"] == "You address Bran directly."
    assert normalized["followup_hooks"][0]["hook_type"] == "conversation_prompt"


def test_combined_background_job_marks_provider_success_when_payload_ok():
    result = _combined_background_llm_job(
        queued_at=0.0,
        provider=_FakeCombinedProvider(),
        session_id="s",
        turn_index=1,
        player_action="I ask Bran what he knows.",
        simulation_state={},
        turn_contract={"player_input": "I ask Bran what he knows."},
        semantic_action_record={"semantic_action_type": "ask"},
        prefer_provider=True,
    )

    assert result["ok"] is True
    assert result["source"] == "provider_combined_background_llm"
    assert result["narration_payload"]["source"] == "provider_runtime_narration"
    assert result["candidate_count"] >= 1
    assert result["prompt_metrics"]["total_chars"] > 0


def test_salvage_combined_narration_from_truncated_json():
    raw = '{"narration":"Bran studies you carefully. The tavern noise lowers as he considers the question.","action":"'
    salvaged = _salvage_combined_narration_from_text(raw)
    assert salvaged["ok"] is True
    assert salvaged["partial"] is True
    assert "Bran studies you carefully" in salvaged["narration"]