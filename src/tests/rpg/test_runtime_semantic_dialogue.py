from app.rpg.session import runtime as rt
from app.rpg.session.runtime import _dialogue_semantic_action_from_player_input
from app.rpg.session.runtime import _dialogue_semantic_action_from_player_input


def test_dialogue_semantic_parser_classifies_bran_report():
    result = _dialogue_semantic_action_from_player_input(
        "I report to Bran that the cloaked traveler trail points toward the road and ask what danger this confirms."
    )
    assert result
    assert result["action_type"] == "social"
    assert result["semantic_family"] == "social"
    assert result["activity_label"] == "report_witness_findings"
    assert result["target_name"] == "Bran"


def test_dialogue_semantic_parser_classifies_bran_question():
    result = _dialogue_semantic_action_from_player_input(
        "I ask Bran where the cloaked traveler went after leaving by the side door."
    )
    assert result
    assert result["action_type"] == "social"
    assert result["semantic_family"] == "social"
    assert result["activity_label"] == "ask_witness_lead"
    assert result["target_name"] == "Bran"


def test_compile_semantic_action_record_prefers_dialogue_activity_label_over_generic_observe():
    simulation_state = {
        "tick": 4,
        "player_state": {"location_id": "loc:tavern"},
        "npc_index": {
            "npc:bran": {
                "id": "npc:bran",
                "name": "Bran",
                "location_id": "loc:tavern",
            }
        },
    }
    runtime_state = {
        "tick": 4,
        "current_scene": {"scene_id": "scene:tavern", "location_id": "loc:tavern"},
    }

    record = rt._compile_semantic_action_record(
        simulation_state,
        runtime_state,
        "I report to Bran that the cloaked traveler trail points toward the road and ask what danger this confirms.",
        {"action_type": "observe", "target_name": "Bran", "target_id": "npc:bran"},
        {"action_type": "observe", "semantic_family": "observation", "target_name": "Bran", "target_id": "npc:bran"},
    )

    assert record["semantic_action"] == "report_witness_findings"
    assert record["action_type"] == "social"
    assert record["semantic_family"] == "social"
    assert record["interaction_mode"] == "dialogue"
    assert record["target_name"] == "Bran"


def test_dialogue_state_update_from_narration_persists_to_authoritative_player_state():
    simulation_state = {"player_state": {}}
    runtime_state = {}
    narration_payload = {
        "dialogue_state_update": {
            "npc_topics": {
                "Bran:cloaked_traveler": {
                    "npc_id": "Bran",
                    "topic": "cloaked_traveler",
                    "last_player_question": "I ask Bran where the cloaked traveler went.",
                    "last_npc_answer": "Bran points toward the road.",
                    "repeat_count": 1,
                    "facts_already_revealed": ["Active objective: Report findings to Bran"],
                }
            },
            "recent_exchanges": [
                {
                    "npc_id": "Bran",
                    "topic": "cloaked_traveler",
                    "player_action": "I ask Bran where the cloaked traveler went.",
                    "npc_line": "Bran points toward the road.",
                }
            ],
        }
    }

    rt._apply_dialogue_state_update_from_narration(simulation_state, runtime_state, narration_payload)

    assert simulation_state["dialogue_state"]["recent_exchanges"]
    assert simulation_state["player_state"]["dialogue_state"]["npc_topics"]
    assert runtime_state["dialogue_state"]["npc_topics"]