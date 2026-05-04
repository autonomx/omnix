from app.rpg.campaign_director.runtime import (
    apply_campaign_director_tick,
    evaluate_campaign_director_tick,
)
from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_packs.activation import activate_story_pack, deactivate_story_pack
from app.rpg.story_packs.importer import import_story_pack


def _pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "director_activation_pack",
        "title": "Director Activation Pack",
        "lore_entries": [{"lore_id": "lore:director_activation", "title": "Director Activation", "truth_status": "rumor"}],
        "story_arcs": [
            {
                "arc_id": "arc:director_activation",
                "title": "Director Activation",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": ["lore:director_activation"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:director_activation",
                "arc_id": "arc:director_activation",
                "kind": "consequence",
                "summary": "The active story pack escalated.",
                "effects": [
                    {"type": "arc_stage_set", "arc_id": "arc:director_activation", "stage": "active_escalation"}
                ],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": "rule:director_activation",
                "arc_id": "arc:director_activation",
                "priority": 90,
                "conditions": [
                    {"type": "arc_pressure_at_least", "arc_id": "arc:director_activation", "minimum": 50},
                    {"type": "arc_stage", "arc_id": "arc:director_activation", "stage": "rumors"},
                ],
                "event": {"event_id": "event:director_activation", "arc_id": "arc:director_activation", "effects": []},
                "max_applications": 1,
            }
        ],
    }


def test_campaign_director_ignores_inactive_imported_pack_rules():
    simulation_state = {}
    import_story_pack(simulation_state, _pack(), turn_index=1)

    result = evaluate_campaign_director_tick(simulation_state, mode="idle", turn_index=2)

    assert result["ok"] is True
    assert result["eligible_count"] == 0
    assert result["registered_rule_count"] == 0


def test_campaign_director_uses_active_pack_rules():
    simulation_state = {}
    imported = import_story_pack(simulation_state, _pack(), turn_index=1)
    activate_story_pack(simulation_state, imported["pack_id"], turn_index=2)

    result = evaluate_campaign_director_tick(simulation_state, mode="idle", turn_index=3)

    assert result["eligible_count"] == 1
    assert result["registered_rule_count"] == 1


def test_campaign_director_applies_active_pack_event():
    simulation_state = {}
    imported = import_story_pack(simulation_state, _pack(), turn_index=1)
    activate_story_pack(simulation_state, imported["pack_id"], turn_index=2)

    result = apply_campaign_director_tick(simulation_state, mode="idle", turn_index=3)

    assert result["applied_count"] == 1
    assert get_story_arc(simulation_state, "arc:director_activation")["stage"] == "active_escalation"


def test_campaign_director_stops_after_pack_deactivation():
    simulation_state = {}
    imported = import_story_pack(simulation_state, _pack(), turn_index=1)
    activate_story_pack(simulation_state, imported["pack_id"], turn_index=2)
    deactivate_story_pack(simulation_state, imported["pack_id"], turn_index=3)

    result = evaluate_campaign_director_tick(simulation_state, mode="idle", turn_index=4)

    assert result["eligible_count"] == 0
    assert result["registered_rule_count"] == 0