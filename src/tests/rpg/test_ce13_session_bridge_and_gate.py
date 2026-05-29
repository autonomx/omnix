from __future__ import annotations

from app.rpg.session import interactive_first_call_runtime as interactive_runtime
from app.rpg.session.first_call_dialogue import choose_first_call_visible_response
from tests.rpg.manual.dialogue_m16_m18_checks import run_dialogue_m16_m18_check


def _bran_diagnostics():
    return {
        "format_version": "first_call_grounding_diagnostics_v1",
        "turn_grounding_packet": {
            "format_version": "turn_grounding_packet_v1",
            "player_input": "Bran, what do you think about sword combat styles?",
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
    assert result["visible_interaction_reason"] if "visible_interaction_reason" in result else result["result"]["visible_interaction_reason"] == "first_call_safe_dialogue_fallback"


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
