from __future__ import annotations

from app.rpg.session.first_call_dialogue import (
    build_non_stateful_dialogue_result,
    choose_first_call_visible_response,
)
from app.rpg.session.interactive_first_call_runtime import _disable_duplicate_runtime_first_call


def _dialogue_advisory():
    return {
        "action_type": "social_activity",
        "semantic_family": "social",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_response": {
            "narration": "Bran considers the question before answering.",
            "npc": {
                "speaker": "Bran",
                "line": "Styles are useful, but mud and panic test your feet faster than any fencing master.",
            },
        },
        "direct_response_gate": {
            "safe_to_display_now": True,
            "reason": "non_mutating_opinion_dialogue",
            "risk_flags": [],
        },
        "utterance_mode": "opinion_question",
        "literal_action_requested": False,
        "state_mutation_requested": False,
        "risk_domain": "none",
        "intent_summary": "Player asks Bran for an opinion.",
        "evidence_spans": ["what do you think"],
        "first_call_grounding_diagnostics": {
            "format_version": "first_call_grounding_diagnostics_v1",
            "turn_grounding_packet": {
                "format_version": "turn_grounding_packet_v1",
                "npc_context": {"addressed_npcs": [{"id": "npc:bran", "name": "Bran"}]},
            },
        },
    }


def test_non_stateful_dialogue_is_consumable_and_keeps_grounding_diagnostics():
    selected = choose_first_call_visible_response(semantic_advisory=_dialogue_advisory())

    assert selected["consumable"] is True
    assert selected["reason"] == "non_stateful_interpretive_dialogue"
    assert selected["source"] == "semantic_advisory"
    assert selected["npc"]["speaker"] == "Bran"
    assert "mud" in selected["text"].lower()
    assert selected["first_call_grounding_diagnostics"]["turn_grounding_packet"]["format_version"] == "turn_grounding_packet_v1"


def test_service_or_commerce_match_blocks_visible_response_consumption():
    selected = choose_first_call_visible_response(
        semantic_advisory=_dialogue_advisory(),
        service_matched=True,
    )

    assert selected["consumable"] is False
    assert selected["reason"] == "service_or_commerce_runtime_wins"


def test_stateful_purchase_visible_response_is_ignored_until_runtime():
    selected = choose_first_call_visible_response(
        semantic_advisory={
            "action_type": "trade",
            "semantic_family": "trade",
            "stateful": True,
            "needs_runtime_resolution": True,
            "target_id": "npc:bran",
            "target_name": "bread",
            "visible_response": {
                "npc": {"speaker": "Bran", "line": "That will be one copper."}
            },
        }
    )

    assert selected["consumable"] is False
    assert selected["reason"] == "no_safe_non_stateful_visible_response"


def test_direct_social_dialogue_visible_response_wins_even_if_flags_request_runtime():
    advisory = _dialogue_advisory()
    advisory["stateful"] = True
    advisory["needs_runtime_resolution"] = True
    advisory["visible_response"] = {
        "narration": "You admit the last few days have been rough.",
        "npc": {
            "speaker": "Bran",
            "line": "Rough, eh? Come on now, friend. Tell old Bran about it.",
        },
    }
    advisory["direct_response_gate"] = {
        "safe_to_display_now": True,
        "reason": "non_mutating_emotional_dialogue",
        "risk_flags": [],
    }

    selected = choose_first_call_visible_response(semantic_advisory=advisory)

    assert selected["consumable"] is True
    assert selected["source"] == "semantic_advisory"
    assert "rough" in selected["npc"]["line"].lower()


def test_llm_direct_response_gate_blocks_dialogue_text_with_runtime_risk():
    advisory = _dialogue_advisory()
    advisory["action_type"] = "social_activity"
    advisory["semantic_family"] = "social"
    advisory["stateful"] = False
    advisory["needs_runtime_resolution"] = False
    advisory["visible_response"] = {
        "narration": "You ask Bran to lower the price.",
        "npc": {"speaker": "Bran", "line": "Sure, I can knock the room down to free."},
    }
    advisory["direct_response_gate"] = {
        "safe_to_display_now": False,
        "reason": "commerce_or_price_change_requested",
        "risk_flags": ["service", "price_change"],
    }

    selected = choose_first_call_visible_response(semantic_advisory=advisory)

    assert selected["consumable"] is False
    assert "direct_response_gate_blocked" in selected["rejection_reasons"][0]


def test_semantic_intent_gate_allows_figurative_risk_word_when_non_mutating():
    advisory = _dialogue_advisory()
    advisory["visible_response"] = {
        "narration": "You admit the insult landed hard.",
        "npc": {"speaker": "Bran", "line": "Aye, words can hit hard. Sit a moment and breathe."},
    }
    advisory["utterance_mode"] = "emotional_expression"
    advisory["literal_action_requested"] = False
    advisory["state_mutation_requested"] = False
    advisory["risk_domain"] = "none"
    advisory["intent_summary"] = "Player says they feel attacked by an insult, not that combat is happening."
    advisory["evidence_spans"] = ["I feel attacked"]

    selected = choose_first_call_visible_response(semantic_advisory=advisory)

    assert selected["consumable"] is True
    assert selected["semantic_intent_gate"]["utterance_mode"] == "emotional_expression"
    assert selected["semantic_intent_gate"]["risk_domain"] == "none"


def test_semantic_intent_gate_blocks_literal_combat_even_if_direct_gate_says_safe():
    advisory = _dialogue_advisory()
    advisory["action_type"] = "social_activity"
    advisory["semantic_family"] = "social"
    advisory["visible_response"] = {
        "narration": "You lunge toward Bran.",
        "npc": {"speaker": "Bran", "line": "Easy there!"},
    }
    advisory["direct_response_gate"] = {
        "safe_to_display_now": True,
        "reason": "mistakenly_marked_safe",
        "risk_flags": [],
    }
    advisory["utterance_mode"] = "action_request"
    advisory["literal_action_requested"] = True
    advisory["state_mutation_requested"] = True
    advisory["risk_domain"] = "combat"
    advisory["intent_summary"] = "Player attempts to attack Bran."
    advisory["evidence_spans"] = ["I attack Bran"]

    selected = choose_first_call_visible_response(semantic_advisory=advisory)

    assert selected["consumable"] is False
    assert "semantic_state_mutation_requested" in selected["rejection_reasons"][0]


def test_build_non_stateful_dialogue_result_does_not_mutate_state_contract():
    simulation_state = {"player_state": {"inventory_state": {"currency": {"silver": 3}}}}
    runtime_state = {"tick": 7}
    result = build_non_stateful_dialogue_result(
        session={"simulation_state": simulation_state, "runtime_state": runtime_state},
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        player_input="Bran, what do you think about sword combat styles?",
        semantic_advisory=_dialogue_advisory(),
    )

    assert result["consumed"] is True
    assert result["result"]["stateful"] is False
    assert result["result"]["needs_runtime_resolution"] is False
    assert result["result"]["visible_interaction_reason"] == "first_call_non_stateful_dialogue"
    assert result["simulation_state"] == simulation_state
    assert result["runtime_state"] == runtime_state
    assert result["llm_purpose"] == "first_call_interpretive_dialogue"


def test_interactive_wrapper_disables_duplicate_runtime_advisory_calls():
    override = _disable_duplicate_runtime_first_call({"fast_turn_mode": True})

    assert override["fast_turn_mode"] is True
    assert override["enable_action_advisory"] is False
    assert override["enable_semantic_action_advisory"] is False
