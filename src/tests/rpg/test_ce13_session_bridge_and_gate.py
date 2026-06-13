from __future__ import annotations

import json

from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory
from app.rpg.session import interactive_first_call_runtime as interactive_runtime
from app.rpg.session.first_call_dialogue import choose_first_call_visible_response
from tests.rpg.manual.dialogue_m16_m18_checks import run_dialogue_m16_m18_check


def _bran_diagnostics(player_input="Bran, what do you think about sword combat styles?"):
    return {
        "format_version": "first_call_grounding_diagnostics_v1",
        "turn_grounding_packet": {
            "format_version": "turn_grounding_packet_v1",
            "player_input": player_input,
            "priority_context": {"addressed_npc_ids": ["npc:bran"]},
            "npc_context": {
                "addressed_npcs": [
                    {
                        "id": "npc:bran",
                        "name": "Bran",
                        "visible_profile": {"public_biography": "Bran guarded caravans before running the tavern."},
                        "personality_profile": {
                            "summary": "Bran is practical and road-worn.",
                            "speech_examples": ["A pretty stance means nothing if your feet slip in the mud."],
                        },
                        "biography": {"public": "Bran guarded caravans before running the tavern."},
                    }
                ]
            },
        },
    }


def test_visible_response_gate_rejects_player_only_restatement_for_direct_npc_question():
    selected = choose_first_call_visible_response(
        semantic_advisory={
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "You turn to Bran and ask what he thinks about sword combat styles.",
                "npc": {"speaker": "", "line": ""},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        }
    )

    assert selected["consumable"] is False
    assert any("missing_npc_speaker" in row for row in selected["rejection_reasons"])


def test_visible_response_gate_requires_matching_addressed_npc_speaker():
    selected = choose_first_call_visible_response(
        semantic_advisory={
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "Bran answers plainly.",
                "npc": {"speaker": "Player", "line": "I think sword styles are interesting."},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        }
    )

    assert selected["consumable"] is False
    assert any("speaker_does_not_match_addressed_npc" in row for row in selected["rejection_reasons"])


def test_visible_response_gate_accepts_matching_bran_line():
    selected = choose_first_call_visible_response(
        semantic_advisory={
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "Bran taps the bar once before answering.",
                "npc": {"speaker": "Bran", "line": "Styles help, but mud and panic test your feet first."},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        }
    )

    assert selected["consumable"] is True
    assert selected["npc"]["speaker"] == "Bran"


def test_interactive_wrapper_uses_session_override_for_first_call_grounding(monkeypatch):
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "social_activity",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {},
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )

    observed = {}

    def fake_semantic(**kwargs):
        observed["simulation_state"] = kwargs["simulation_state"]
        return {
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "Bran answers plainly.",
                "npc": {"speaker": "Bran", "line": "Styles help, but your feet matter first."},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        }

    monkeypatch.setattr(interactive_runtime, "get_semantic_action_advisory", fake_semantic)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input="Bran, what do you think about sword combat styles?",
        session_override={
            "session_id": "manual_service_bran_test",
            "simulation_state": {"npc_index": {"npc:bran": {"id": "npc:bran", "name": "Bran"}}},
            "runtime_state": {"tick": 0},
        },
    )

    assert result["consumed"] is True
    assert observed["simulation_state"]["npc_index"]["npc:bran"]["name"] == "Bran"
    assert result["first_call_grounding_diagnostics"]["turn_grounding_packet"]["format_version"] == "turn_grounding_packet_v1"


