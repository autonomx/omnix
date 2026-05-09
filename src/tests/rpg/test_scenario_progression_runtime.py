from app.rpg.progression.runtime import (
    apply_progression_for_action,
    get_active_progression_actions,
)


def test_progression_graph_produces_initial_concrete_action():
    state = {}

    actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=5,
    )

    assert actions
    assert actions[0]["source"] == "scenario_progression_graph"
    assert "Bran" in actions[0]["command"]
    assert "follow up on the lead" not in actions[0]["command"].lower()


def test_progression_applies_effects_and_unlocks_next_action():
    state = {}

    result = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        turn_index=1,
    )

    assert result["changed"] is True
    state = result["state"]
    assert "fact:witness_left_side_door" in state["progression_facts"]
    assert "npc:mira" in state["progression_unlocked_npcs"]

    actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    commands = [row["command"] for row in actions]
    assert any("side door" in command.lower() for command in commands)


def test_progression_can_complete_first_quest_and_start_second():
    state = {}
    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
        "I turn to Mira and ask what she saw near the side door.",
        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
        "I ask Bran if the old east road leads to a bridge.",
        "I approach the local patron and quietly ask what he knows about the mill bridge.",
        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
    ]
    for idx, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=idx,
        )
        state = result["state"]

    quests = state["quest_progress"]["quests"]
    assert quests["quest:witness_search"]["completed"] is True
    assert quests["quest:warn_wagon"]["status"] == "active"
    assert "npc:garran" in state["progression_unlocked_npcs"]
    assert "location:garran_wagon_yard" in state["progression_unlocked_locations"]


def test_progression_registry_returns_seed_specific_actions_for_caravan_scenario():
    tavern_actions = get_active_progression_actions(
        {},
        scenario_seed="tavern_story_seed",
        limit=3,
    )
    caravan_actions = get_active_progression_actions(
        {},
        scenario_seed="caravan_ambush_seed",
        limit=3,
    )

    assert tavern_actions
    assert caravan_actions
    assert tavern_actions[0]["graph_id"] != caravan_actions[0]["graph_id"]
    assert "Bran" in tavern_actions[0]["command"]
    assert "Selka" in caravan_actions[0]["command"]
    assert "Bran" not in caravan_actions[0]["command"]


def test_caravan_progression_completes_aftermath_and_starts_waystation_stage():
    state = {}
    actions = [
        "I hurry to Selka, help stabilize the wounded, and ask how the ambush began.",
        "I inspect the burned wagons for broken bolts, fire oil, and anything the attackers left behind.",
        "I question Orren about the missing cargo, the wagon manifest, and what the attackers chose to take.",
        "I follow the attackers' tracks through Ember Ravine, checking the ridge and wash for hoofprints and boot marks.",
        "I report to Selka that the tracks look mercenary and lead toward Ashfall Waystation.",
        "I leave the ravine and travel straight to Ashfall Waystation before the trail goes cold.",
    ]

    for idx, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="caravan_ambush_seed",
            player_action=action,
            turn_index=idx,
        )
        state = result["state"]

    quests = state["quest_progress"]["quests"]
    assert quests["quest:caravan_aftermath"]["completed"] is True
    assert quests["quest:waystation_conspiracy"]["status"] == "active"
    assert state["current_location"] == "location:ashfall_waystation"
    assert "npc:hadrik" in state["progression_unlocked_npcs"]


def test_completed_node_is_not_returned_again_after_effects_apply():
    state = {}

    first = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        turn_index=1,
    )
    state = first["state"]

    actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )

    action_ids = [row["action_id"] for row in actions]
    assert "ask_bran_about_tension" not in action_ids
    assert "ask_bran_who_left_side_door" in action_ids


def test_progression_nodes_advance_in_order_without_repeating_first_node():
    state = {}

    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
    ]

    matched = []
    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]
        matched.extend(result["summary"].get("matched_node_ids", []))

    assert matched == [
        "ask_bran_about_tension",
        "ask_bran_who_left_side_door",
        "ask_bran_direction",
    ]
    assert len(state["progression_completed_nodes"]) == 3


