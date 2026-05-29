from __future__ import annotations

from app.rpg.session import interactive_first_call_runtime as interactive_runtime
from app.rpg.session.first_call_dialogue import choose_first_call_visible_response
from tests.rpg.manual.summary_sanitizer import compact_result_for_summary, sanitize_turn_for_summary


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


def test_sanitizer_preserves_first_call_diagnostics_in_debug_and_full():
    result = {
        "narration": "Bran answers.",
        "first_call_grounding_diagnostics": _bran_diagnostics(),
        "first_call_action_advisory": {"stateful": False},
        "first_call_semantic_advisory": {"stateful": False},
        "grounding_validation": {"selected_candidate": "first_call_visible_response"},
    }
    compact = compact_result_for_summary(result, detail="full")
    turn = {
        "turn_index": 1,
        "player_input": "Bran?",
        "result": compact,
        "first_call_grounding_diagnostics": result["first_call_grounding_diagnostics"],
        "first_call_action_advisory": result["first_call_action_advisory"],
        "first_call_semantic_advisory": result["first_call_semantic_advisory"],
    }

    sanitized = sanitize_turn_for_summary(turn, detail="full")

    assert sanitized["first_call_grounding_diagnostics"]["turn_grounding_packet"]["format_version"] == "turn_grounding_packet_v1"
    assert sanitized["first_call_action_advisory"]["stateful"] is False
    assert sanitized["first_call_semantic_advisory"]["stateful"] is False
