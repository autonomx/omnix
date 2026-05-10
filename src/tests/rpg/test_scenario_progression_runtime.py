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


def _apply_actions(state, actions):
    from app.rpg.progression.runtime import apply_progression_for_action

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        assert result["changed"] is True, (turn, action, result)
        state = result["state"]
    return state


def test_five_graph_campaign_progresses_through_sable_chain_proof():
    from app.rpg.progression.runtime import build_scenario_progression_arc_summary

    state = {}
    actions = [
        # Graph 1
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
        "I help Garran prepare the wagon for the safer route and get ready to leave.",
        "I leave Garran's wagon yard with the wagon and take the quarry road.",
        "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        "I scan the rock shelf for watchers or scouts watching the quarry road.",
        "I tell Garran we should slow the wagon and lure the watchers into revealing the ambush.",
        "I help Garran protect the wagon while drawing the ambushers out of hiding.",
        # Graph 2
        "I question the captured bandit about who hired them and why they targeted Garran's wagon.",
        "I search the bandit's satchel for letters, marked coins, or anything tying them to the old mill.",
        "I return to the Rusty Flagon and bring Bran the proof linking the ambush to the old mill.",
        "I ask Bran what he knows about the old mill and who might be using it now.",
        "I travel to the old mill ruins to follow the marked coin lead.",
        "I inspect the old mill cellar, trapdoor, and floor marks for signs of recent use.",
        "I search behind the loose cellar stones for the smuggler cache.",
        "I read the wax-sealed order from the hidden smuggler cache.",
        "I decide to follow the north road shrine lead before the Black Briar contact disappears.",
        # Graph 3
        "I travel to the north road shrine to follow the Black Briar contact lead.",
        "I inspect the shrine grounds for fresh tracks, ash, hidden marks, or signs of the Black Briar contact.",
        "I search the shrine stones and offering bowl for the hidden Black Briar contact token.",
        "I hide near the north road shrine and watch for the Black Briar contact signal.",
        "I shadow the hooded Black Briar contact from the shrine without revealing myself.",
        "I follow the Black Briar contact to the ruined tollhouse.",
        "I eavesdrop on the meeting at the ruined tollhouse to learn who the contact serves.",
        "I recover the tollhouse manifest before the Black Briar contact can remove it.",
        "I confront the Black Briar contact with the recovered manifest and demand the truth about Captain Voss.",
        "I return to Bran and Garran with the manifest proving Captain Voss is behind the attacks.",
        # Graph 4
        "I gather Bran and Garran to plan how to use the proof against Captain Voss.",
        "I ask Bran and Garran who in town still supports Captain Voss.",
        "I go to the magistrate hall and request a public hearing against Captain Voss.",
        "I present the tollhouse manifest and marked evidence to the magistrate.",
        "I ask Bran and Garran to stand as public witnesses at the hearing against Captain Voss.",
        "I protect Bran and Garran from Voss's watchmen and warn the guards that the magistrate has accepted the evidence.",
        "I attend the public hearing and stand with Bran and Garran as the evidence against Captain Voss is heard.",
        "I answer Captain Voss's accusation by tying the manifest, the marked coin, and the witnesses together.",
        "I press Captain Voss to explain why his initials appear on the tollhouse manifest.",
        "I ask the magistrate to arrest Captain Voss and open a wider investigation into his faction.",
        "I help Bran and Garran stabilize the town and reopen the wagon routes after Voss is exposed.",
        "I report back to Bran and Garran that Voss is exposed, then plan to investigate which faction backed him.",
        # Graph 5
        "I review the evidence with Bran and Garran to decide how to identify the faction that backed Captain Voss.",
        "I study the manifest payment marks to trace who funded Captain Voss.",
        "I ask Bran what he knows about the Silver Crow cipher on Voss's payment marks.",
        "I question the old teamster at the wagon yard about the Silver Crow cargo routes.",
        "I travel to the abandoned cooperage to search for the Silver Crow cache.",
        "I inspect the cooperage cellar for hidden doors, cargo marks, or the Silver Crow cache.",
        "I open the hidden Silver Crow cache beneath the cooperage cellar.",
        "I read and decipher the coded Silver Crow ledger from the hidden cache.",
        "I compare the ledger names and seals to identify the Sable Chain agent funding the Silver Crow.",
        "I follow the ledger trail to locate Agent Marlowe before the Sable Chain can erase the evidence.",
        "I confront Agent Marlowe with the Silver Crow ledger and demand the truth about the Sable Chain.",
        "I return to Bran and Garran with proof that the Sable Chain backed Captain Voss through the Silver Crow.",
    ]

    state = _apply_actions(state, actions)
    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")

    assert arc["graph_count"] == 5
    assert arc["completed_graph_count"] == 5
    assert arc["campaign_graphs_complete"] is True
    assert arc["completed_node_count"] >= 61
    assert "graph:tavern_story_seed:voss_backers_investigation" in arc["completed_graph_ids"]
    assert "fact:allies_have_sable_chain_proof" in state["progression_facts"]
    assert "lead:sable_chain_next_arc" in state["progression_leads"]


