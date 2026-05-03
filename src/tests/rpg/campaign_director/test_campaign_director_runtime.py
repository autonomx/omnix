from app.rpg.campaign_director.runtime import (
    apply_campaign_director_tick,
    build_campaign_director_snapshot,
    evaluate_campaign_director_tick,
)
from app.rpg.npc_evolution.state import get_npc_evolution
from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_packs.importer import import_story_pack
from app.rpg.story_events.state import get_applied_story_event


def _pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "director_bandit_pack",
        "title": "Director Bandit Pack",
        "lore_entries": [{"lore_id": "lore:red_sashes", "title": "The Red Sashes", "truth_status": "rumor"}],
        "story_arcs": [
            {
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": ["lore:red_sashes"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:bandits_burn_tavern",
                "arc_id": "arc:bandit_pressure",
                "kind": "consequence",
                "summary": "Bandits burned Bran's tavern.",
                "effects": [
                    {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "aftermath"},
                    {
                        "type": "npc_evolution",
                        "npc_id": "bran",
                        "npc_arc_id": "npc_arc:bran_revenge",
                        "profession": "former_innkeeper",
                        "motivation": "revenge_against_red_sashes",
                        "personality_deltas": {"vengeful": 20},
                        "flags": {"tavern_lost": True},
                    },
                    {"type": "world_event_emit"},
                ],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": "rule:burn_tavern",
                "arc_id": "arc:bandit_pressure",
                "priority": 90,
                "conditions": [
                    {
                        "type": "arc_pressure_at_least",
                        "arc_id": "arc:bandit_pressure",
                        "minimum": 50,
                    },
                    {
                        "type": "arc_stage",
                        "arc_id": "arc:bandit_pressure",
                        "stage": "rumors",
                    },
                ],
                "event": {"event_id": "event:bandits_burn_tavern", "arc_id": "arc:bandit_pressure", "effects": []},
                "cooldown_turns": 5,
                "max_applications": 1,
            }
        ],
    }


def test_campaign_director_evaluates_registered_rules_without_applying():
    simulation_state = {}
    import_story_pack(simulation_state, _pack(), turn_index=1)

    result = evaluate_campaign_director_tick(simulation_state, mode="idle", turn_index=2)

    assert result["ok"] is True
    assert result["eligible_count"] == 1
    assert result["director_pressure"][0]["eligible_event_id"] == "event:bandits_burn_tavern"
    assert get_story_arc(simulation_state, "arc:bandit_pressure")["stage"] == "rumors"
    assert get_applied_story_event(simulation_state, "event:bandits_burn_tavern") is None


def test_campaign_director_applies_registered_story_event_effects():
    simulation_state = {}
    import_story_pack(simulation_state, _pack(), turn_index=1)

    result = apply_campaign_director_tick(simulation_state, mode="idle", turn_index=2)

    arc = get_story_arc(simulation_state, "arc:bandit_pressure")
    evolution = get_npc_evolution(simulation_state, "bran")
    assert result["ok"] is True
    assert result["applied_count"] == 1
    assert arc["stage"] == "aftermath"
    assert evolution["motivation"] == "revenge_against_red_sashes"
    assert evolution["flags"]["tavern_lost"] is True
    assert get_applied_story_event(simulation_state, "event:bandits_burn_tavern") is not None


def test_campaign_director_does_not_apply_in_unsafe_mode():
    simulation_state = {}
    import_story_pack(simulation_state, _pack(), turn_index=1)

    result = apply_campaign_director_tick(simulation_state, mode="combat", turn_index=2)

    assert result["ok"] is True
    assert result["reason"] == "unsafe_mode"
    assert result["applied_count"] == 0
    assert get_story_arc(simulation_state, "arc:bandit_pressure")["stage"] == "rumors"


def test_campaign_director_respects_max_applications_and_story_event_idempotency():
    simulation_state = {}
    import_story_pack(simulation_state, _pack(), turn_index=1)

    first = apply_campaign_director_tick(simulation_state, mode="idle", turn_index=2)
    second = apply_campaign_director_tick(simulation_state, mode="idle", turn_index=3)

    assert first["applied_count"] == 1
    assert second["applied_count"] == 0
    assert get_story_arc(simulation_state, "arc:bandit_pressure")["stage"] == "aftermath"


def test_campaign_director_snapshot_is_bounded_and_advisory():
    simulation_state = {}
    import_story_pack(simulation_state, _pack(), turn_index=1)

    snapshot = build_campaign_director_snapshot(simulation_state, mode="idle", turn_index=2)

    assert snapshot["ok"] is True
    assert snapshot["advisory_only"] is True
    assert len(snapshot["director_pressure"]) <= snapshot["bounded"]["max_pressure_items"]