def test_interactive_wrapper_consumes_valid_provider_visible_response(monkeypatch):
    class FakeGateway:
        def complete(self, prompt):
            return {
                "text": json.dumps(
                    {
                        "action_type": "social_activity",
                        "semantic_family": "social",
                        "interaction_mode": "direct",
                        "target_id": "npc:bran",
                        "target_name": "Bran",
                        "stateful": False,
                        "needs_runtime_resolution": False,
                        "visible_response": {
                            "narration": "Bran answers with road-worn certainty.",
                            "npc": {
                                "speaker": "Bran",
                                "line": "Styles matter less than keeping your feet under you when the road turns slick.",
                            },
                        },
                        "direct_response_gate": {
                            "safe_to_display_now": True,
                            "reason": "non_mutating_opinion_dialogue",
                            "risk_flags": [],
                        },
                        "reason": "Direct non-stateful NPC opinion question.",
                    }
                )
            }

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: FakeGateway())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("interactive first-call should use one semantic LLM call")
        ),
    )

    def fail_if_called(**kwargs):
        raise AssertionError("canonical runtime should not handle valid first-call NPC dialogue")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input="Bran, what do you think about sword combat styles?",
        session_override={
            "session_id": "manual_service_bran_test",
            "simulation_state": {
                "npc_index": {
                    "npc:bran": {
                        "id": "npc:bran",
                        "name": "Bran",
                        "biography": {"public": "Bran guarded caravans before running the tavern."},
                        "personality_profile": {
                            "summary": "Bran is practical and road-worn.",
                            "speech_examples": ["A pretty stance means nothing if your feet slip in the mud."],
                        },
                    }
                }
            },
            "runtime_state": {"tick": 0},
        },
    )

    diagnostics = result["first_call_grounding_diagnostics"]

    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_interpretive_dialogue"
    assert result["result"]["visible_interaction_reason"] == "first_call_non_stateful_dialogue"
    assert result["npc"]["speaker"] == "Bran"
    assert "road turns slick" in result["npc"]["line"]
    assert result["grounding_validation"]["turn_grounding_packet"]["format_version"] == "turn_grounding_packet_v1"
    assert result["grounding_validation"]["first_call_grounding_diagnostics"]["provider_status"] == "valid_json"
    assert diagnostics["provider_called"] is True
    assert diagnostics["provider_status"] == "valid_json"
    assert diagnostics["provider_parse_ok"] is True
    assert diagnostics["provider_visible_response_present"] is True
    assert diagnostics["provider_non_stateful"] is True
    assert diagnostics["raw_text_length"] > 0


def test_first_call_diagnostics_distinguish_malformed_provider_response():
    class FakeGateway:
        def complete(self, prompt):
            return {"text": "this is not json"}

    advisory = get_semantic_action_advisory(
        llm_gateway=FakeGateway(),
        player_input="Bran, what do you think about sword combat styles?",
        simulation_state={},
        runtime_state={},
        candidate_action={"action_type": "social_activity", "target_id": "npc:bran", "target_name": "Bran"},
    )
    diagnostics = advisory["first_call_grounding_diagnostics"]

    assert diagnostics["provider_called"] is True
    assert diagnostics["provider_status"] == "malformed_json"
    assert diagnostics["provider_parse_ok"] is False
    assert diagnostics["provider_malformed_json"] is True
    assert diagnostics["provider_response_empty"] is False
    assert diagnostics["raw_text"] == "this is not json"


def test_first_call_diagnostics_distinguish_empty_provider_response():
    class FakeGateway:
        def complete(self, prompt):
            return {"text": ""}

    advisory = get_semantic_action_advisory(
        llm_gateway=FakeGateway(),
        player_input="Bran, what do you think about sword combat styles?",
        simulation_state={},
        runtime_state={},
        candidate_action={"action_type": "social_activity", "target_id": "npc:bran", "target_name": "Bran"},
    )
    diagnostics = advisory["first_call_grounding_diagnostics"]

    assert diagnostics["provider_called"] is True
    assert diagnostics["provider_status"] == "empty_response"
    assert diagnostics["provider_parse_ok"] is False
    assert diagnostics["provider_malformed_json"] is False
    assert diagnostics["provider_response_empty"] is True
    assert diagnostics["raw_text_length"] == 0