def test_four_graph_campaign_progresses_through_captain_voss_consequence():
    from app.rpg.progression.runtime import (
        apply_progression_for_action,
        build_scenario_progression_arc_summary,
    )

    state = {}
    actions = [
        # Graph 1
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
        "I help Garran prepare the wagon for the safer route and get ready to leave.",
        "I leave Garran's wagon yard with the wagon and take the quarry road.",
        "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        "I scan the rock shelf for watchers or scouts watching the quarry road.",
        "I tell Garran we should slow the wagon and lure the watchers into revealing the ambush.",
        "I help Garran protect the wagon while drawing the ambushers out of hiding.",
        # Graph 2
        "I question the captured bandit about who hired them and why they targeted Garran's wagon.",
        "I search the bandit's satchel for letters, marked coins, or anything tying them to the old mill.",
        "I return to the Rusty Flagon and bring Bran the proof linking the ambush to the old mill.",
        "I ask Bran what he knows about the old mill and who might be using it now.",
        "I travel to the old mill ruins to follow the marked coin lead.",
        "I inspect the old mill cellar, trapdoor, and floor marks for signs of recent use.",
        "I search behind the loose cellar stones for the smuggler cache.",
        "I read the wax-sealed order from the hidden smuggler cache.",
        "I decide to follow the north road shrine lead before the Black Briar contact disappears.",
        # Graph 3
        "I travel to the north road shrine to follow the Black Briar contact lead.",
        "I inspect the shrine grounds for fresh tracks, ash, hidden marks, or signs of the Black Briar contact.",
        "I search the shrine stones and offering bowl for the hidden Black Briar contact token.",
        "I hide near the north road shrine and watch for the Black Briar contact signal.",
        "I shadow the hooded Black Briar contact from the shrine without revealing myself.",
        "I follow the Black Briar contact to the ruined tollhouse.",
        "I eavesdrop on the meeting at the ruined tollhouse to learn who the contact serves.",
        "I recover the tollhouse manifest before the Black Briar contact can remove it.",
        "I confront the Black Briar contact with the recovered manifest and demand the truth about Captain Voss.",
        "I return to Bran and Garran with the manifest proving Captain Voss is behind the attacks.",
        # Graph 4
        "I gather Bran and Garran to plan how to use the proof against Captain Voss.",
        "I ask Bran and Garran who in town still supports Captain Voss.",
        "I go to the magistrate hall and request a public hearing against Captain Voss.",
        "I present the tollhouse manifest and marked evidence to the magistrate.",
        "I ask Bran and Garran to stand as public witnesses at the hearing against Captain Voss.",
        "I protect Bran and Garran from Voss's watchmen and warn the guards that the magistrate has accepted the evidence.",
        "I attend the public hearing and stand with Bran and Garran as the evidence against Captain Voss is heard.",
        "I answer Captain Voss's accusation by tying the manifest, the marked coin, and the witnesses together.",
        "I press Captain Voss to explain why his initials appear on the tollhouse manifest.",
        "I ask the magistrate to arrest Captain Voss and open a wider investigation into his faction.",
        "I help Bran and Garran stabilize the town and reopen the wagon routes after Voss is exposed.",
        "I report back to Bran and Garran that Voss is exposed, then plan to investigate which faction backed him.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        assert result["changed"] is True, (turn, action, result)
        state = result["state"]

    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")

    assert arc["graph_count"] == 5
    assert arc["completed_graph_count"] == 4
    assert arc["campaign_graphs_complete"] is False
    assert arc["completed_node_count"] >= 49
    assert "graph:tavern_story_seed:captain_voss_consequence" in arc["completed_graph_ids"]
    assert "fact:voss_arc_closed" in state["progression_facts"]
    assert "lead:investigate_voss_backers" in state["progression_leads"]


def test_three_graph_campaign_progresses_to_voss_proof():
    from app.rpg.progression.runtime import (
        apply_progression_for_action,
        build_scenario_progression_arc_summary,
    )

    state = {}
    actions = [
        # Graph 1
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
        "I help Garran prepare the wagon for the safer route and get ready to leave.",
        "I leave Garran's wagon yard with the wagon and take the quarry road.",
        "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        "I scan the rock shelf for watchers or scouts watching the quarry road.",
        "I tell Garran we should slow the wagon and lure the watchers into revealing the ambush.",
        "I help Garran protect the wagon while drawing the ambushers out of hiding.",
        # Graph 2
        "I question the captured bandit about who hired them and why they targeted Garran's wagon.",
        "I search the bandit's satchel for letters, marked coins, or anything tying them to the old mill.",
        "I return to the Rusty Flagon and bring Bran the proof linking the ambush to the old mill.",
        "I ask Bran what he knows about the old mill and who might be using it now.",
        "I travel to the old mill ruins to follow the marked coin lead.",
        "I inspect the old mill cellar, trapdoor, and floor marks for signs of recent use.",
        "I search behind the loose cellar stones for the smuggler cache.",
        "I read the wax-sealed order from the hidden smuggler cache.",
        "I decide to follow the north road shrine lead before the Black Briar contact disappears.",
        # Graph 3
        "I travel to the north road shrine to follow the Black Briar contact lead.",
        "I inspect the shrine grounds for fresh tracks, ash, hidden marks, or signs of the Black Briar contact.",
        "I search the shrine stones and offering bowl for the hidden Black Briar contact token.",
        "I hide near the north road shrine and watch for the Black Briar contact signal.",
        "I shadow the hooded Black Briar contact from the shrine without revealing myself.",
        "I follow the Black Briar contact to the ruined tollhouse.",
        "I eavesdrop on the meeting at the ruined tollhouse to learn who the contact serves.",
        "I recover the tollhouse manifest before the Black Briar contact can remove it.",
        "I confront the Black Briar contact with the recovered manifest and demand the truth about Captain Voss.",
        "I return to Bran and Garran with the manifest proving Captain Voss is behind the attacks.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        assert result["changed"] is True, (turn, action, result)
        state = result["state"]

    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")

    assert arc["graph_count"] == 5
    assert arc["completed_graph_count"] == 3
    assert arc["campaign_graphs_complete"] is False
    assert arc["completed_node_count"] >= 37
    assert "graph:tavern_story_seed:north_road_shrine" in arc["completed_graph_ids"]
    assert "fact:allies_have_voss_proof" in state["progression_facts"]


def test_campaign_complete_clears_active_graph_after_two_graphs_complete():
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
        "I help Garran prepare the wagon for the safer route and get ready to leave.",
        "I leave Garran's wagon yard with the wagon and take the quarry road.",
        "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        "I scan the rock shelf for watchers or scouts watching the quarry road.",
        "I tell Garran we should slow the wagon and lure the watchers into revealing the ambush.",
        "I help Garran protect the wagon while drawing the ambushers out of hiding.",
        "I question the captured bandit about who hired them and why they targeted Garran's wagon.",
        "I search the bandit's satchel for letters, marked coins, or anything tying them to the old mill.",
        "I return to the Rusty Flagon and bring Bran the proof linking the ambush to the old mill.",
        "I ask Bran what he knows about the old mill and who might be using it now.",
        "I travel to the old mill ruins to follow the marked coin lead.",
        "I inspect the old mill cellar, trapdoor, and floor marks for signs of recent use.",
        "I search behind the loose cellar stones for the smuggler cache.",
        "I read the wax-sealed order from the hidden smuggler cache.",
        "I decide to follow the north road shrine lead before the Black Briar contact disappears.",
    ]

    for turn, action in enumerate(actions, start=1):
        result = apply_progression_for_action(
            state,
            scenario_seed="tavern_story_seed",
            player_action=action,
            turn_index=turn,
        )
        state = result["state"]

    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")
    actions_after_complete = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )

    assert arc["campaign_graphs_complete"] is False
    assert arc["completed_graph_count"] == 2
    assert arc["graph_count"] == 5
    assert arc["active_graph_id"] == "graph:tavern_story_seed:north_road_shrine"
    assert state["scenario_progression_active_graph_id"] == "graph:tavern_story_seed:north_road_shrine"
    assert state["scenario_progression_waiting_for_next_graph_pack"] is False
    assert actions_after_complete
    assert actions_after_complete[0]["action_id"] == "travel_to_north_road_shrine"


