from __future__ import annotations

from app.rpg.ai.semantic_action_intelligence import (
    build_semantic_action_prompt,
    normalize_semantic_action_advisory,
)
from app.rpg.session.first_call_dialogue import (
    build_non_stateful_dialogue_result,
    choose_first_call_visible_response,
)


def _diagnostics(player_input: str = "I hug Bran") -> dict:
    return {
        "turn_grounding_packet": {
            "format_version": "test_packet_v1",
            "player_input": player_input,
            "priority_context": {"addressed_npc_ids": ["npc:bran"]},
            "npc_context": {"addressed_npcs": [{"id": "npc:bran", "name": "Bran"}]},
        }
    }


def test_semantic_prompt_treats_hug_as_flavor_not_stateful_mechanic() -> None:
    prompt = build_semantic_action_prompt(
        "I hug Bran",
        simulation_state={},
        runtime_state={},
        candidate_action={},
    )

    assert "semantic_route flavor_action" in prompt
    assert "Do not force these into predefined action variables" in prompt
    assert "'I hug Elara' => semantic_route flavor_action, stateful false" in prompt
    assert "'I hug Elara' => stateful true" not in prompt


def test_normalize_flavor_action_forces_non_stateful_safe_direct_route() -> None:
    advisory = normalize_semantic_action_advisory(
        {
            "semantic_route": "flavor_action",
            "action_type": "social_affection",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "activity_label": "hug",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "utterance_mode": "action_request",
            "literal_action_requested": True,
            "state_mutation_requested": True,
            "risk_domain": "relationship_change",
            "stateful": True,
            "needs_runtime_resolution": True,
            "visible_response": {
                "narration": "Bran reacts.",
                "npc": {"speaker": "Bran", "line": "Easy there, friend."},
            },
            "direct_response_gate": {
                "safe_to_display_now": False,
                "reason": "raw",
                "risk_flags": ["relationship_change"],
            },
        },
        candidate_action={},
    )

    assert advisory["semantic_route"] == "flavor_action"
    assert advisory["stateful"] is False
    assert advisory["needs_runtime_resolution"] is False
    assert advisory["state_mutation_requested"] is False
    assert advisory["risk_domain"] == "none"
    assert advisory["direct_response_gate"]["safe_to_display_now"] is True


def test_first_call_consumes_flavor_action_without_runtime_resolution() -> None:
    semantic_advisory = normalize_semantic_action_advisory(
        {
            "semantic_route": "flavor_action",
            "action_type": "social_affection",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "activity_label": "hug",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "utterance_mode": "emotional_expression",
            "literal_action_requested": True,
            "state_mutation_requested": False,
            "risk_domain": "none",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "Bran reacts to the hug.",
                "npc": {"speaker": "Bran", "line": "Easy there, friend."},
            },
            "direct_response_gate": {"safe_to_display_now": True, "reason": "flavor", "risk_flags": []},
            "first_call_grounding_diagnostics": _diagnostics(),
        },
        candidate_action={},
    )
    semantic_advisory["first_call_grounding_diagnostics"] = _diagnostics()

    result = build_non_stateful_dialogue_result(
        session={},
        simulation_state={},
        runtime_state={},
        player_input="I hug Bran",
        semantic_advisory=semantic_advisory,
    )

    assert result["consumed"] is True
    assert result["stateful"] is False
    assert result["needs_runtime_resolution"] is False
    assert result["result"]["semantic_route"] == "flavor_action"
    assert result["llm_purpose"] == "first_call_flavor_action"


