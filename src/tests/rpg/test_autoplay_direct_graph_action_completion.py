from tests.rpg.autoplay_llm_campaign import (
    _direct_complete_graph_action_from_command,
)


def test_direct_completion_recruits_garran_and_completes_party_setup():
    completed_action_ids = set()
    completed_mechanics = set()

    result = _direct_complete_graph_action_from_command(
        command="I ask Garran to join me on the mill road.",
        row={"turn_index": 13},
        all_graph_actions=[
            {
                "id": "ask_garran_to_join",
                "command": "I ask Garran to join me on the mill road.",
                "mechanic": "party_setup",
                "action_terms": ["ask garran", "join me", "mill road"],
                "effects": {
                    "flags": {
                        "mechanic:party_setup": True,
                    }
                },
            }
        ],
        completed_action_ids=completed_action_ids,
        completed_mechanics=completed_mechanics,
    )

    assert result["completed"] is True
    assert "ask_garran_to_join" in completed_action_ids
    assert "party_setup" in completed_mechanics
    assert "party_recruitment" in completed_mechanics

    row = result["row"]
    assert row["garran_recruited"] is True
    assert row["party_setup_completed"] is True
    assert "npc:garran" in row["party"]["companions"]
    assert any(
        hook.get("hook_id") == "hook:mechanic:recruit_garran"
        for hook in row["fired_hooks"]
    )