def test_no_match_does_not_overwrite_last_changed_summary():
    state = {}

    first = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        turn_index=1,
    )
    state = first["state"]
    assert state["scenario_progression_summary"]["matched_node_ids"] == ["ask_bran_about_tension"]

    second = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I do something unrelated.",
        turn_index=2,
    )
    state = second["state"]

    assert state["scenario_progression_summary"]["matched_node_ids"] == ["ask_bran_about_tension"]
    assert state["scenario_progression_last_no_match"]["turn_index"] == 2


def test_progression_revision_increases_as_nodes_advance():
    from app.rpg.progression.runtime import apply_progression_for_action

    state = {}

    first = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        turn_index=1,
    )
    state = first["state"]
    first_revision = state["progression_state_revision"]

    second = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran who left through the side door and why they were afraid.",
        turn_index=2,
    )
    state = second["state"]

    assert state["progression_state_revision"] > first_revision
    assert state["progression_completed_node_count"] == 2
    assert second["summary"]["matched_node_ids"] == ["ask_bran_who_left_side_door"]


def test_progression_continues_into_second_stage_after_report_to_bran():
    state = {}
    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
        "I turn to Mira and ask what she saw near the side door.",
        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
        "I ask Bran if the old east road leads to a bridge.",
        "I approach the local patron and quietly ask what he knows about the mill bridge.",
        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
        "I ask Bran who is most likely to travel the road before dawn.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]

    assert "ask_bran_garran" in state["progression_completed_nodes"]
    assert "fact:garran_supply_wagon" in state["progression_facts"]
    assert "lead:travel_wagon_yard" in state["progression_leads"]

    next_actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    action_ids = [row["action_id"] for row in next_actions]
    assert "travel_to_wagon_yard" in action_ids


def test_progression_reaches_wagon_yard_and_warns_garran():
    state = {}
    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
        "I turn to Mira and ask what she saw near the side door.",
        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
        "I ask Bran if the old east road leads to a bridge.",
        "I approach the local patron and quietly ask what he knows about the mill bridge.",
        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
        "I ask Bran who is most likely to travel the road before dawn.",
        "I leave the tavern and travel toward Garran's wagon yard.",
        "I tell Garran the mill bridge may be an ambush and show him the evidence.",
        "I ask Garran if there is another route around the bridge.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]

    completed = state["progression_completed_nodes"]
    assert "travel_to_wagon_yard" in completed
    assert "warn_garran" in completed
    assert "ask_alternate_route" in completed
    assert state["current_location"] == "location:garran_wagon_yard"
    assert "fact:quarry_road_option" in state["progression_facts"]


def test_report_findings_starts_warn_wagon_quest_and_objectives():
    from app.rpg.progression.runtime import apply_progression_for_action, get_active_progression_actions

    state = {}
    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
        "I turn to Mira and ask what she saw near the side door.",
        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
        "I ask Bran if the old east road leads to a bridge.",
        "I approach the local patron and quietly ask what he knows about the mill bridge.",
        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]

    quests = state["quest_progress"]["quests"]
    assert quests["quest:witness_search"]["completed"] is True
    assert quests["quest:warn_wagon"]["status"] == "active"
    assert quests["quest:warn_wagon"]["completed"] is False

    objective_ids = {
        obj["objective_id"]
        for obj in quests["quest:warn_wagon"]["objectives"]
    }
    assert "objective:travel_to_wagon_yard" in objective_ids
    assert "objective:warn_garran" in objective_ids

    next_actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    action_ids = [row["action_id"] for row in next_actions]
    assert "ask_bran_garran" in action_ids


def test_ask_bran_garran_can_match_from_lead_even_if_quest_state_lags():
    from app.rpg.progression.runtime import apply_progression_for_action

    state = {
        "progression_leads": {
            "lead:ask_bran_garran": {
                "lead_id": "lead:ask_bran_garran",
                "text": "Ask Bran who travels the road before dawn.",
            }
        }
    }

    result = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran who is most likely to travel the road before dawn.",
        turn_index=9,
    )

    assert result["changed"] is True
    assert result["summary"]["matched_node_ids"] == ["ask_bran_garran"]
    assert "lead:travel_wagon_yard" in result["state"]["progression_leads"]


