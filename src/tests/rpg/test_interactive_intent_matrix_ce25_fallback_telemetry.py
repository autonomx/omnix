from __future__ import annotations

from app.rpg.session import interactive_first_call_runtime as interactive_runtime
from tests.rpg.test_ce13_session_bridge_and_gate import _bran_diagnostics


def _session_override():
    return {
        "session_id": "manual_service_bran_ce25_matrix",
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
    }


def _install_default_stateful_direct_question(monkeypatch, player_input: str) -> None:
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
        raise AssertionError("canonical runtime should not handle grounded direct NPC question")

    monkeypatch.setattr(interactive_runtime.canonical_runtime, "apply_turn", fail_if_called)


def _assert_safe_dialogue_fallback(result, *, topic: str) -> None:
    assert result["consumed"] is True
    assert result["llm_purpose"] == "first_call_safe_dialogue_fallback"
    assert result["source"] == "first_call_dialogue_safe_fallback_v1"
    assert result["result"]["visible_interaction_reason"] == "first_call_safe_dialogue_fallback"
    assert result["result"]["fallback_topic"] == topic

    top_validation = result["grounding_validation"]
    nested_validation = result["result"]["grounding_validation"]
    for validation in (top_validation, nested_validation):
        assert validation["fallback_used"] is True
        assert validation["fallback_source"] == "first_call_dialogue_safe_fallback_v1"
        assert validation["fallback_topic"] == topic
        assert validation["source"] == "first_call_dialogue_safe_fallback_v1"


def test_ce25_interactive_matrix_food_question_has_safe_fallback_telemetry(monkeypatch):
    player_input = "Bran, what food do you sell at the tavern?"
    _install_default_stateful_direct_question(monkeypatch, player_input)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_ce25_matrix",
        player_input=player_input,
        session_override=_session_override(),
    )

    _assert_safe_dialogue_fallback(result, topic="commerce_inquiry")
    line = result["npc"]["line"].lower()
    assert any(term in line for term in ("food", "drink", "traveler fare", "stock", "prices"))
    assert "sword" not in line
    assert "mud" not in line


def test_ce25_interactive_matrix_rumor_question_has_safe_fallback_telemetry(monkeypatch):
    player_input = "Bran, what rumors have you heard?"
    _install_default_stateful_direct_question(monkeypatch, player_input)

    result = interactive_runtime.apply_turn(
        session_id="manual_service_bran_ce25_matrix",
        player_input=player_input,
        session_override=_session_override(),
    )

    _assert_safe_dialogue_fallback(result, topic="rumor_inquiry")
    line = result["npc"]["line"].lower()
    assert "rumor" in line or "heard" in line
    assert "sword" not in line
    assert "mud" not in line


def test_ce25_interactive_matrix_discount_request_still_goes_to_runtime(monkeypatch):
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
        session_id="manual_service_bran_ce25_matrix",
        player_input=player_input,
        performance_override={"narration_mode": "deferred"},
        session_override=_session_override(),
    )

    assert observed["called"] is True
    assert observed["action"]["action_type"] == "persuade"
    assert result["stateful_runtime_narration_contract"]["stateful_runtime_authoritative"] is True
    assert result["stateful_runtime_narration_contract"]["runtime_resolved_before_narration"] is True
