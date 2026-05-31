from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


def _rusty_flagon_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:witness_to_quarry",
        scenario_seed="tavern_story_seed",
        title="Witness Search → Warn the Wagon → Quarry Road Ambush",
        priority=100,
        nodes=[
            ProgressionNode(
                node_id="ask_bran_about_tension",
                title="Ask the innkeeper why the tavern feels tense.",
                requires=[],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["tension", "trouble", "tense"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_bran_about_tension",
                        "I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=100,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:witness_left_side_door",
                        "text": "A cloaked traveler left through the side door in fear.",
                    },
                    {"unlock_npc": "npc:mira", "name": "Mira"},
                    {"unlock_location": "location:side_door", "name": "Side Door"},
                    {"unlock_objective": "objective:find_witness"},
                    {"start_quest": "quest:witness_search", "title": "Witness Search"},
                ],
                priority=100,
            ),
            ProgressionNode(
                node_id="ask_bran_who_left_side_door",
                title="Ask Bran who left through the side door.",
                requires=[{"fact": "fact:witness_left_side_door"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["side door", "traveler", "witness", "left"],
                    },
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["who", "afraid", "left"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_bran_who_left_side_door",
                        "I ask Bran who left through the side door and why they were afraid.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=95,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:cloaked_traveler",
                        "text": "The witness was a cloaked traveler.",
                    },
                    {
                        "unlock_fact": "fact:traveler_feared_patrol_or_bandits",
                        "text": "The traveler feared someone watching the road.",
                    },
                    {"advance_objective": "objective:find_witness", "amount": 1},
                ],
                priority=95,
            ),
            ProgressionNode(
                node_id="ask_bran_direction",
                title="Ask Bran which direction the traveler went.",
                requires=[{"fact": "fact:cloaked_traveler"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["direction", "went", "where", "road"],
                    },
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["where did", "where they", "after leaving"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_bran_direction",
                        "I ask Bran what direction the cloaked traveler went after leaving.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=90,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:east_road_direction",
                        "text": "The traveler fled toward the old east road.",
                    },
                    {
                        "unlock_lead": "lead:ask_mira",
                        "text": "Mira saw the traveler near the side door.",
                    },
                    {"unlock_objective": "objective:ask_mira"},
                ],
                priority=90,
            ),
            ProgressionNode(
                node_id="ask_mira_side_door",
                title="Ask Mira what she saw near the side door.",
                requires=[{"lead": "lead:ask_mira"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:mira",
                        "topics_any": ["side door", "traveler", "saw", "witness"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_mira_side_door",
                        "I turn to Mira and ask what she saw near the side door.",
                        "ask",
                        target_type="npc",
                        target_id="npc:mira",
                        priority=100,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:blood_on_latch",
                        "text": "The traveler left blood on the side-door latch.",
                    },
                    {
                        "unlock_fact": "fact:bridge_warning",
                        "text": "The traveler warned about a bridge.",
                    },
                    {
                        "unlock_location": "location:side_door_latch",
                        "name": "Side-Door Latch",
                    },
                    {"advance_objective": "objective:ask_mira", "amount": 1},
                    {"unlock_objective": "objective:inspect_side_door"},
                ],
                priority=100,
            ),
            ProgressionNode(
                node_id="inspect_side_door",
                title="Inspect the side door for physical evidence.",
                requires=[{"fact": "fact:blood_on_latch"}],
                action_patterns=[
                    {
                        "semantic": "inspect",
                        "target_id": "location:side_door_latch",
                        "topics_any": ["blood", "latch", "track", "print", "cloth"],
                    },
                    {
                        "semantic": "inspect",
                        "topics_any": ["side door", "latch", "threshold"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "inspect_side_door",
                        "I inspect the side door, latch, and threshold for blood, tracks, or torn cloth.",
                        "inspect",
                        target_type="location",
                        target_id="location:side_door_latch",
                        priority=100,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:boot_print_outside",
                        "text": "A muddy boot print points outside.",
                    },
                    {
                        "unlock_lead": "lead:ask_bran_bridge",
                        "text": "Ask Bran whether the old east road leads to a bridge.",
                    },
                    {"advance_objective": "objective:inspect_side_door", "amount": 1},
                ],
                priority=100,
            ),
            ProgressionNode(
                node_id="ask_bran_bridge",
                title="Ask Bran whether the old east road leads to a bridge.",
                requires=[{"lead": "lead:ask_bran_bridge"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["bridge", "east road", "old road"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_bran_bridge",
                        "I ask Bran if the old east road leads to a bridge.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=95,
                    )
                ],
                effects=[
                    {"unlock_location": "location:mill_bridge", "name": "Mill Bridge"},
                    {
                        "unlock_fact": "fact:mill_bridge_ambush_risk",
                        "text": "The mill bridge is a likely ambush point.",
                    },
                    {"unlock_npc": "npc:local_patron", "name": "Local Patron"},
                    {
                        "unlock_lead": "lead:ask_patron_bridge",
                        "text": "A local patron may know about the bridge.",
                    },
                ],
                priority=95,
            ),
            ProgressionNode(
                node_id="ask_patron_bridge",
                title="Ask the local patron about the mill bridge.",
                requires=[{"lead": "lead:ask_patron_bridge"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:local_patron",
                        "topics_any": ["bridge", "lanterns", "bandits", "wagons"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_patron_bridge",
                        "I approach the local patron and quietly ask what he knows about the mill bridge.",
                        "ask",
                        target_type="npc",
                        target_id="npc:local_patron",
                        priority=100,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:bandits_watch_wagons",
                        "text": "Bandits have watched wagons near the mill bridge.",
                    },
                    {
                        "unlock_lead": "lead:report_findings_to_bran",
                        "text": "Report the bridge evidence to Bran.",
                    },
                    {"advance_objective": "objective:find_witness", "amount": 2},
                ],
                priority=100,
            ),
            ProgressionNode(
                node_id="report_findings_to_bran",
                title="Report the witness and bridge evidence to Bran.",
                requires=[{"fact": "fact:bandits_watch_wagons"}],
                action_patterns=[
                    {
                        "semantic": "report",
                        "target_id": "npc:bran",
                        "topics_any": ["bridge", "bandits", "trail", "findings", "evidence"],
                    },
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["bridge", "bandits", "trail", "findings", "evidence"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "report_findings_to_bran",
                        "I report to Bran that the traveler's trail, the blood, and the bridge story point to an ambush.",
                        "report",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=110,
                    )
                ],
                effects=[
                    {"complete_objective": "objective:find_witness"},
                    {"complete_quest": "quest:witness_search"},
                    {"start_quest": "quest:warn_wagon", "title": "Warn the Wagon"},
                    {"unlock_objective": "objective:travel_to_wagon_yard", "summary": "Travel to Garran's wagon yard."},
                    {"unlock_objective": "objective:warn_garran"},
                    {"unlock_npc": "npc:garran", "name": "Garran"},
                    {"unlock_location": "location:garran_wagon_yard", "name": "Garran's Wagon Yard"},
                    {"unlock_lead": "lead:ask_bran_garran", "text": "Ask Bran who travels the road before dawn."},
                ],
                priority=110,
            ),
            ProgressionNode(
                node_id="ask_bran_garran",
                title="Ask Bran who will travel the road before dawn.",
                requires=[{"lead": "lead:ask_bran_garran"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["wagon", "road", "dawn", "traveler", "who"],
                    },
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["most likely", "travel the road", "before dawn"],
                    },
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["who is most likely", "road before dawn"],
                    },
                    {"semantic": "ask", "topics_any": ["bran", "who", "road", "dawn"]},
                ],
                suggested_actions=[
                    _a(
                        "ask_bran_garran",
                        "I ask Bran who is most likely to travel the road before dawn.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=105,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:garran_supply_wagon",
                        "text": "Garran's supply wagon leaves before dawn.",
                    },
                    {
                        "unlock_lead": "lead:travel_wagon_yard",
                        "text": "Go to Garran's wagon yard.",
                    },
                    {
                        "unlock_objective": "objective:travel_to_wagon_yard",
                        "summary": "Travel to Garran's wagon yard.",
                    },
                ],
                priority=105,
            ),
            ProgressionNode(
                node_id="milestone:prepare_for_mill_road",
                title="Prepare for the mill road",
                requires=[{"lead": "lead:travel_wagon_yard"}],
                action_patterns=[
                    {"semantic": "buy", "topics_any": ["buy", "rations", "supplies"]},
                    {"semantic": "service", "topics_any": ["pay", "rent", "room", "lodging", "rest"]},
                    {"semantic": "party", "topics_any": ["ask", "join", "garran", "help", "road"]},
                ],
                suggested_actions=[
                    _a(
                        "buy_rations_from_bran",
                        "I buy two rations from Bran.",
                        "buy",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=100,
                        mechanic="buying",
                        required_mechanic="buying",
                        completes_mechanic="buying",
                        changed_parts=["inventory_change", "currency_change", "mechanic_completed"],
                        effects={
                            "flags": {
                                "mechanic:buying": True,
                                "mechanic:inventory_change": True,
                                "mechanic:currency_change": True,
                            },
                        },
                        action_terms=["buy", "purchase", "ration", "rations", "supplies", "bran"],
                    ),
                    _a(
                        "rent_room_from_bran",
                        "I pay Bran for a common room and rest.",
                        "service",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=100,
                        mechanic="service_or_lodging",
                        required_mechanic="service_or_lodging",
                        completes_mechanic="service_or_lodging",
                        changed_parts=["service_or_lodging", "currency_change", "mechanic_completed"],
                        effects={
                            "flags": {
                                "mechanic:service_or_lodging": True,
                                "mechanic:currency_change": True,
                            },
                        },
                        action_terms=["rent", "room", "lodging", "rest", "pay bran", "common room"],
                    ),
                    _a(
                        "ask_garran_to_join",
                        "I ask Garran to join me on the mill road.",
                        "party",
                        target_type="npc",
                        target_id="npc:garran",
                        priority=100,
                        mechanic="party_setup",
                        required_mechanic="party_setup",
                        completes_mechanic="party_setup",
                        changed_parts=[
                            "party_setup",
                            "party_recruitment",
                            "companion_added",
                            "mechanic_completed",
                        ],
                        effects={
                            "party": {
                                "add_companion": "npc:garran",
                            },
                            "flags": {
                                "party:garran_recruited": True,
                                "mechanic:party_setup": True,
                                "mechanic:party_recruitment": True,
                            },
                        },
                        display={
                            "narration": "Garran accepts the danger of the mill road and prepares to travel with you.",
                            "npc": {
                                "speaker": "Garran",
                                "line": "If the road is involved, you should not walk it alone.",
                            },
                            "summary": "Garran joins the party for the mill road.",
                        },
                        action_terms=[
                            "ask garran",
                            "garran to join",
                            "join me",
                            "join us",
                            "come with",
                            "come along",
                            "travel with me",
                            "help me on the mill road",
                            "help on the mill road",
                            "watch the road",
                            "road with me",
                            "mill road",
                        ],
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:prepare_for_mill_road", "summary": "Prepare for the mill road by gathering supplies, resting, and securing help."},
                    {"complete_objective": "objective:prepare_for_mill_road"},
                ],
                priority=100,
                objective_type="mechanics_opportunity",
                required_mechanics=[
                    "buying",
                    "service_or_lodging",
                    "party_setup",
                ],
            ),
            ProgressionNode(
                node_id="travel_to_wagon_yard",
                title="Travel to Garran's wagon yard.",
                requires=[{"lead": "lead:travel_wagon_yard"}],
                action_patterns=[
                    {
                        "semantic": "travel",
                        "target_id": "location:garran_wagon_yard",
                        "topics_any": ["wagon yard", "garran", "yard"],
                    },
                    {
                        "semantic": "travel",
                        "topics_any": ["wagon yard", "garran"],
                    },
                    {"semantic": "travel", "topics_any": ["leave the tavern", "garran"]},
                    {"semantic": "travel", "topics_any": ["travel toward", "wagon yard"]},
                    {"semantic": "travel", "topics_any": ["go to", "wagon yard"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_wagon_yard",
                        "I leave the tavern and travel toward Garran's wagon yard.",
                        "travel",
                        target_type="location",
                        target_id="location:garran_wagon_yard",
                        priority=110,
                    )
                ],
                effects=[
                    {
                        "set_location": "location:garran_wagon_yard",
                        "name": "Garran's Wagon Yard",
                    },
                    {
                        "unlock_fact": "fact:reached_garran_yard",
                        "text": "The player reached Garran's wagon yard.",
                    },
                    {"unlock_lead": "lead:warn_garran", "text": "Warn Garran about the bridge ambush."},
                    {"advance_objective": "objective:travel_to_wagon_yard", "amount": 1},
                ],
                priority=110,
            ),
            ProgressionNode(
                node_id="warn_garran",
                title="Warn Garran about the bridge ambush.",
                requires=[{"lead": "lead:warn_garran"}],
                action_patterns=[
                    {
                        "semantic": "warn",
                        "target_id": "npc:garran",
                        "topics_any": ["bridge", "ambush", "bandits", "wagon"],
                    },
                    {
                        "semantic": "tell",
                        "target_id": "npc:garran",
                        "topics_any": ["bridge", "ambush", "bandits", "wagon"],
                    },
                    {"semantic": "warn", "topics_any": ["garran", "bridge", "ambush"]},
                    {"semantic": "tell", "topics_any": ["garran", "bridge", "ambush"]},
                    {"semantic": "report", "topics_any": ["garran", "bridge", "ambush"]},
                ],
                suggested_actions=[
                    _a(
                        "warn_garran",
                        "I tell Garran the mill bridge may be an ambush and show him the evidence.",
                        "warn",
                        target_type="npc",
                        target_id="npc:garran",
                        priority=115,
                    )
                ],
                effects=[
                    {"advance_objective": "objective:warn_garran", "amount": 1},
                    {"complete_objective": "objective:travel_to_wagon_yard"},
                    {
                        "unlock_fact": "fact:garran_warned",
                        "text": "Garran has been warned about the ambush.",
                    },
                    {"unlock_objective": "objective:choose_safe_route"},
                    {
                        "unlock_lead": "lead:alternate_route",
                        "text": "Ask Garran about another route.",
                    },
                ],
                priority=115,
            ),
            ProgressionNode(
                node_id="ask_alternate_route",
                title="Ask Garran about another route.",
                requires=[{"lead": "lead:alternate_route"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:garran",
                        "topics_any": ["route", "around", "bridge", "safe", "alternate"],
                    },
                    {"semantic": "ask", "topics_any": ["garran", "another route"]},
                    {"semantic": "ask", "topics_any": ["garran", "alternate route"]},
                    {"semantic": "ask", "topics_any": ["route around", "bridge"]},
                ],
                suggested_actions=[
                    _a(
                        "ask_alternate_route",
                        "I ask Garran if there is another route around the bridge.",
                        "ask",
                        target_type="npc",
                        target_id="npc:garran",
                        priority=105,
                    )
                ],
                effects=[
                    {"advance_objective": "objective:choose_safe_route", "amount": 1},
                    {"unlock_fact": "fact:quarry_road_option", "text": "The quarry road can bypass the bridge."},
                    {"unlock_location": "location:quarry_road", "name": "Quarry Road"},
                    {"unlock_lead": "lead:prepare_quarry_road", "text": "Prepare the wagon for the quarry road."},
                ],
                priority=105,
            ),
            ProgressionNode(
                node_id="prepare_quarry_road",
                title="Prepare to take the safer route.",
                requires=[{"lead": "lead:prepare_quarry_road"}],
                action_patterns=[
                    {"semantic": "prepare", "topics_any": ["wagon", "quarry", "route", "leave"]},
                    {
                        "semantic": "travel",
                        "target_id": "location:quarry_road",
                        "topics_any": ["quarry road", "leave"],
                    },
                    {"semantic": "prepare", "topics_any": ["prepare", "wagon", "safer route"]},
                    {"semantic": "prepare", "topics_any": ["help", "wagon", "route"]},
                    {"semantic": "travel", "topics_any": ["leave by", "quarry road"]},
                    {"semantic": "travel", "topics_any": ["quarry road", "now"]},
                ],
                suggested_actions=[
                    _a(
                        "prepare_quarry_road",
                        "I help Garran prepare the wagon for the safer route and get ready to leave.",
                        "prepare",
                        target_type="location",
                        target_id="location:garran_wagon_yard",
                        priority=100,
                    ),
                    _a(
                        "leave_by_quarry_road",
                        "I tell Garran and Mira we leave by the quarry road now, before the bridge watchers realize the trick.",
                        "travel",
                        target_type="location",
                        target_id="location:quarry_road",
                        priority=95,
                    ),
                ],
                effects=[
                    {"complete_objective": "objective:choose_safe_route"},
                    {"complete_quest": "quest:warn_wagon"},
                    {"start_quest": "quest:quarry_road_ambush", "title": "Quarry Road Ambush"},
                    {"unlock_objective": "objective:leave_by_quarry_road", "summary": "Leave the wagon yard by the quarry road."},
                    {"unlock_objective": "objective:scout_quarry_road", "summary": "Scout the quarry road for ambush signs."},
                    {"unlock_objective": "objective:spot_bridge_watchers", "summary": "Identify any watchers or scouts near the route."},
                    {"unlock_objective": "objective:choose_ambush_response", "summary": "Choose how to handle the ambush threat."},
                    {"unlock_location": "location:quarry_road", "name": "Quarry Road"},
                    {"unlock_fact": "fact:quarry_road_option", "text": "The quarry road can bypass the bridge."},
                    {"unlock_lead": "lead:quarry_road", "text": "The quarry road avoids the mill bridge."},
                    {"unlock_lead": "lead:leave_by_quarry_road", "text": "Leave the wagon yard by the quarry road."},
                ],
            ),
            ProgressionNode(
                node_id="leave_by_quarry_road",
                title="Leave the wagon yard by the quarry road.",
                requires=[{"lead": "lead:leave_by_quarry_road"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:quarry_road", "topics_any": ["quarry road", "leave"]},
                    {"semantic": "travel", "topics_any": ["leave", "quarry road"]},
                    {"semantic": "travel", "topics_any": ["wagon yard", "quarry road"]},
                    {"semantic": "travel", "topics_any": ["take", "quarry road"]},
                ],
                suggested_actions=[
                    _a(
                        "leave_by_quarry_road",
                        "I leave Garran's wagon yard with the wagon and take the quarry road.",
                        "travel",
                        target_type="location",
                        target_id="location:quarry_road",
                        priority=95,
                    ),
                ],
                effects=[
                    {"set_location": "location:quarry_road", "name": "Quarry Road"},
                    {"advance_objective": "objective:leave_by_quarry_road", "amount": 1},
                    {"complete_objective": "objective:leave_by_quarry_road"},
                    {"unlock_fact": "fact:quarry_road_reached", "text": "The wagon party reached the quarry road."},
                    {"unlock_lead": "lead:scout_quarry_road", "text": "Scout the quarry road before advancing."},
                ],
            ),
            ProgressionNode(
                node_id="scout_quarry_road",
                title="Scout the quarry road.",
                requires=[{"lead": "lead:scout_quarry_road"}],
                action_patterns=[
                    {"semantic": "scout", "target_id": "location:quarry_road", "topics_any": ["quarry road"]},
                    {"semantic": "scout", "topics_any": ["tracks", "hiding places", "ambush signs"]},
                    {"semantic": "scout", "topics_any": ["quarry road", "tracks"]},
                    {"semantic": "inspect", "target_id": "location:quarry_road", "topics_any": ["scout", "quarry road"]},
                    {"semantic": "inspect", "topics_any": ["quarry road", "tracks"]},
                    {"semantic": "inspect", "topics_any": ["ambush signs", "quarry"]},
                    {"semantic": "inspect", "topics_any": ["rocks", "hiding places"]},
                ],
                suggested_actions=[
                    _a(
                        "scout_quarry_road",
                        "I scout ahead on the quarry road for tracks, hiding places, and ambush signs.",
                        "inspect",
                        target_type="location",
                        target_id="location:quarry_road",
                        priority=94,
                    ),
                ],
                effects=[
                    {"advance_objective": "objective:scout_quarry_road", "amount": 1},
                    {"complete_objective": "objective:scout_quarry_road"},
                    {"unlock_fact": "fact:quarry_road_tracks", "text": "Fresh boot tracks cross the quarry road near a rock shelf."},
                    {"unlock_lead": "lead:spot_bridge_watchers", "text": "Look for watchers near the rock shelf."},
                ],
            ),
            ProgressionNode(
                node_id="spot_bridge_watchers",
                title="Spot the watchers near the quarry road.",
                requires=[{"lead": "lead:spot_bridge_watchers"}],
                action_patterns=[
                    {"semantic": "scan", "topics_any": ["rock shelf", "watchers"]},
                    {"semantic": "scan", "topics_any": ["watchers", "scouts"]},
                    {"semantic": "scout", "topics_any": ["watchers", "rock shelf"]},
                    {"semantic": "inspect", "topics_any": ["watchers", "rock shelf"]},
                    {"semantic": "inspect", "topics_any": ["lookout", "quarry road"]},
                    {"semantic": "inspect", "topics_any": ["bandit scouts", "rocks"]},
                    {"semantic": "ask", "target_id": "npc:garran", "topics_any": ["watchers", "lookouts", "rock shelf"]},
                ],
                suggested_actions=[
                    _a(
                        "spot_bridge_watchers",
                        "I scan the rock shelf for watchers or scouts watching the quarry road.",
                        "inspect",
                        target_type="location",
                        target_id="location:quarry_road",
                        priority=93,
                    ),
                ],
                effects=[
                    {"advance_objective": "objective:spot_bridge_watchers", "amount": 1},
                    {"complete_objective": "objective:spot_bridge_watchers"},
                    {"unlock_fact": "fact:bandit_watchers_spotted", "text": "Two watchers are hidden near the rock shelf."},
                    {"unlock_lead": "lead:choose_ambush_response", "text": "Decide whether to lure, avoid, or confront the watchers."},
                ],
            ),
            ProgressionNode(
                node_id="choose_ambush_response",
                title="Choose how to respond to the ambush threat.",
                requires=[{"lead": "lead:choose_ambush_response"}],
                action_patterns=[
                    {"semantic": "prepare", "topics_any": ["lure", "watchers"]},
                    {"semantic": "prepare", "topics_any": ["protect", "wagon"]},
                    {"semantic": "prepare", "topics_any": ["avoid", "ambush"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["plan", "watchers", "wagon"]},
                ],
                suggested_actions=[
                    _a(
                        "choose_ambush_response",
                        "I tell Garran we should slow the wagon and lure the watchers into revealing the ambush.",
                        "tell",
                        target_type="npc",
                        target_id="npc:garran",
                        priority=92,
                    ),
                ],
                effects=[
                    {"advance_objective": "objective:choose_ambush_response", "amount": 1},
                    {"complete_objective": "objective:choose_ambush_response"},
                    {"unlock_fact": "fact:ambush_response_chosen", "text": "The party chooses a plan to draw out the ambushers without risking the wagon."},
                    {"unlock_objective": "objective:protect_wagon", "summary": "Protect the wagon while executing the plan."},
                    {"unlock_lead": "lead:protect_wagon", "text": "Protect the wagon while the ambush plan unfolds."},
                ],
            ),
            ProgressionNode(
                node_id="protect_wagon_or_lure_bandits",
                title="Protect the wagon and draw out the ambushers.",
                requires=[{"lead": "lead:protect_wagon"}],
                action_patterns=[
                    {"semantic": "prepare", "topics_any": ["protect", "wagon"]},
                    {"semantic": "prepare", "topics_any": ["lure", "bandits"]},
                    {"semantic": "inspect", "topics_any": ["ambushers", "wagon"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["protect", "wagon"]},
                ],
                suggested_actions=[
                    _a(
                        "protect_wagon_or_lure_bandits",
                        "I help Garran protect the wagon while drawing the ambushers out of hiding.",
                        "prepare",
                        target_type="location",
                        target_id="location:quarry_road",
                        priority=91,
                        mechanic="combat_started",
                        required_mechanic="combat_started",
                        completes_mechanic="combat_resolved",
                        changed_parts=[
                            "combat_started",
                            "combat_resolved",
                            "xp_gain",
                            "mechanic_completed",
                        ],
                        effects={
                            "flags": {
                                "mechanic:combat_started": True,
                                "mechanic:combat_resolved": True,
                                "mechanic:xp_gain": True,
                            },
                        },
                        action_terms=["ambush", "bandit", "fight", "protect", "wagon", "lure"],
                    ),
                ],
                effects=[
                    {"advance_objective": "objective:protect_wagon", "amount": 1},
                    {"complete_objective": "objective:protect_wagon"},
                    {"unlock_fact": "fact:ambushers_drawn_out", "text": "The ambushers are drawn out before they can strike the wagon."},
                    {"complete_quest": "quest:quarry_road_ambush"},
                ],
            ),
        ],
    )
    return graph
