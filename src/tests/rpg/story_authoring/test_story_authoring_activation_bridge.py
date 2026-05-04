import json

from app.rpg.campaign_director.runtime import evaluate_campaign_director_tick
from app.rpg.story_authoring.approval import (
    approve_story_proposal,
    draft_story_proposal_for_approval,
)
from app.rpg.story_packs.activation import is_story_pack_active


def _pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "approval_activation_pack",
        "title": "Approval Activation Pack",
        "lore_entries": [{"lore_id": "lore:approval_activation", "title": "Approval Activation", "truth_status": "rumor"}],
        "story_arcs": [
            {
                "arc_id": "arc:approval_activation",
                "title": "Approval Activation",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": ["lore:approval_activation"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:approval_activation",
                "arc_id": "arc:approval_activation",
                "kind": "consequence",
                "summary": "Approval activated pack escalated.",
                "effects": [],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": "rule:approval_activation",
                "arc_id": "arc:approval_activation",
                "priority": 90,
                "conditions": [
                    {"type": "arc_pressure_at_least", "arc_id": "arc:approval_activation", "minimum": 50}
                ],
                "event": {"event_id": "event:approval_activation", "arc_id": "arc:approval_activation", "effects": []},
            }
        ],
    }


def test_approve_without_auto_activate_imports_but_director_ignores():
    simulation_state = {}
    draft = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft activation pack.",
        llm_text_override=json.dumps(_pack()),
        turn_index=1,
    )
    approved = approve_story_proposal(
        simulation_state,
        pending_id=draft["pending_id"],
        turn_index=2,
        auto_activate=False,
    )
    evaluation = evaluate_campaign_director_tick(simulation_state, mode="idle", turn_index=3)

    assert approved["ok"] is True
    assert is_story_pack_active(simulation_state, "storypack:approval_activation_pack") is False
    assert evaluation["eligible_count"] == 0


def test_approve_with_auto_activate_bridges_to_director():
    simulation_state = {}
    draft = draft_story_proposal_for_approval(
        simulation_state,
        authoring_goal="Draft activation pack.",
        llm_text_override=json.dumps(_pack()),
        turn_index=1,
    )
    approved = approve_story_proposal(
        simulation_state,
        pending_id=draft["pending_id"],
        turn_index=2,
        auto_activate=True,
    )
    evaluation = evaluate_campaign_director_tick(simulation_state, mode="idle", turn_index=3)

    assert approved["ok"] is True
    assert approved["reason"] == "approved_imported_activated"
    assert is_story_pack_active(simulation_state, "storypack:approval_activation_pack") is True
    assert evaluation["eligible_count"] == 1