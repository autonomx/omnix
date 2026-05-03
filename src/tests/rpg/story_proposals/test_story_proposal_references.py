from app.rpg.story_proposals.validation import validate_story_proposal


def test_story_proposal_unknown_arc_reference_rejected():
    result = validate_story_proposal(
        {},
        {
            "proposal_version": "story_proposal_v1",
            "proposal_type": "story_pack",
            "story_events": [
                {
                    "event_id": "event:x",
                    "arc_id": "arc:missing",
                    "effects": [],
                }
            ],
        },
    )

    assert result["ok"] is False
    assert "unknown_arc_reference" in str(result["errors"])


def test_story_proposal_invalid_quest_reference_rejected():
    result = validate_story_proposal(
        {},
        {
            "proposal_version": "story_proposal_v1",
            "proposal_type": "story_pack",
            "lore_entries": [{"lore_id": "lore:x", "title": "X"}],
            "story_arcs": [
                {
                    "arc_id": "arc:x",
                    "title": "X",
                    "linked_quests": ["bad_quest_id"],
                }
            ],
        },
    )

    assert result["ok"] is False
    assert "invalid_quest_reference" in str(result["errors"])


def test_story_proposal_duplicate_ids_rejected():
    result = validate_story_proposal(
        {},
        {
            "proposal_version": "story_proposal_v1",
            "proposal_type": "story_pack",
            "lore_entries": [
                {"lore_id": "lore:x", "title": "X"},
                {"lore_id": "lore:x", "title": "X again"},
            ],
        },
    )

    assert result["ok"] is False
    assert "duplicate_id" in str(result["errors"])