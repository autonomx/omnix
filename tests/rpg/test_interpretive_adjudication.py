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


def test_impossible_npc_request_becomes_interpretive_adjudication() -> None:
    from app.rpg.session.interpretive_adjudication import (
        build_interpretive_adjudication_result,
        classify_interpretive_intent,
        should_use_interpretive_adjudication,
    )

    selection = {"reason": "no_safe_non_stateful_visible_response", "consumable": False}

    assert (
        classify_interpretive_intent(
            player_input="i ask bran to jump 10 feet in the air",
            semantic_advisory=_semantic_advisory(),
            selection=selection,
        )
        == "npc_capability_request"
    )
    assert should_use_interpretive_adjudication(
        player_input="i ask bran to jump 10 feet in the air",
        semantic_advisory=_semantic_advisory(),
        selection=selection,
    )

    result = build_interpretive_adjudication_result(
        session={"simulation_state": {}, "runtime_state": {}},
        simulation_state={},
        runtime_state={"tick": 3},
        player_input="i ask bran to jump 10 feet in the air",
        action_advisory={},
        semantic_advisory=_semantic_advisory(),
        selection=selection,
    )

    assert result["consumed"] is True
    assert result["stateful"] is False
    assert result["needs_runtime_resolution"] is False
    assert result["no_state_mutation"] is True
    assert result["result"]["outcome"] == "interpretive_adjudication"
    assert result["result"]["interpretive_intent"] == "npc_capability_request"
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
        selection={"reason": "no_safe_non_stateful_visible_response", "consumable": False},
    )

    assert result["result"]["interpretive_intent"] == "unverified_debt_claim"
    assert result["result"]["no_state_mutation"] is True
    assert "proof" in result["npc"]["line"].lower()
    assert result["simulation_state"] == {"currency": {"gold": 1}}


def test_parse_noise_remains_outside_interpretive_adjudication() -> None:
    from app.rpg.session.interpretive_adjudication import should_use_interpretive_adjudication

    assert not should_use_interpretive_adjudication(
        player_input="[object Object]",
        semantic_advisory=_semantic_advisory(),
        selection={"reason": "no_safe_non_stateful_visible_response", "consumable": False},
    )
    assert not should_use_interpretive_adjudication(
        player_input="...",
        semantic_advisory=_semantic_advisory(),
        selection={"reason": "no_safe_non_stateful_visible_response", "consumable": False},
    )


def test_installed_hook_routes_meaningful_unsupported_input_before_runtime(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime as runtime
    from app.rpg.session.interpretive_adjudication import install_interpretive_adjudication_hook

    monkeypatch.delattr(runtime, "_omnix_interpretive_adjudication_hook_installed", raising=False)
    install_interpretive_adjudication_hook()

    selection = {"reason": "no_safe_non_stateful_visible_response", "consumable": False}
    should_fallback = runtime._should_safe_fallback_nonstateful_dialogue(
        {},
        _semantic_advisory(),
        selection,
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
        selection=selection,
    )

    assert result["source"] == "world_grounded_interpretive_adjudication_v1"
    assert result["result"]["outcome"] == "interpretive_adjudication"
    assert result["stateful"] is False
