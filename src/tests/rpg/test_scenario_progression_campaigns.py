from __future__ import annotations

from tests.rpg.scenario_progression_helpers import _apply_actions, _campaign_actions_through_graph_8


def test_eight_graph_campaign_progresses_through_handler_veska_pursuit():
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
        # Graph 6
        "I meet with Bran and Garran to plan how to move against the Sable Chain before they strike back.",
        "I secure the Silver Crow ledger, the manifest, and Marlowe's proof before the Sable Chain can steal them.",
        "I scout the streets around the River Gate safehouse for Sable Chain watchers.",
        "I shadow the Sable Chain watchers from the safehouse to learn where they report.",
        "I follow the watchers to the River Gate warehouses.",
        "I inspect the River Gate warehouse marks, crates, and chalk signs for Sable Chain codes.",
        "I search the warehouse office for Sable Chain countermove orders.",
        "I rush back to warn Bran and Garran that the Sable Chain plans to burn the evidence and silence witnesses.",
        "I help Bran and Garran prepare the safehouse defense and protect the evidence before the Sable Chain strike.",
        "I intercept the Sable Chain strike team before they can burn the safehouse evidence.",
        "I capture the strike team's sealed orders before they can destroy them.",
        "I report to Bran and Garran that the Sable Chain countermove failed and the sealed orders point to a higher handler.",
        # Graph 7
        "I review the sealed orders with Bran and Garran to identify the higher Sable Chain handler.",
        "I decode the handler's route cipher from the sealed orders.",
        "I warn the east road teamsters that the Sable Chain handler plans to choke the supply route.",
        "I scout the east road for roadblocks, chokepoints, and Sable Chain pressure points.",
        "I disable the false toll markers the Sable Chain placed along the east road.",
        "I search the old milepost for the Sable Chain handler's dead drop.",
        "I read the route pressure instructions from the handler's dead drop.",
        "I travel to Black Ford before the Sable Chain handler's people can seize the crossing.",
        "I confront the Sable Chain route pressure agents at Black Ford and order them to stand down.",
        "I secure the Black Ford crossing so the teamsters can keep the east road open.",
        "I study the captured route papers to identify the Sable Chain handler's signature.",
        "I return to Bran and Garran with the name of the Sable Chain handler: Veska.",
        # Graph 8
        "I meet with Bran and Garran to plan how to pursue Handler Veska before the Sable Chain relocates.",
        "I trace Veska's courier route from the captured route papers and sealed orders.",
        "I travel to the old north watchpost to follow Veska's courier trail.",
        "I inspect the old north watchpost for courier signs, Sable Chain marks, and Veska's trail.",
        "I intercept Veska's courier before the message can leave the old north watchpost.",
        "I recover Veska's coded message from the intercepted courier.",
        "I decode Veska's coded message to learn where the Sable Chain leadership is moving.",
        "I travel to the ridge hideout before Veska's leadership cell can relocate.",
        "I scout the ridge hideout for guards, exits, and signs of Handler Veska.",
        "I confront Handler Veska at the ridge hideout with the proof linking her to the Sable Chain route pressure.",
        "I secure Veska's leadership ledgers before the Sable Chain can destroy or move them.",
        "I return to Bran and Garran with Veska's leadership ledgers and proof of the Sable Chain command structure.",
    ]

    state = _apply_actions(state, actions)
    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")

    assert arc["graph_count"] == 9
    assert arc["completed_graph_count"] == 8
    assert arc["campaign_graphs_complete"] is False
    assert arc["completed_node_count"] >= 97
    assert "graph:tavern_story_seed:handler_veska_leadership_pursuit" in arc["completed_graph_ids"]
    assert "fact:allies_have_veska_ledgers" in state["progression_facts"]
    assert "lead:sable_chain_endgame_next_arc" in state["progression_leads"]

def test_nine_graph_campaign_has_active_endgame_content_at_turn_100():
    from app.rpg.progression.runtime import (
        build_scenario_progression_arc_summary,
        get_active_progression_actions,
    )

    state = {}
    actions = _campaign_actions_through_graph_8() + [
        "I review Veska's ledgers with Bran and Garran to map the Sable Chain command structure.",
        "I study the ledger entries to identify the hidden Sable Chain paymaster.",
        "I trace the Red Lantern payment line from Veska's ledgers to find where the Sable Chain money is moving.",
    ]

    state = _apply_actions(state, actions)
    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")
    next_actions = get_active_progression_actions(state, scenario_seed="tavern_story_seed", limit=8)
    next_action_ids = [row["action_id"] for row in next_actions]

    assert arc["graph_count"] == 9
    assert arc["completed_graph_count"] == 8
    assert arc["campaign_graphs_complete"] is False
    assert arc["completed_node_count"] >= 100
    assert arc["active_graph_id"] == "graph:tavern_story_seed:sable_chain_endgame_opener"
    assert "travel_to_old_counting_house" in next_action_ids

def test_nine_graph_campaign_can_complete_sable_chain_endgame_opener():
    from app.rpg.progression.runtime import build_scenario_progression_arc_summary

    state = {}
    actions = _campaign_actions_through_graph_8() + [
        "I review Veska's ledgers with Bran and Garran to map the Sable Chain command structure.",
        "I study the ledger entries to identify the hidden Sable Chain paymaster.",
        "I trace the Red Lantern payment line from Veska's ledgers to find where the Sable Chain money is moving.",
        "I travel to the old counting house near the market ward to follow the Red Lantern payment trail.",
        "I inspect the counting house records for Red Lantern payments and Sable Chain accounts.",
        "I secure the Red Lantern payment records before the Sable Chain can destroy them.",
        "I return to Bran and Garran with the Red Lantern records proving the Sable Chain paymaster's role.",
    ]

    state = _apply_actions(state, actions)
    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")

    assert arc["graph_count"] == 9
    assert arc["completed_graph_count"] == 9
    assert arc["completed_node_count"] >= 104
    assert "graph:tavern_story_seed:sable_chain_endgame_opener" in arc["completed_graph_ids"]
    assert "fact:allies_have_red_lantern_records" in state["progression_facts"]
    assert "lead:red_lantern_paymaster_next_arc" in state["progression_leads"]

