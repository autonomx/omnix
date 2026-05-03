from app.rpg.story_packs.importer import import_story_pack
from tests.rpg.manual.campaign_director_m22_m24_checks import (
    run_campaign_director_m22_m24_checks,
)


def _pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "tiny_director",
        "title": "Tiny Director",
        "lore_entries": [{"lore_id": "lore:x", "title": "X", "truth_status": "rumor"}],
        "story_arcs": [
            {
                "arc_id": "arc:x",
                "title": "X",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": ["lore:x"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:x",
                "arc_id": "arc:x",
                "effects": [{"type": "arc_stage_set", "arc_id": "arc:x", "stage": "aftermath"}],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": "rule:x",
                "arc_id": "arc:x",
                "priority": 80,
                "conditions": [
                    {"type": "arc_pressure_at_least", "arc_id": "arc:x", "minimum": 50}
                ],
                "event": {"event_id": "event:x", "arc_id": "arc:x", "effects": []},
            }
        ],
    }


def test_manual_campaign_director_evaluate_check_reads_session_state():
    session = {"simulation_state": {}}
    import_story_pack(session["simulation_state"], _pack(), turn_index=1)

    result = run_campaign_director_m22_m24_checks(
        checks=[
            {
                "type": "campaign_director_evaluate",
                "mode": "idle",
                "turn_index": 2,
                "expected_eligible_count": 1,
                "expected_first_event_id": "event:x",
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_campaign_director_apply_check_mutates_state():
    session = {"simulation_state": {}}
    import_story_pack(session["simulation_state"], _pack(), turn_index=1)

    result = run_campaign_director_m22_m24_checks(
        checks=[
            {
                "type": "campaign_director_apply",
                "mode": "idle",
                "turn_index": 2,
                "expected_applied_count": 1,
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True