def test_mixed_unsupported_consequential_action_fails_without_mutation() -> None:
    semantic_advisory = normalize_semantic_action_advisory(
        {
            "semantic_route": "mixed",
            "route_components": [
                {"semantic_route": "flavor_action", "summary": "The player hugs Bran.", "supported": True},
                {
                    "semantic_route": "unsupported_consequential_action",
                    "summary": "The player attempts to steal Bran's coin purse.",
                    "supported": False,
                },
            ],
            "unsupported_consequential_action": True,
            "unsupported_reason": "theft_not_supported",
            "graceful_failure_required": True,
            "action_type": "sneak",
            "semantic_family": "stealth",
            "interaction_mode": "direct",
            "activity_label": "steal_coin_purse",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "utterance_mode": "action_request",
            "literal_action_requested": True,
            "state_mutation_requested": True,
            "risk_domain": "inventory",
            "intent_summary": "The player hugs Bran while attempting to steal his coin purse.",
            "stateful": True,
            "needs_runtime_resolution": True,
            "direct_response_gate": {"safe_to_display_now": False, "reason": "theft", "risk_flags": ["inventory"]},
            "first_call_grounding_diagnostics": _diagnostics("I hug Bran and steal his coin purse"),
        },
        candidate_action={},
    )
    semantic_advisory["first_call_grounding_diagnostics"] = _diagnostics(
        "I hug Bran and steal his coin purse"
    )

    result = build_non_stateful_dialogue_result(
        session={},
        simulation_state={"player_state": {"inventory_state": {"currency": {"silver": 10}}}},
        runtime_state={},
        player_input="I hug Bran and steal his coin purse",
        semantic_advisory=semantic_advisory,
    )

    assert result["consumed"] is True
    assert result["state_mutation_applied"] is False
    assert result["authoritative_state_mutation_allowed"] is False
    assert result["result"]["success"] is False
    assert result["result"]["outcome"] == "unsupported_consequential_action_failed"
    assert result["result"]["route_components"][1]["supported"] is False
    assert "fails" in result["final_narration"].lower()


def test_structured_self_audit_blocks_misclassified_dialogue_without_keyword_gate() -> None:
    semantic_advisory = {
        "semantic_route": "dialogue",
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "target_id": "npc:bran",
        "target_name": "Bran",
        "utterance_mode": "casual_conversation",
        "literal_action_requested": False,
        "state_mutation_requested": False,
        "risk_domain": "none",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_response": {
            "narration": "Bran considers the request.",
            "npc": {"speaker": "Bran", "line": "Fine, a little cheaper this once."},
        },
        "direct_response_gate": {"safe_to_display_now": True, "reason": "llm_claimed_dialogue", "risk_flags": []},
        "classification_review": {
            "hidden_state_change_risk": "high",
            "hard_state_domains": ["commerce"],
            "mutation_claims": [],
        },
        "first_call_grounding_diagnostics": _diagnostics("Bran, give me a discount"),
    }

    selected = choose_first_call_visible_response(semantic_advisory=semantic_advisory)

    assert selected["consumable"] is False
    assert any(
        reason.endswith("semantic_self_audit_hard_state_domain:commerce")
        for reason in selected["rejection_reasons"]
    )


def test_structured_mutation_claim_blocks_direct_visible_response_without_raw_text_matching() -> None:
    semantic_advisory = {
        "semantic_route": "flavor_action",
        "action_type": "social_affection",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "target_id": "npc:bran",
        "target_name": "Bran",
        "utterance_mode": "emotional_expression",
        "literal_action_requested": True,
        "state_mutation_requested": False,
        "risk_domain": "none",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_response": {
            "narration": "Bran hugs you back.",
            "npc": {"speaker": "Bran", "line": "All right, friend."},
            "state_delta": {"relationship_delta": 1},
        },
        "direct_response_gate": {"safe_to_display_now": True, "reason": "flavor", "risk_flags": []},
        "first_call_grounding_diagnostics": _diagnostics("I hug Bran"),
    }

    selected = choose_first_call_visible_response(semantic_advisory=semantic_advisory)

    assert selected["consumable"] is False
    assert any(
        reason.endswith("structured_state_mutation_claim:visible_response.state_delta")
        for reason in selected["rejection_reasons"]
    )