def test_graph_handoff_activates_bandit_aftermath_after_quarry_ambush():
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
        "I ask Bran who is most likely to travel the road before dawn.",
        "I leave the tavern and travel toward Garran's wagon yard.",
        "I tell Garran the mill bridge may be an ambush and show him the evidence.",
        "I ask Garran if there is another route around the bridge.",
        "I help Garran prepare the wagon for the safer route and get ready to leave.",
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
        assert result["changed"] is True, (turn, action, result)
        state = result["state"]

    next_actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    action_ids = [row["action_id"] for row in next_actions]

    assert "graph:tavern_story_seed:witness_to_quarry" in state["scenario_progression_completed_graph_ids"]
    assert state["scenario_progression_active_graph_id"] == "graph:tavern_story_seed:bandit_aftermath"
    assert state["scenario_progression_waiting_for_next_graph_pack"] is False
    assert "question_captured_bandit" in action_ids
    assert "arc_complete_regroup" not in action_ids


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

    assert arc["campaign_graphs_complete"] is False
    assert arc["arc_complete"] is False  # Active graph is not complete
    assert arc["completed_graph_count"] == 1
    assert arc["active_graph_id"] == "graph:tavern_story_seed:bandit_aftermath"

    actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    assert actions
    assert actions[0]["action_id"] == "question_captured_bandit"


