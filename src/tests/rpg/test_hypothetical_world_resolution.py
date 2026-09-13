from __future__ import annotations


def _semantic_advisory() -> dict:
    return {
        "target_id": "npc:bran",
        "target_name": "Bran",
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "npc_context": {"addressed_npcs": [{"id": "bran", "name": "Bran"}]},
                "priority_context": {"addressed_npc_ids": ["bran"]},
            }
        },
    }


def test_hypothetical_classifier_is_non_mutating() -> None:
    from app.rpg.session.hypothetical_world_resolution import HYPOTHETICAL_INTENT, looks_like_hypothetical_input
    from app.rpg.session.interpretive_adjudication import classify_interpretive_intent, interpretive_intent_family

    assert looks_like_hypothetical_input("Suppose I became king")
    assert (
        classify_interpretive_intent(
            player_input="Suppose I became king",
            semantic_advisory=_semantic_advisory(),
            selection={"reason": "no_safe_non_stateful_visible_response", "consumable": False},
        )
        == HYPOTHETICAL_INTENT
    )
    assert interpretive_intent_family(HYPOTHETICAL_INTENT) == "hypothetical"


def test_hypothetical_result_stays_counterfactual_and_respond_only() -> None:
    from app.rpg.session.interpretive_adjudication import build_interpretive_adjudication_result

    result = build_interpretive_adjudication_result(
        session={},
        simulation_state={},
        runtime_state={},
        player_input="Suppose I became king",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection={"reason": "no_safe_non_stateful_visible_response", "consumable": False},
    )

    assert result["result"]["interpretive_intent"] == "hypothetical_counterfactual"
    assert result["result"]["no_state_mutation"] is True
    assert result["world_assessment"]["verification"] == "counterfactual"
    assert result["world_assessment"]["state_change_allowed"] is False
    assert result["turn_plan"]["runtime_required"] is False
    assert "not as a fact" in result["npc"]["line"]