def test_interactive_wrapper_safe_fallback_blocks_canonical_combat_fallback(monkeypatch):
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "social_activity",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {},
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "You turn to Bran and ask about sword styles.",
                "npc": {"speaker": "", "line": ""},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )

    def fail_if_called(**kwargs):
        raise AssertionError("canonical runtime should not handle rejected non-stateful NPC dialogue")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input="Bran, what do you think about sword combat styles?",
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_safe_dialogue_fallback"
    assert result["npc"]["speaker"] == "Bran"
    assert "mud" in result["npc"]["line"].lower()
    assert result["grounding_validation"]["selected_candidate"] == "primary"
    assert result["grounding_validation"]["first_call_grounding_packet_version"] == "turn_grounding_packet_v1"


def test_direct_npc_question_packet_blocks_canonical_runtime_even_when_advisory_defaults_stateful(monkeypatch):
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "semantic_family": "observation",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )

    def fail_if_called(**kwargs):
        raise AssertionError("canonical runtime should not handle grounded direct NPC question")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input="Bran, what do you think about sword combat styles?",
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_safe_dialogue_fallback"
    assert result["npc"]["speaker"] == "Bran"
    assert result["result"]["visible_interaction_reason"] == "first_call_safe_dialogue_fallback"


def test_valid_provider_food_question_stays_llm_dialogue(monkeypatch):
    player_input = "Bran, what food do you sell?"

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "social_activity",
            "stateful": False,
            "needs_runtime_resolution": False,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "Bran glances toward the kitchen before answering.",
                "npc": {"speaker": "Bran", "line": "There is stew most days, bread if the baker came through, and ale enough."},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )

    def fail_if_called(**kwargs):
        raise AssertionError("canonical runtime should not handle valid first-call food dialogue")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input=player_input,
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    line = result["npc"]["line"].lower()

    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_interpretive_dialogue"
    assert result["result"]["visible_interaction_reason"] == "first_call_non_stateful_dialogue"
    assert "stew" in line
    assert "sword" not in line


def test_direct_npc_food_question_safe_fallback_is_topic_aware(monkeypatch):
    player_input = "Bran, what food do you sell at the tavern?"

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "semantic_family": "observation",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )

    def fail_if_called(**kwargs):
        raise AssertionError("canonical runtime should not handle grounded direct food question")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input=player_input,
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    line = result["npc"]["line"].lower()

    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_safe_dialogue_fallback"
    assert result["grounding_validation"]["fallback_topic"] == "commerce_inquiry"
    assert any(term in line for term in ("food", "drink", "traveler fare", "stock", "prices"))
    assert "sword" not in line
    assert "guard" not in line
    assert "mud" not in line


def test_direct_npc_rumor_question_safe_fallback_is_topic_aware(monkeypatch):
    player_input = "Bran, what rumors have you heard?"

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "semantic_family": "observation",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )

    def fail_if_called(**kwargs):
        raise AssertionError("canonical runtime should not handle grounded direct rumor question")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input=player_input,
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    line = result["npc"]["line"].lower()

    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_safe_dialogue_fallback"
    assert result["grounding_validation"]["fallback_topic"] == "rumor_inquiry"
    assert "rumor" in line or "heard" in line
    assert "sword" not in line
    assert "mud" not in line


def test_direct_npc_wellbeing_question_safe_fallback_is_topic_aware(monkeypatch):
    player_input = "I ask Bran about how his day is going."

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "investigate",
            "semantic_family": "observation",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )

    def fail_if_called(**kwargs):
        raise AssertionError("canonical runtime should not handle grounded direct wellbeing question")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input=player_input,
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    line = result["npc"]["line"].lower()

    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_safe_dialogue_fallback"
    assert result["grounding_validation"]["fallback_topic"] == "wellbeing_inquiry"
    assert any(term in line for term in ("day", "hearth", "managing", "decent"))
    assert "sword" not in line
    assert "combat" not in line
    assert "violence" not in line