def test_prepare_quarry_road_seeds_next_arc_objectives_and_actions():
    state = {}
    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
        "I turn to Mira and ask what she saw near the side door.",
        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
        "I ask Bran if the old east road leads to a bridge.",
        "I approach the local patron and quietly ask what he knows about the mill bridge.",
        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
        "I ask Bran who is most likely to travel the road before dawn.",
        "I leave the tavern and travel toward Garran's wagon yard.",
        "I tell Garran the mill bridge may be an ambush and show him the evidence.",
        "I ask Garran if there is another route around the bridge.",
        "I help Garran prepare the wagon for the safer quarry road.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]

    quests = state["quest_progress"]["quests"]
    quarry = quests["quest:quarry_road_ambush"]
    assert quarry["status"] == "active"
    objective_ids = {obj["objective_id"] for obj in quarry["objectives"]}
    assert "objective:leave_by_quarry_road" in objective_ids
    assert "objective:scout_quarry_road" in objective_ids
    assert "objective:spot_bridge_watchers" in objective_ids
    assert "objective:choose_ambush_response" in objective_ids

    next_actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    action_ids = [row["action_id"] for row in next_actions]
    assert "leave_by_quarry_road" in action_ids


def test_quarry_road_arc_can_continue_after_prepare_node():
    state = {}
    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
        "I turn to Mira and ask what she saw near the side door.",
        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
        "I ask Bran if the old east road leads to a bridge.",
        "I approach the local patron and quietly ask what he knows about the mill bridge.",
        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
        "I ask Bran who is most likely to travel the road before dawn.",
        "I leave the tavern and travel toward Garran's wagon yard.",
        "I tell Garran the mill bridge may be an ambush and show him the evidence.",
        "I ask Garran if there is another route around the bridge.",
        "I help Garran prepare the wagon for the safer quarry road.",
        "I leave Garran's wagon yard with the wagon and take the quarry road.",
        "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        "I scan the rock shelf for watchers or scouts watching the quarry road.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]

    completed = state["progression_completed_nodes"]
    assert "leave_by_quarry_road" in completed
    assert "scout_quarry_road" in completed
    assert "spot_bridge_watchers" in completed
    assert state["current_location"] == "location:quarry_road"
    assert "lead:choose_ambush_response" in state["progression_leads"]


def test_arc_summary_reports_complete_after_full_graph():
    from app.rpg.progression.runtime import (
        apply_progression_for_action,
        build_scenario_progression_arc_summary,
        get_active_progression_actions,
    )

    state = {}
    actions = [
        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        "I ask Bran who left through the side door and why they were afraid.",
        "I ask Bran what direction the cloaked traveler went after leaving.",
        "I turn to Mira and ask what she saw near the side door.",
        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
        "I ask Bran if the old east road leads to a bridge.",
        "I approach the local patron and quietly ask what he knows about the mill bridge.",
        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
        "I ask Bran who is most likely to travel the road before dawn.",
        "I leave the tavern and travel toward Garran's wagon yard.",
        "I tell Garran the mill bridge may be an ambush and show him the evidence.",
        "I ask Garran if there is another route around the bridge.",
        "I help Garran prepare the wagon for the safer quarry road.",
        "I leave Garran's wagon yard with the wagon and take the quarry road.",
        "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        "I scan the rock shelf for watchers or scouts watching the quarry road.",
        "I tell Garran we should slow the wagon and lure the watchers into revealing the ambush.",
        "I help Garran protect the wagon while drawing the ambushers out of hiding.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]

    arc = build_scenario_progression_arc_summary(
        state,
        scenario_seed="tavern_story_seed",
    )

    assert arc["arc_complete"] is True
    assert arc["completed_node_count"] == arc["expected_node_count"]
    assert arc["active_graph_quest_count"] == 0
    assert arc["active_graph_objective_count"] == 0

    actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    assert actions
    assert actions[0]["action_id"] == "arc_complete_regroup"