def test_arc_complete_actions_include_next_lead_bridge():
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

    actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    action_ids = [row["action_id"] for row in actions]

    assert "question_captured_bandit" in action_ids
    assert "arc_complete_regroup" not in action_ids


def test_scout_quarry_road_matches_scout_action():
    from app.rpg.progression.runtime import apply_progression_for_action

    state = {
        "scenario_progression_active_graph_id": "graph:tavern_story_seed:witness_to_quarry",
        "progression_leads": {
            "lead:scout_quarry_road": {
                "lead_id": "lead:scout_quarry_road",
                "text": "Scout the quarry road before advancing.",
                "source": "scenario_progression_graph",
            }
        },
        "quest_progress": {
            "quests": {
                "quest:quarry_road_ambush": {
                    "quest_id": "quest:quarry_road_ambush",
                    "title": "Quarry Road Ambush",
                    "status": "active",
                    "completed": False,
                    "source": "scenario_progression_graph",
                    "objectives": [
                        {"objective_id": "objective:scout_quarry_road", "status": "active", "completed": False}
                    ],
                }
            }
        },
    }

    result = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
        turn_index=15,
    )

    assert result["changed"] is True
    assert result["summary"]["matched_node_ids"] == ["scout_quarry_road"]
    assert "fact:quarry_road_tracks" in result["state"]["progression_facts"]
    assert "lead:spot_bridge_watchers" in result["state"]["progression_leads"]


