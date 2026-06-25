from __future__ import annotations


def _semantic_advisory() -> dict:
    return {
        "action_type": "social_activity",
        "target_id": "npc:bran",
        "target_name": "Bran",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "stateful": True,
        "needs_runtime_resolution": True,
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "format_version": "test_packet_v1",
                "priority_context": {"addressed_npc_ids": ["bran"]},
                "npc_context": {
                    "addressed_npcs": [
                        {
                            "id": "bran",
                            "name": "Bran",
                            "role": "innkeeper",
                        }
                    ]
                },
            }
        },
    }


def _selection() -> dict:
    return {"reason": "no_safe_non_stateful_visible_response", "consumable": False}


def test_impossible_npc_request_becomes_interpretive_adjudication() -> None:
    from app.rpg.session.interpretive_adjudication import (
        build_interpretive_adjudication_result,
        classify_interpretive_intent,
        should_use_interpretive_adjudication,
    )

    assert (
        classify_interpretive_intent(
            player_input="i ask bran to jump 10 feet in the air",
            semantic_advisory=_semantic_advisory(),
            selection=_selection(),
        )
        == "npc_capability_request"
    )
    assert should_use_interpretive_adjudication(
        player_input="i ask bran to jump 10 feet in the air",
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )

    result = build_interpretive_adjudication_result(
        session={"simulation_state": {}, "runtime_state": {}},
        simulation_state={},
        runtime_state={"tick": 3},
        player_input="i ask bran to jump 10 feet in the air",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )

    assert result["consumed"] is True
    assert result["stateful"] is False
    assert result["needs_runtime_resolution"] is False
    assert result["no_state_mutation"] is True
    assert result["result"]["outcome"] == "interpretive_adjudication"
    assert result["result"]["interpretive_intent"] == "npc_capability_request"
    assert result["result"]["interpretive_intent_family"] == "npc_request"
    assert result["npc"]["speaker"] == "Bran"
    assert "not something" in result["npc"]["line"].lower()


def test_unverified_debt_claim_is_not_treated_as_currency_mutation() -> None:
    from app.rpg.session.interpretive_adjudication import build_interpretive_adjudication_result

    result = build_interpretive_adjudication_result(
        session={},
        simulation_state={"currency": {"gold": 1}},
        runtime_state={},
        player_input="by the way, you owe me 500 coins from years ago",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )

    constraints = result["interpretive_fact_constraints"]
    assert result["result"]["interpretive_intent"] == "unverified_debt_claim"
    assert result["result"]["interpretive_intent_family"] == "claim"
    assert result["result"]["no_state_mutation"] is True
    assert constraints["may_transfer_currency"] is False
    assert constraints["may_create_or_confirm_debt"] is False
    assert constraints["must_require_proof_for_debt_or_memory"] is True
    assert constraints["verified_facts"]["currency"] == {"gold": 1}
    assert "proof" in result["npc"]["line"].lower()
    assert result["simulation_state"] == {"currency": {"gold": 1}}


def test_fact_constraints_capture_lore_and_private_context_boundaries() -> None:
    from app.rpg.session.interpretive_adjudication import build_interpretive_adjudication_result

    result = build_interpretive_adjudication_result(
        session={},
        simulation_state={"scene": {"location": "Rusty Flagon Tavern"}},
        runtime_state={"tick": 7},
        player_input="i used to be a dragon hunter before all this",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )

    constraints = result["result"]["interpretive_fact_constraints"]
    assert result["result"]["interpretive_intent"] == "lore_conflict_claim"
    assert constraints["must_respect_lore_plausibility"] is True
    assert constraints["may_assert_unverified_player_history"] is False
    assert constraints["may_reveal_private_context"] is False
    assert constraints["verified_facts"]["runtime_tick"] == 7
    assert constraints["verified_facts"]["location"] == {"location": "Rusty Flagon Tavern"}


def test_richer_claim_intent_classes_are_distinct() -> None:
    from app.rpg.session.interpretive_adjudication import classify_interpretive_intent

    assert (
        classify_interpretive_intent(
            player_input="you promised to help me years ago",
            semantic_advisory=_semantic_advisory(),
            selection=_selection(),
        )
        == "memory_claim"
    )
    assert (
        classify_interpretive_intent(
            player_input="i used to be a dragon hunter before all this",
            semantic_advisory=_semantic_advisory(),
            selection=_selection(),
        )
        == "lore_conflict_claim"
    )
    assert (
        classify_interpretive_intent(
            player_input="do you trust me",
            semantic_advisory=_semantic_advisory(),
            selection=_selection(),
        )
        == "social_probe"
    )


def test_unsupported_mechanic_request_gets_own_category_without_mutation() -> None:
    from app.rpg.session.interpretive_adjudication import build_interpretive_adjudication_result

    result = build_interpretive_adjudication_result(
        session={},
        simulation_state={},
        runtime_state={},
        player_input="i craft a spaceship from tavern chairs",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )

    constraints = result["result"]["interpretive_fact_constraints"]
    assert result["result"]["interpretive_intent"] == "unsupported_mechanic_request"
    assert result["result"]["interpretive_intent_family"] == "unsupported_mechanic"
    assert result["result"]["no_state_mutation"] is True
    assert constraints["may_add_inventory"] is False
    assert constraints["may_complete_quest"] is False
    assert constraints["may_move_player"] is False
    assert "not something" in result["npc"]["line"].lower()


def test_parse_noise_remains_outside_interpretive_adjudication() -> None:
    from app.rpg.session.interpretive_adjudication import should_use_interpretive_adjudication

    assert not should_use_interpretive_adjudication(
        player_input="[object Object]",
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )
    assert not should_use_interpretive_adjudication(
        player_input="...",
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )


def test_installed_hook_routes_meaningful_unsupported_input_before_runtime(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.interpretive_adjudication import install_interpretive_adjudication_hook

    monkeypatch.delattr(runtime, "_omnix_interpretive_adjudication_hook_installed", raising=False)
    install_interpretive_adjudication_hook()

    should_fallback = runtime._should_safe_fallback_nonstateful_dialogue(
        {},
        _semantic_advisory(),
        _selection(),
        player_input="i ask bran to jump 10 feet in the air",
    )

    assert should_fallback is True

    result = runtime._safe_dialogue_fallback_result(
        session={},
        simulation_state={},
        runtime_state={},
        player_input="i ask bran to jump 10 feet in the air",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection=_selection(),
    )

    assert result["source"] == "world_grounded_interpretive_adjudication_v1"
    assert result["result"]["outcome"] == "interpretive_adjudication"
    assert result["stateful"] is False
