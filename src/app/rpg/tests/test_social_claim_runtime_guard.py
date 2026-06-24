from __future__ import annotations

from app.rpg.session.runtime_part39 import _phase8_part39_patch_social_claim_mismatch


def _social_claim_semantic_action() -> dict:
    return {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "public",
        "activity_label": "reporting_accomplishment",
        "utterance_mode": "declarative",
        "literal_action_requested": False,
        "state_mutation_requested": True,
        "risk_domain": "social_reputation",
        "intent_summary": "The player is reporting a major in-world accomplishment.",
        "evidence_spans": ["i was able to kill a dragon from the north"],
        "semantic_advisory": {
            "semantic_family": "social",
            "interaction_mode": "public",
            "activity_label": "reporting_accomplishment",
            "utterance_mode": "declarative",
            "literal_action_requested": False,
            "state_mutation_requested": True,
            "risk_domain": "social_reputation",
            "intent_summary": "The player is reporting a major in-world accomplishment.",
            "evidence_spans": ["i was able to kill a dragon from the north"],
        },
    }


def test_social_accomplishment_claim_does_not_render_stale_travel_result():
    player_input = "i was able to kill a dragon from the north"
    stale_travel = {
        "action_type": "exploration",
        "action": "Travel is completed, moving from the tavern to the village square.",
        "narration": (
            "The party leaves The Rusty Flagon Tavern and steps out into the "
            "bustling Village Square."
        ),
        "travel_result": {
            "matched": True,
            "from_location_id": "rusty_flagon",
            "to_location_id": "village_square",
        },
        "semantic_action": _social_claim_semantic_action(),
    }
    payload = {
        **stale_travel,
        "result": dict(stale_travel),
        "authoritative": dict(stale_travel),
        "narration_context": {"resolved_result": dict(stale_travel)},
    }

    patched = _phase8_part39_patch_social_claim_mismatch(
        payload,
        player_input=player_input,
    )

    assert patched["action_type"] == "social_activity"
    assert patched["semantic_family"] == "social"
    assert patched["claim_veracity"] == "unverified"
    assert patched["verified_world_fact"] is False
    assert patched["state_mutation_requested"] is False
    assert patched["travel_result"]["matched"] is False
    assert patched["travel_result"]["reason"] == "social_claim_not_travel"
    assert "unverified claim" in patched["final_narration"]
    assert "Village Square" not in patched["final_narration"]
    assert patched["result"]["action_type"] == "social_activity"
    assert patched["authoritative"]["travel_result"]["matched"] is False
    assert patched["narration_context"]["resolved_result"]["action_type"] == "social_activity"


def test_social_accomplishment_claim_without_travel_mismatch_is_left_alone():
    player_input = "i was able to kill a dragon from the north"
    payload = {
        "action_type": "social_activity",
        "narration": "You make a bold claim at the bar.",
        "semantic_action": _social_claim_semantic_action(),
    }

    patched = _phase8_part39_patch_social_claim_mismatch(
        payload,
        player_input=player_input,
    )

    assert patched == payload
