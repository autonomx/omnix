from app.rpg.story_proposals.normalization import normalize_story_proposal


def test_story_proposal_normalizes_shape_and_defaults():
    proposal = normalize_story_proposal(
        {
            "proposal_id": "proposal:red_sashes",
            "title": "Red Sashes Intro",
            "lore_entries": [
                {"lore_id": "lore:red_sashes", "title": "The Red Sashes"}
            ],
            "story_arcs": [
                {"arc_id": "arc:bandit_pressure", "title": "Bandit Pressure", "pressure": 20}
            ],
        }
    )

    assert proposal["proposal_version"] == "story_proposal_v1"
    assert proposal["proposal_type"] == "story_pack"
    assert proposal["lore_entries"][0]["truth_status"] == "unknown"
    assert proposal["story_arcs"][0]["pressure"] == 20
    assert proposal["story_events"] == []
    assert proposal["escalation_rules"] == []


def test_story_proposal_normalization_bounds_lists():
    proposal = normalize_story_proposal(
        {
            "lore_entries": [
                {"lore_id": f"lore:{i}", "title": f"Lore {i}"}
                for i in range(100)
            ]
        }
    )

    assert len(proposal["lore_entries"]) == proposal["limits"]["max_lore_entries"]