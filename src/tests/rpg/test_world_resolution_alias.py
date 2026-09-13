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


def test_world_resolution_aliases_legacy_intent_classifier() -> None:
    from app.rpg.session.world_resolution import (
        classify_world_resolution_intent,
        should_use_world_resolution,
        world_resolution_intent_family,
    )

    selection = {"reason": "no_safe_non_stateful_visible_response", "consumable": False}

    assert (
        classify_world_resolution_intent(
            player_input="do you trust me",
            semantic_advisory=_semantic_advisory(),
            selection=selection,
        )
        == "social_probe"
    )
    assert world_resolution_intent_family("social_probe") == "social"
    assert should_use_world_resolution(
        player_input="do you trust me",
        semantic_advisory=_semantic_advisory(),
        selection=selection,
    )


def test_world_resolution_result_includes_contract_payloads() -> None:
    from app.rpg.session.world_resolution import build_world_resolution_result

    result = build_world_resolution_result(
        session={},
        simulation_state={},
        runtime_state={},
        player_input="do you trust me",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection={"reason": "no_safe_non_stateful_visible_response", "consumable": False},
    )

    assert result["result"]["interpretive_intent"] == "social_probe"
    assert result["intent_result"]["legacy_category"] == "social_probe"
    assert result["response_authority"]["source"] == "addressed_npc"
    assert result["turn_plan"]["presentation_type"] == "npc_dialogue"
