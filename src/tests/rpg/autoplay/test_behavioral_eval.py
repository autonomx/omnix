from tests.rpg.autoplay.behavioral_eval import evaluate_behavioral_autoplay


def test_behavioral_eval_fails_vague_repeated_lead_loop():
    transcript = [
        {"player_action": "I follow up on the lead: toward."}
        for _ in range(20)
    ]
    latest_state = {
        "quest_progress": {"quests": {}},
        "scenario_progression_log": [],
    }

    result = evaluate_behavioral_autoplay(transcript, latest_state, requested_turns=20)

    assert result["ok"] is False
    assert result["gates"]["exact_action_streak_ok"] is False
    assert result["gates"]["scenario_progression_changed_ok"] is False


def test_behavioral_eval_passes_structural_progression():
    transcript = [
        {"player_action": "I ask Bran why the tavern feels tense.", "progression_sidecar_completed_node_count": 1},
        {"player_action": "I ask Bran who left through the side door.", "progression_sidecar_completed_node_count": 2},
        {"player_action": "I ask Mira what she saw near the side door.", "progression_sidecar_completed_node_count": 3},
        {"player_action": "I inspect the side-door latch for blood.", "progression_sidecar_completed_node_count": 4},
        {"player_action": "I ask the local patron about the bridge.", "progression_sidecar_completed_node_count": 4},
        {"player_action": "I report the bridge evidence to Bran.", "progression_sidecar_completed_node_count": 4},
        {"player_action": "I travel toward Garran's wagon yard.", "progression_sidecar_completed_node_count": 5},
        {"player_action": "I warn Garran about the bridge ambush.", "progression_sidecar_completed_node_count": 5},
        {"player_action": "I ask Garran about another route.", "progression_sidecar_completed_node_count": 5},
        {"player_action": "I help prepare the wagon for the safer route.", "progression_sidecar_completed_node_count": 5},
    ]
    latest_state = {
        "scenario_progression_log": [{"changed": True} for _ in range(8)],
        "progression_completed_nodes": {f"node_{i}": {} for i in range(5)},
        "quest_progress": {
            "quests": {
                "quest:witness_search": {"status": "completed", "completed": True},
                "quest:warn_wagon": {"status": "active", "completed": False},
            }
        },
        "progression_unlocked_npcs": {"npc:mira": {}, "npc:garran": {}},
        "progression_unlocked_locations": {"location:side_door": {}, "location:garran_wagon_yard": {}},
        "progression_facts": {f"fact:{index}": {} for index in range(5)},
        "location_history": [{"location_id": "location:garran_wagon_yard"}],
    }

    result = evaluate_behavioral_autoplay(transcript, latest_state, requested_turns=20)

    assert result["ok"] is True


def test_behavioral_eval_fails_repeated_graph_node():
    transcript = [
        {"player_action": f"I ask Bran thing {i}."}
        for i in range(10)
    ]
    latest_state = {
        "scenario_progression_log": [
            {
                "changed": True,
                "turn_index": 1,
                "matched_node_ids": ["ask_bran_about_tension"],
            },
            {
                "changed": True,
                "turn_index": 2,
                "matched_node_ids": ["ask_bran_about_tension"],
            },
        ],
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
        },
        "quest_progress": {
            "quests": {
                "quest:witness_search": {"status": "active", "completed": False}
            }
        },
        "progression_unlocked_npcs": {"npc:mira": {}},
        "progression_unlocked_locations": {"location:side_door": {}},
        "progression_facts": {"fact:witness_left_side_door": {}},
    }

    result = evaluate_behavioral_autoplay(
        transcript,
        latest_state,
        requested_turns=20,
    )

    assert result["ok"] is False
    assert result["gates"]["no_repeated_nonrepeatable_node_ok"] is False


def test_behavioral_eval_fails_when_sidecar_fields_missing():
    transcript = [
        {"player_action": "I ask Bran why the tavern is tense."},
        {"player_action": "I ask Bran who left through the side door."},
    ]
    latest_state = {
        "scenario_progression_log": [
            {"changed": True, "matched_node_ids": ["ask_bran_about_tension"]},
            {"changed": True, "matched_node_ids": ["ask_bran_who_left_side_door"]},
        ],
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
        },
        "quest_progress": {"quests": {}},
    }

    result = evaluate_behavioral_autoplay(transcript, latest_state, requested_turns=20)

    assert result["gates"]["progression_sidecar_fields_present_ok"] is False


def test_behavioral_eval_deduplicates_same_turn_node_log_duplicates():
    latest_state = {
        "scenario_progression_log": [
            {"changed": True, "turn_index": 1, "matched_node_ids": ["ask_bran_about_tension"]},
            {"changed": True, "turn_index": 1, "matched_node_ids": ["ask_bran_about_tension"]},
            {"changed": True, "turn_index": 2, "matched_node_ids": ["ask_bran_who_left_side_door"]},
            {"changed": True, "turn_index": 2, "matched_node_ids": ["ask_bran_who_left_side_door"]},
        ],
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
            "ask_bran_direction": {},
        },
        "quest_progress": {
            "quests": {
                "quest:witness_search": {"status": "completed", "completed": True},
                "quest:warn_wagon": {"status": "active", "completed": False},
            }
        },
        "progression_unlocked_npcs": {"npc:mira": {}, "npc:garran": {}},
        "progression_unlocked_locations": {"location:side_door": {}, "location:garran_wagon_yard": {}},
        "progression_facts": {"fact:1": {}, "fact:2": {}, "fact:3": {}},
        "location_history": [{"location_id": "location:garran_wagon_yard"}],
    }
    transcript = [
        {"player_action": "I ask Bran why the tavern is tense.", "progression_sidecar_completed_node_count": 1},
        {"player_action": "I ask Bran who left.", "progression_sidecar_completed_node_count": 2},
        {"player_action": "I ask Bran where they went.", "progression_sidecar_completed_node_count": 3},
    ]

    result = evaluate_behavioral_autoplay(transcript, latest_state, requested_turns=20)

    assert result["metrics"]["matched_node_counts"]["ask_bran_about_tension"] == 1
    assert result["metrics"]["matched_node_counts"]["ask_bran_who_left_side_door"] == 1
    assert result["gates"]["no_repeated_nonrepeatable_node_ok"] is True