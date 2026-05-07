from app.rpg.quest_progress import (
    ensure_quest_runtime_state,
    quest_rows_from_story_arc_view,
    starter_quest_state_for_seed,
    summarize_runtime_quests,
)


def test_starter_quest_state_for_tavern_story_seed_has_witness_objectives():
    state = starter_quest_state_for_seed("tavern_story_seed")

    quest = state["quests"]["quest:witness_search"]
    objective_text = [item["summary"] for item in quest["objectives"]]

    assert quest["title"] == "Witness Search"
    assert "Find the witness" in objective_text
    assert "Report findings to Bran" in objective_text


def test_ensure_quest_runtime_state_seeds_tavern_quest_once():
    runtime_state = {}
    runtime_state = ensure_quest_runtime_state(
        runtime_state=runtime_state,
        scenario_seed="tavern_story_seed",
    )
    runtime_state = ensure_quest_runtime_state(
        runtime_state=runtime_state,
        scenario_seed="tavern_story_seed",
    )

    summary = summarize_runtime_quests(runtime_state)

    assert summary["quest_count"] == 1
    assert len(summary["timeline"]) == 1
    assert summary["quests"][0]["title"] == "Witness Search"


def test_quest_rows_from_story_arc_view_projects_milestones():
    rows = quest_rows_from_story_arc_view(
        {
            "arcs": [
                {
                    "arc_id": "witness_search",
                    "title": "Witness Search",
                    "status": "active",
                    "milestones": [
                        {"title": "Find the witness", "status": "active"},
                        {"title": "Report findings to Bran", "status": "active"},
                    ],
                }
            ]
        }
    )

    assert rows[0]["title"] == "Witness Search"
    assert len(rows[0]["objectives"]) == 2