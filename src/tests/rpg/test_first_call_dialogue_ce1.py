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
