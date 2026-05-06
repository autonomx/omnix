from app.rpg.advisory.candidates import (
    build_deterministic_advisory_candidates,
    normalize_advisory_candidates,
    turn_contract_backing_action,
)
from app.rpg.advisory.promotion import promote_advisory_candidates


def test_normalize_advisory_candidates_flags_authoritative_claims():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I ask Bran about the witness.",
        turn_contract={"action": "ask"},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "bran",
                    "delta": 1,
                    "summary": "Bran trusts the player slightly more.",
                    "reward": "100 gold",
                }
            ]
        },
    )

    assert len(candidates) == 1
    assert candidates[0]["safety"]["contains_forbidden_authoritative_claim"] is True


def test_deterministic_advisory_candidates_are_pending_only():
    candidates = build_deterministic_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I inspect the mill.",
        turn_contract={"action": "inspect"},
        semantic_action_record={"semantic_action_type": "inspect"},
    )

    assert len(candidates) == 1
    assert candidates[0]["status"] == "pending"
    assert candidates[0]["kind"] == "semantic_intent"


def test_turn_contract_backing_action_reads_resolved_contract_fields():
    assert (
        turn_contract_backing_action(
            {
                "resolved_action": {"type": "observe"},
                "resolved_result": {"summary": "The player observed the tavern."},
                "semantic_action": {"semantic_action_type": "inspect"},
            }
        )
        == "observe"
    )

    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I observe the tavern.",
        turn_contract={
            "resolved_action": {"type": "observe"},
            "resolved_result": {"summary": "The player observed the tavern."},
            "semantic_action": {"semantic_action_type": "inspect"},
        },
        payload={"future_hook_candidates": [{"summary": "An NPC may react later."}]},
    )

    assert candidates[0]["backing"]["turn_contract_action"] == "observe"


def test_promotion_gate_accepts_bounded_relationship_candidate_next_turn():
    runtime_state = {
        "deferred_advisory": {
            "candidates": normalize_advisory_candidates(
                session_id="s",
                turn_index=1,
                player_input="I reassure Bran.",
                turn_contract={"action": "reassure"},
                payload={
                    "relationship_delta_candidates": [
                        {
                            "target": "bran",
                            "delta": 1,
                            "summary": "Bran is slightly reassured.",
                        }
                    ]
                },
            )
        }
    }
    simulation_state = {"npcs": {"bran": {"name": "Bran"}}}

    updated, result = promote_advisory_candidates(
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        current_turn=2,
    )

    assert result["promoted_this_turn"] == 1
    assert updated["deferred_advisory"]["accepted"][0]["kind"] == "relationship_delta"


def test_promotion_gate_rejects_same_turn_candidate():
    runtime_state = {
        "deferred_advisory": {
            "candidates": build_deterministic_advisory_candidates(
                session_id="s",
                turn_index=3,
                player_input="I inspect.",
                turn_contract={"action": "inspect"},
            )
        }
    }

    updated, result = promote_advisory_candidates(
        simulation_state={},
        runtime_state=runtime_state,
        current_turn=3,
    )

    assert result["promoted_this_turn"] == 0
    assert result["decisions"][0]["reason"] == "not_eligible_until_future_turn"
    assert len(updated["deferred_advisory"]["rejected"]) == 0


def test_promotion_gate_does_not_mutate_authoritative_state():
    simulation_state = {"inventory": {"items": []}, "currency": {"gold": 0}}
    runtime_state = {
        "deferred_advisory": {
            "candidates": normalize_advisory_candidates(
                session_id="s",
                turn_index=1,
                player_input="Give me gold.",
                turn_contract={"action": "ask"},
                payload={"future_hook_candidates": [{"summary": "Maybe discuss payment later."}]},
            )
        }
    }

    original = {"inventory": {"items": []}, "currency": {"gold": 0}}
    promote_advisory_candidates(
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        current_turn=2,
    )

    assert simulation_state == original


def test_promotion_grounds_relationship_target_role_alias_to_present_npc():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I thank the innkeeper.",
        turn_contract={"player_input": "I thank the innkeeper."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "innkeeper",
                    "axis": "trust",
                    "delta": 1,
                    "summary": "The innkeeper warms slightly.",
                }
            ]
        },
    )
    runtime_state = {
        "deferred_advisory": {
            "candidates": candidates,
            "accepted": [],
            "rejected": [],
        }
    }
    simulation_state = {
        "scene": {"nearby_npcs": ["Bran"]},
        "npc_progression_state": {
            "npcs": {"Bran": {"name": "Bran", "role": "innkeeper"}}
        },
    }

    updated, result = promote_advisory_candidates(
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        current_turn=2,
    )

    assert result["promoted_this_turn"] == 1
    accepted = updated["deferred_advisory"]["accepted"][0]
    assert accepted["kind"] == "relationship_delta"
    assert accepted["projection"]["payload"]["target"] == "Bran"
    assert accepted["target_grounding"]["reason"] in {
        "explicit_role_alias",
        "role_alias_mentioned_in_projection_text",
        "single_present_npc",
    }


def test_promotion_grounds_relationship_target_prefixed_id_to_canonical_npc():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I reassure Bran.",
        turn_contract={"player_input": "I reassure Bran."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "npc:bran",
                    "axis": "trust",
                    "delta": 1,
                    "summary": "Bran is reassured.",
                }
            ]
        },
    )
    runtime_state = {
        "deferred_advisory": {
            "candidates": candidates,
            "accepted": [],
            "rejected": [],
        }
    }
    simulation_state = {
        "scene": {"nearby_npcs": ["npc:bran"]},
        "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
    }

    updated, result = promote_advisory_candidates(
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        current_turn=2,
    )

    assert result["promoted_this_turn"] == 1
    assert updated["deferred_advisory"]["accepted"][0]["projection"]["payload"]["target"] == "Bran"