def test_direct_npc_discount_request_goes_to_runtime_not_safe_dialogue(monkeypatch):
    player_input = "Bran, give me a discount."
    observed = {}

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "load_runtime_session", lambda session_id: None)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "save_runtime_session", lambda session: session)
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "persuade",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "persuade",
            "semantic_family": "social",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(player_input),
        },
    )

    def fake_apply_turn(**kwargs):
        observed["called"] = True
        observed["action"] = kwargs["action"]
        return {
            "ok": True,
            "result": {
                "narration": "Bran weighs the request without changing any prices yet.",
                "narration_status": "queued",
                "resolved_result": {"ok": True},
            },
        }

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fake_apply_turn)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input=player_input,
        performance_override={"narration_mode": "deferred"},
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    assert observed["called"] is True
    assert observed["action"]["action_type"] == "persuade"
    assert result["stateful_runtime_narration_contract"]["stateful_runtime_authoritative"] is True
    assert result["stateful_runtime_narration_contract"]["runtime_resolved_before_narration"] is True


def test_stateful_first_call_visible_response_is_ignored_until_runtime(monkeypatch):
    observed = {}

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "load_runtime_session", lambda session_id: None)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "save_runtime_session", lambda session: session)
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "trade",
            "target_id": "item:bread",
            "target_name": "bread",
            "stateful": True,
            "needs_runtime_resolution": True,
            "visible_response": {
                "narration": "Bran hands over free bread.",
                "npc": {"speaker": "Bran", "line": "Here, take it for free."},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "trade",
            "semantic_family": "trade",
            "target_id": "item:bread",
            "target_name": "bread",
            "stateful": True,
            "needs_runtime_resolution": True,
            "visible_response": {
                "narration": "Bran hands over free bread.",
                "npc": {"speaker": "Bran", "line": "Here, take it for free."},
            },
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )

    def fake_apply_turn(**kwargs):
        observed["action"] = kwargs["action"]
        observed["performance_override"] = kwargs["performance_override"]
        return {
            "ok": True,
            "result": {
                "resolved_result": {
                    "service_result": {
                        "success": False,
                        "reason": "insufficient_funds",
                        "price": {"copper": 2},
                    }
                },
                "narration": "Bran names the price. You do not have enough coin.",
                "narration_status": "queued",
                "used_llm": False,
            },
        }

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fake_apply_turn)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input="I buy the bread from Bran.",
        performance_override={"narration_mode": "deferred"},
        session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
    )

    contract = result["stateful_runtime_narration_contract"]

    assert observed["action"]["action_type"] == "trade"
    assert observed["action"]["metadata"]["first_call_advisory"] is True
    assert observed["performance_override"]["enable_action_advisory"] is False
    assert observed["performance_override"]["enable_semantic_action_advisory"] is False
    assert result["result"]["resolved_result"]["service_result"]["success"] is False
    assert contract["first_call_visible_response_ignored_for_stateful"] is True
    assert contract["runtime_resolved_before_narration"] is True
    assert contract["narration_status"] == "queued"
    assert "free bread" not in result["result"]["narration"].lower()


def test_stateful_runtime_saves_grounded_session_before_canonical_apply(monkeypatch):
    saved_sessions = []

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": True})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "load_runtime_session", lambda session_id: None)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "save_runtime_session", lambda session: saved_sessions.append(session) or session)
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "trade",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "trade",
            "semantic_family": "trade",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )

    def fake_apply_turn(**kwargs):
        return {
            "ok": True,
            "result": {
                "resolved_result": {"service_result": {"success": True}},
                "narration_status": "queued",
            },
        }

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fake_apply_turn)

    interactive_runtime.apply_turn(
        session_id="manual_service_bran_test",
        player_input="I buy Hot stew from Bran.",
        performance_override={"narration_mode": "deferred"},
        session_override={
            "session_id": "manual_service_bran_test",
            "simulation_state": {
                "player_state": {
                    "inventory_state": {
                        "currency": {"gold": 0, "silver": 3, "copper": 0},
                    }
                }
            },
            "runtime_state": {},
        },
    )

    assert saved_sessions
    saved_currency = saved_sessions[0]["simulation_state"]["player_state"]["inventory_state"]["currency"]
    assert saved_currency == {"gold": 0, "silver": 3, "copper": 0}
    assert saved_sessions[0]["manifest"]["session_id"] == "manual_service_bran_test"
    assert saved_sessions[0]["runtime_state"]["narration_mode"] == "deferred"