def test_seven_graph_campaign_progresses_through_handler_route_pressure():
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
        # Graph 6
        "I meet with Bran and Garran to plan how to move against the Sable Chain before they strike back.",
        "I secure the Silver Crow ledger, the manifest, and Marlowe's proof before the Sable Chain can steal them.",
        "I scout the streets around the River Gate safehouse for Sable Chain watchers.",
        "I shadow the Sable Chain watchers from the safehouse to learn where they report.",
        "I follow the watchers to the River Gate warehouses.",
        "I inspect the River Gate warehouse marks, crates, and chalk signs for Sable Chain codes.",
        "I search the warehouse office for Sable Chain countermove orders.",
        "I rush back to warn Bran and Garran that the Sable Chain plans to burn the evidence and silence witnesses.",
        "I help Bran and Garran prepare the safehouse defense and protect the evidence before the Sable Chain strike.",
        "I intercept the Sable Chain strike team before they can burn the safehouse evidence.",
        "I capture the strike team's sealed orders before they can destroy them.",
        "I report to Bran and Garran that the Sable Chain countermove failed and the sealed orders point to a higher handler.",
        # Graph 7
        "I review the sealed orders with Bran and Garran to identify the higher Sable Chain handler.",
        "I decode the handler's route cipher from the sealed orders.",
        "I warn the east road teamsters that the Sable Chain handler plans to choke the supply route.",
        "I scout the east road for roadblocks, chokepoints, and Sable Chain pressure points.",
        "I disable the false toll markers the Sable Chain placed along the east road.",
        "I search the old milepost for the Sable Chain handler's dead drop.",
        "I read the route pressure instructions from the handler's dead drop.",
        "I travel to Black Ford before the Sable Chain handler's people can seize the crossing.",
        "I confront the Sable Chain route pressure agents at Black Ford and order them to stand down.",
        "I secure the Black Ford crossing so the teamsters can keep the east road open.",
        "I study the captured route papers to identify the Sable Chain handler's signature.",
        "I return to Bran and Garran with the name of the Sable Chain handler: Veska.",
    ]

    state = _apply_actions(state, actions)
    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")

    assert arc["graph_count"] == 9
    assert arc["completed_graph_count"] == 7
    assert arc["campaign_graphs_complete"] is False
    assert arc["completed_node_count"] >= 85
    assert "graph:tavern_story_seed:sable_chain_handler_route_pressure" in arc["completed_graph_ids"]
    assert "fact:allies_know_handler_veska" in state["progression_facts"]
    assert "lead:handler_veska_next_arc" in state["progression_leads"]

def test_six_graph_campaign_progresses_through_sable_chain_countermove():
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
        # Graph 6
        "I meet with Bran and Garran to plan how to move against the Sable Chain before they strike back.",
        "I secure the Silver Crow ledger, the manifest, and Marlowe's proof before the Sable Chain can steal them.",
        "I scout the streets around the River Gate safehouse for Sable Chain watchers.",
        "I shadow the Sable Chain watchers from the safehouse to learn where they report.",
        "I follow the watchers to the River Gate warehouses.",
        "I inspect the River Gate warehouse marks, crates, and chalk signs for Sable Chain codes.",
        "I search the warehouse office for Sable Chain countermove orders.",
        "I rush back to warn Bran and Garran that the Sable Chain plans to burn the evidence and silence witnesses.",
        "I help Bran and Garran prepare the safehouse defense and protect the evidence before the Sable Chain strike.",
        "I intercept the Sable Chain strike team before they can burn the safehouse evidence.",
        "I capture the strike team's sealed orders before they can destroy them.",
        "I report to Bran and Garran that the Sable Chain countermove failed and the sealed orders point to a higher handler.",
    ]

    state = _apply_actions(state, actions)
    arc = build_scenario_progression_arc_summary(state, scenario_seed="tavern_story_seed")

    assert arc["graph_count"] == 9
    assert arc["completed_graph_count"] == 6
    assert arc["campaign_graphs_complete"] is False
    assert arc["completed_node_count"] >= 73
    assert "graph:tavern_story_seed:sable_chain_countermove" in arc["completed_graph_ids"]
    assert "fact:sable_chain_countermove_thwarted" in state["progression_facts"]
    assert "lead:sable_chain_handler_next_arc" in state["progression_leads"]

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

    assert arc["graph_count"] == 9
    assert arc["completed_graph_count"] == 5
    assert arc["campaign_graphs_complete"] is False
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

    assert arc["graph_count"] == 9
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

    assert arc["graph_count"] == 9
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
    assert arc["graph_count"] == 9
    assert arc["active_graph_id"] == "graph:tavern_story_seed:north_road_shrine"
    assert state["scenario_progression_active_graph_id"] == "graph:tavern_story_seed:north_road_shrine"
    assert state["scenario_progression_waiting_for_next_graph_pack"] is False
    assert actions_after_complete
    assert actions_after_complete[0]["action_id"] == "travel_to_north_road_shrine"
