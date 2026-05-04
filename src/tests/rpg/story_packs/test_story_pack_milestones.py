from app.rpg.story_arcs.milestones import get_story_arc_milestone
from app.rpg.story_packs.importer import import_story_pack


def test_story_pack_import_seeds_arc_milestones():
    simulation_state = {}
    pack = {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "milestone_pack",
        "title": "Milestone Pack",
        "lore_entries": [{"lore_id": "lore:x", "title": "X", "truth_status": "rumor"}],
        "story_arcs": [
            {
                "arc_id": "arc:x",
                "title": "X",
                "stage": "rumors",
                "linked_lore": ["lore:x"],
                "milestones": [
                    {
                        "milestone_id": "milestone:x",
                        "title": "Find the witness",
                        "objective_text": "Find the witness near the tavern.",
                    }
                ],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }

    result = import_story_pack(simulation_state, pack, turn_index=1)

    assert result["ok"] is True
    assert get_story_arc_milestone(simulation_state, "milestone:x")["objective_text"] == "Find the witness near the tavern."