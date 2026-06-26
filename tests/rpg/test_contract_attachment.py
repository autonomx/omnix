from __future__ import annotations


def _raw_result() -> dict:
    return {
        "source": "world_grounded_interpretive_adjudication_v1",
        "player_input": "do you trust me",
        "first_call_semantic_advisory": {"target_id": "npc:bran", "target_name": "Bran"},
        "npc": {"speaker": "Bran"},
        "result": {
            "interpretive_intent": "social_probe",
            "interpretive_intent_family": "social",
            "no_state_mutation": True,
            "needs_runtime_resolution": False,
            "interpretive_fact_constraints": {
                "intent": "social_probe",
                "intent_family": "social",
                "may_mutate_state": False,
            },
        },
        "resolved_result": {},
        "grounding_validation": {},
    }


def test_contract_attachment_adds_standard_fields() -> None:
    from app.rpg.session.contract_attachment import add_contracts_to_interpretive_result

    enriched = add_contracts_to_interpretive_result(_raw_result())

    assert enriched["intent_result"]["legacy_category"] == "social_probe"
    assert enriched["world_assessment"]["actionability"] == "respond_only"
    assert enriched["response_authority"]["source"] == "addressed_npc"
    assert enriched["turn_plan"]["runtime_required"] is False
    assert enriched["reasoning_trace"]["runtime_decision"]["decision"] == "not_required"
    assert enriched["result"]["turn_plan"] == enriched["turn_plan"]


def test_contract_attachment_leaves_other_results_unmodified() -> None:
    from app.rpg.session.contract_attachment import add_contracts_to_interpretive_result

    result = {"source": "other", "result": {"ok": True}}

    assert add_contracts_to_interpretive_result(result) == result
