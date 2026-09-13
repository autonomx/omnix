from __future__ import annotations


def _interpretive_result(intent: str, family: str) -> dict:
    return {
        "source": "world_grounded_interpretive_adjudication_v1",
        "first_call_semantic_advisory": {
            "target_id": "npc:bran",
            "target_name": "Bran",
        },
        "npc": {"speaker": "Bran", "line": "Test line."},
        "result": {
            "interpretive_intent": intent,
            "interpretive_intent_family": family,
            "no_state_mutation": True,
            "needs_runtime_resolution": False,
            "interpretive_fact_constraints": {
                "intent": intent,
                "intent_family": family,
                "may_mutate_state": False,
                "may_transfer_currency": False,
                "verified_facts": {"currency": {"gold": 1}},
            },
        },
        "grounding_validation": {
            "first_call_addressed_npc_ids": ["bran"],
        },
    }


def test_debt_claim_maps_to_unverified_respond_only_assessment() -> None:
    from app.rpg.session.world_reasoning_adapter import build_world_reasoning_from_interpretive_result

    mapped = build_world_reasoning_from_interpretive_result(_interpretive_result("unverified_debt_claim", "claim"))

    assert mapped["format_version"] == "world_reasoning_adapter_v1"
    assert mapped["intent_result"]["kind"] == "claim"
    assert mapped["intent_result"]["legacy_category"] == "unverified_debt_claim"
    assert mapped["intent_result"]["target_id"] == "npc:bran"
    assert mapped["world_assessment"]["verification"] == "unverified"
    assert mapped["world_assessment"]["actionability"] == "respond_only"
    assert mapped["world_assessment"]["state_change_allowed"] is False
    assert mapped["world_assessment"]["constraints"]["verified_facts"]["currency"] == {"gold": 1}


def test_lore_conflict_maps_to_contradictory_assessment() -> None:
    from app.rpg.session.world_reasoning_adapter import build_world_reasoning_from_interpretive_result

    mapped = build_world_reasoning_from_interpretive_result(_interpretive_result("lore_conflict_claim", "claim"))

    assert mapped["world_assessment"]["plausibility"] == "contradictory"
    assert mapped["world_assessment"]["lore_result"] == "inconsistent_or_unverified"
    assert mapped["world_assessment"]["knowledge_scope"] == "addressed_npc"


def test_unsupported_mechanic_maps_to_mechanic_candidate_intent() -> None:
    from app.rpg.session.world_reasoning_adapter import build_world_reasoning_from_interpretive_result

    mapped = build_world_reasoning_from_interpretive_result(
        _interpretive_result("unsupported_mechanic_request", "unsupported_mechanic")
    )

    assert mapped["intent_result"]["kind"] == "mechanic_candidate"
    assert mapped["world_assessment"]["actionability"] == "reject"
    assert mapped["world_assessment"]["physical_result"] == "unlikely"
    assert mapped["world_assessment"]["metadata"]["no_state_mutation"] is True


def test_observation_maps_to_observable_without_runtime() -> None:
    from app.rpg.session.world_reasoning_adapter import build_world_reasoning_from_interpretive_result

    mapped = build_world_reasoning_from_interpretive_result(_interpretive_result("observation_request", "observation"))

    assert mapped["intent_result"]["kind"] == "observation"
    assert mapped["world_assessment"]["verification"] == "observable"
    assert mapped["world_assessment"]["actionability"] == "observe"
    assert mapped["world_assessment"]["metadata"]["needs_runtime_resolution"] is False