def test_spot_bridge_watchers_matches_scan_action():
    from app.rpg.progression.runtime import apply_progression_for_action

    state = {
        "scenario_progression_active_graph_id": "graph:tavern_story_seed:witness_to_quarry",
        "progression_leads": {
            "lead:spot_bridge_watchers": {
                "lead_id": "lead:spot_bridge_watchers",
                "text": "Look for watchers near the rock shelf.",
                "source": "scenario_progression_graph",
            }
        },
        "quest_progress": {
            "quests": {
                "quest:quarry_road_ambush": {
                    "quest_id": "quest:quarry_road_ambush",
                    "title": "Quarry Road Ambush",
                    "status": "active",
                    "completed": False,
                    "source": "scenario_progression_graph",
                    "objectives": [
                        {"objective_id": "objective:spot_bridge_watchers", "status": "active", "completed": False}
                    ],
                }
            }
        },
    }

    result = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I scan the rock shelf for watchers or scouts watching the quarry road.",
        turn_index=16,
    )

    assert result["changed"] is True
    assert result["summary"]["matched_node_ids"] == ["spot_bridge_watchers"]
    assert "fact:bandit_watchers_spotted" in result["state"]["progression_facts"]
    assert "lead:choose_ambush_response" in result["state"]["progression_leads"]


def test_read_wax_sealed_order_matches_generated_read_action():
    from app.rpg.progression.runtime import apply_progression_for_action

    state = {
        "scenario_progression_active_graph_id": "graph:tavern_story_seed:bandit_aftermath",
        "scenario_progression_completed_graph_ids": ["graph:tavern_story_seed:witness_to_quarry"],
        "progression_leads": {
            "lead:read_wax_sealed_order": {
                "lead_id": "lead:read_wax_sealed_order",
                "text": "Read the wax-sealed order.",
            }
        },
    }

    result = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I read the wax-sealed order from the hidden smuggler cache.",
        turn_index=26,
    )

    assert result["changed"] is True
    assert result["summary"]["matched_node_ids"] == ["read_wax_sealed_order"]
    assert "fact:order_mentions_black_briar_contact" in result["state"]["progression_facts"]
    assert "lead:decide_mill_next_step" in result["state"]["progression_leads"]


def test_decide_mill_next_step_matches_generated_decide_action():
    from app.rpg.progression.runtime import apply_progression_for_action

    state = {
        "scenario_progression_active_graph_id": "graph:tavern_story_seed:bandit_aftermath",
        "scenario_progression_completed_graph_ids": ["graph:tavern_story_seed:witness_to_quarry"],
        "progression_leads": {
            "lead:decide_mill_next_step": {
                "lead_id": "lead:decide_mill_next_step",
                "text": "Decide whether to set a watch or follow the north road shrine lead.",
            }
        },
    }

    result = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I decide to follow the north road shrine lead before the Black Briar contact disappears.",
        turn_index=27,
    )

    assert result["changed"] is True
    assert result["summary"]["matched_node_ids"] == ["decide_mill_next_step"]
    assert "fact:north_road_shrine_next" in result["state"]["progression_facts"]


def test_prepare_quarry_road_unlocks_leave_by_quarry_road_and_starts_next_quest():
    state = {
        "scenario_progression_active_graph_id": "graph:tavern_story_seed:witness_to_quarry",
        "progression_leads": {
            "lead:prepare_quarry_road": {
                "lead_id": "lead:prepare_quarry_road",
                "text": "Prepare the wagon for the quarry road.",
                "source": "scenario_progression_graph",
            }
        },
        "quest_progress": {
            "quests": {
                "quest:warn_wagon": {
                    "quest_id": "quest:warn_wagon",
                    "title": "Warn the Wagon",
                    "status": "active",
                    "completed": False,
                    "source": "scenario_progression_graph",
                    "objectives": [
                        {"objective_id": "objective:choose_safe_route", "status": "active", "completed": False}
                    ],
                }
            }
        },
    }

    result = apply_progression_for_action(
        state,
        scenario_seed="tavern_story_seed",
        player_action="I help Garran prepare the wagon for the safer route and get ready to leave.",
        turn_index=13,
    )

    assert result["changed"] is True
    assert result["summary"]["matched_node_ids"] == ["prepare_quarry_road"]

    state = result["state"]
    assert "lead:leave_by_quarry_road" in state["progression_leads"]
    assert state["quest_progress"]["quests"]["quest:warn_wagon"]["status"] == "completed"
    assert state["quest_progress"]["quests"]["quest:quarry_road_ambush"]["status"] == "active"

    next_actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    action_ids = [row["action_id"] for row in next_actions]
    assert "leave_by_quarry_road" in action_ids