def test_stateful_narration_modes_report_contract(monkeypatch):
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "resolve_service_turn", lambda **kwargs: {"matched": False})
    monkeypatch.setattr(interactive_runtime, "build_app_llm_gateway", lambda: object())
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "_build_turn_id", lambda runtime_state: "turn:test")
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "load_runtime_session", lambda session_id: None)
    monkeypatch.setattr(interactive_runtime.canonical_runtime, "save_runtime_session", lambda session: session)
    monkeypatch.setattr(
        interactive_runtime,
        "get_action_advisory",
        lambda **kwargs: {
            "action_type": "trade",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )
    monkeypatch.setattr(
        interactive_runtime,
        "get_semantic_action_advisory",
        lambda **kwargs: {
            "action_type": "trade",
            "semantic_family": "trade",
            "stateful": True,
            "needs_runtime_resolution": True,
            "first_call_grounding_diagnostics": _bran_diagnostics(),
        },
    )

    def fake_apply_turn(**kwargs):
        mode = kwargs["performance_override"]["narration_mode"]
        return {
            "ok": True,
            "result": {
                "resolved_result": {"service_result": {"success": True, "item": "bread"}},
                "deterministic_fallback_narration": "You buy the bread.",
                "narration": "Bran wraps the bread and takes your coin.",
                "narration_status": "completed" if mode == "blocking" else "queued",
                "used_llm": mode == "blocking",
            },
        }

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fake_apply_turn)

    results = {
        mode: interactive_runtime.apply_turn(
            session_id="manual_service_bran_test",
            player_input="I buy the bread from Bran.",
            performance_override={"narration_mode": mode},
            session_override={"session_id": "manual_service_bran_test", "simulation_state": {}, "runtime_state": {}},
        )
        for mode in ("deferred", "blocking", "deterministic", "disabled")
    }

    assert results["deferred"]["stateful_runtime_narration_contract"]["narration_status"] == "queued"
    assert results["blocking"]["stateful_runtime_narration_contract"]["narration_status"] == "completed"
    assert results["deterministic"]["result"]["narration_status"] == "deterministic"
    assert results["deterministic"]["result"]["used_llm"] is False
    assert results["deterministic"]["result"]["narration"] == "You buy the bread."
    assert results["disabled"]["result"]["narration_status"] == "disabled"
    assert results["disabled"]["result"]["used_llm"] is False
    assert results["disabled"]["result"]["narration"] == ""


def test_dialogue_grounding_check_accepts_compact_grounding_validation_bridge():
    result = {
        "stateful": False,
        "needs_runtime_resolution": False,
        "npc": {"speaker": "Bran", "line": "Styles help, but mud matters."},
        "grounding_validation": {
            "turn_grounding_packet": _bran_diagnostics()["turn_grounding_packet"],
        },
    }
    check_result = run_dialogue_m16_m18_check(
        check={
            "type": "dialogue_first_call_grounding",
            "expected_npc_id": "npc:bran",
            "expected_packet_version": "turn_grounding_packet_v1",
            "require_biography": True,
            "require_personality": True,
            "require_speech_examples": True,
            "expected_non_stateful": True,
        },
        result=result,
        session={},
    )

    assert check_result["ok"] is True
    assert check_result["has_diagnostics"] is True
    assert check_result["packet_version"] == "turn_grounding_packet_v1"
