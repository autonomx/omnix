from __future__ import annotations

from typing import Any, Dict, List

from app.rpg.progression.models import (
    ProgressionAction,
    ProgressionNode,
    ScenarioProgressionGraph,
)


def _a(
    action_id: str,
    command: str,
    semantic: str,
    *,
    target_type: str = "",
    target_id: str = "",
    priority: int = 50,
    mechanic: str = "",
    required_mechanic: str = "",
    completes_mechanic: str = "",
    completion_flags: List[str] = None,
    changed_parts: List[str] = None,
    effects: Dict[str, Any] = None,
    display: Dict[str, Any] = None,
    action_terms: List[str] = None,
) -> ProgressionAction:
    return ProgressionAction(
        action_id=action_id,
        command=command,
        semantic=semantic,
        target_type=target_type,
        target_id=target_id,
        priority=priority,
        mechanic=mechanic,
        required_mechanic=required_mechanic,
        completes_mechanic=completes_mechanic,
        completion_flags=completion_flags or [],
        changed_parts=changed_parts or [],
        effects=effects or {},
        display=display or {},
        action_terms=action_terms or [],
    )


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


def _build_tavern_aftermath_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:bandit_aftermath",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="question_captured_bandit",
                title="Question the captured bandit about who hired them.",
                requires=[{"fact": "fact:ambushers_drawn_out"}],
                action_patterns=[
                    {"semantic": "ask", "topics_any": ["bandit", "who hired", "ambush"]},
                    {"semantic": "ask", "topics_any": ["captured bandit", "leader"]},
                    {"semantic": "ask", "topics_any": ["who sent", "bandits"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["question", "bandit"]},
                ],
                suggested_actions=[
                    _a(
                        "question_captured_bandit",
                        "I question the captured bandit about who hired them and why they targeted Garran's wagon.",
                        "ask",
                        target_type="npc",
                        target_id="npc:garran",
                        priority=95,
                    )
                ],
                effects=[
                    {"start_quest": "quest:mill_ruins_lead", "title": "Mill Ruins Lead"},
                    {"unlock_objective": "objective:identify_bandit_employer", "summary": "Identify who hired the ambushers."},
                    {"complete_objective": "objective:identify_bandit_employer"},
                    {"unlock_fact": "fact:bandits_hired_by_mill_agent", "text": "The ambushers were paid by someone operating near the old mill ruins."},
                    {"unlock_lead": "lead:search_bandit_satchel", "text": "Search the bandit satchel for proof."},
                ],
            ),
            ProgressionNode(
                node_id="search_bandit_satchel",
                title="Search the bandit satchel for proof.",
                requires=[{"lead": "lead:search_bandit_satchel"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["satchel", "proof"]},
                    {"semantic": "inspect", "topics_any": ["bandit satchel"]},
                    {"semantic": "inspect", "topics_any": ["letter", "coin", "mark"]},
                ],
                suggested_actions=[
                    _a(
                        "search_bandit_satchel",
                        "I search the bandit's satchel for letters, marked coins, or anything tying them to the old mill.",
                        "inspect",
                        priority=94,
                    )
                ],
                effects=[
                    {"unlock_objective": "objective:find_mill_proof", "summary": "Find proof connecting the ambush to the old mill."},
                    {"complete_objective": "objective:find_mill_proof"},
                    {"unlock_fact": "fact:marked_mill_coin", "text": "A marked coin bears the stamp of the abandoned mill storehouse."},
                    {"unlock_lead": "lead:return_to_bran_with_proof", "text": "Return to Bran with the proof."},
                ],
            ),
            ProgressionNode(
                node_id="return_to_bran_with_proof",
                title="Return to Bran with the proof.",
                requires=[{"lead": "lead:return_to_bran_with_proof"}],
                action_patterns=[
                    {"semantic": "travel", "topics_any": ["return", "bran"]},
                    {"semantic": "travel", "topics_any": ["back", "tavern"]},
                    {"semantic": "report", "target_id": "npc:bran", "topics_any": ["proof", "mill"]},
                ],
                suggested_actions=[
                    _a(
                        "return_to_bran_with_proof",
                        "I return to the Rusty Flagon and bring Bran the proof linking the ambush to the old mill.",
                        "travel",
                        target_type="location",
                        target_id="location:rusty_flagon_tavern",
                        priority=93,
                    )
                ],
                effects=[
                    {"set_location": "location:rusty_flagon_tavern", "name": "The Rusty Flagon Tavern"},
                    {"unlock_fact": "fact:bran_seen_mill_proof", "text": "Bran has seen the proof that the old mill is connected to the ambush."},
                    {"unlock_lead": "lead:ask_bran_about_old_mill", "text": "Ask Bran what he knows about the old mill."},
                ],
            ),
            ProgressionNode(
                node_id="ask_bran_about_old_mill",
                title="Ask Bran about the old mill.",
                requires=[{"lead": "lead:ask_bran_about_old_mill"}],
                action_patterns=[
                    {"semantic": "ask", "target_id": "npc:bran", "topics_any": ["old mill", "mill ruins"]},
                    {"semantic": "ask", "topics_any": ["bran", "mill"]},
                    {"semantic": "ask", "topics_any": ["who used the mill"]},
                ],
                suggested_actions=[
                    _a(
                        "ask_bran_about_old_mill",
                        "I ask Bran what he knows about the old mill and who might be using it now.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=92,
                    )
                ],
                effects=[
                    {"unlock_fact": "fact:mill_ruins_smugglers", "text": "Bran says smugglers once used the old mill cellar after the fire."},
                    {"unlock_lead": "lead:travel_to_old_mill", "text": "Travel to the old mill ruins."},
                ],
            ),
            ProgressionNode(
                node_id="travel_to_old_mill",
                title="Travel to the old mill ruins.",
                requires=[{"lead": "lead:travel_to_old_mill"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:old_mill_ruins", "topics_any": ["old mill"]},
                    {"semantic": "travel", "topics_any": ["mill ruins"]},
                    {"semantic": "travel", "topics_any": ["go to", "mill"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_old_mill",
                        "I travel to the old mill ruins to follow the marked coin lead.",
                        "travel",
                        target_type="location",
                        target_id="location:old_mill_ruins",
                        priority=91,
                    )
                ],
                effects=[
                    {"set_location": "location:old_mill_ruins", "name": "Old Mill Ruins"},
                    {"unlock_location": "location:old_mill_ruins", "name": "Old Mill Ruins"},
                    {"unlock_fact": "fact:old_mill_reached", "text": "The old mill ruins have been reached."},
                    {"unlock_lead": "lead:inspect_mill_cellar", "text": "Inspect the old mill cellar."},
                ],
            ),
            ProgressionNode(
                node_id="inspect_mill_cellar",
                title="Inspect the old mill cellar.",
                requires=[{"lead": "lead:inspect_mill_cellar"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["cellar", "mill"]},
                    {"semantic": "inspect", "topics_any": ["trapdoor", "cellar"]},
                    {"semantic": "inspect", "target_id": "location:old_mill_ruins", "topics_any": ["cellar"]},
                ],
                suggested_actions=[
                    _a(
                        "inspect_mill_cellar",
                        "I inspect the old mill cellar, trapdoor, and floor marks for signs of recent use.",
                        "inspect",
                        target_type="location",
                        target_id="location:old_mill_ruins",
                        priority=90,
                    )
                ],
                effects=[
                    {"unlock_objective": "objective:inspect_mill_cellar", "summary": "Inspect the old mill cellar."},
                    {"complete_objective": "objective:inspect_mill_cellar"},
                    {"unlock_fact": "fact:mill_cellar_recent_use", "text": "The mill cellar shows fresh boot prints and scrape marks from moved crates."},
                    {"unlock_lead": "lead:find_smuggler_cache", "text": "Find the hidden smuggler cache."},
                ],
            ),
            ProgressionNode(
                node_id="find_smuggler_cache",
                title="Find the hidden smuggler cache.",
                requires=[{"lead": "lead:find_smuggler_cache"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["cache", "crates"]},
                    {"semantic": "inspect", "topics_any": ["hidden", "smuggler"]},
                    {"semantic": "inspect", "topics_any": ["loose stones", "cellar"]},
                ],
                suggested_actions=[
                    _a(
                        "find_smuggler_cache",
                        "I search behind the loose cellar stones for the smuggler cache.",
                        "inspect",
                        priority=89,
                    )
                ],
                effects=[
                    {"unlock_fact": "fact:smuggler_cache_found", "text": "A hidden cache contains route notes, dried rations, and a wax-sealed order."},
                    {"unlock_lead": "lead:read_wax_sealed_order", "text": "Read the wax-sealed order."},
                ],
            ),
            ProgressionNode(
                node_id="read_wax_sealed_order",
                title="Read the wax-sealed order.",
                requires=[{"lead": "lead:read_wax_sealed_order"}],
                action_patterns=[
                    {"semantic": "read", "topics_any": ["wax sealed order"]},
                    {"semantic": "read", "topics_any": ["wax-sealed order"]},
                    {"semantic": "read", "topics_any": ["sealed order"]},
                    {"semantic": "read", "topics_any": ["hidden smuggler cache"]},
                    {"semantic": "read", "topics_any": ["order", "cache"]},
                    {"semantic": "inspect", "topics_any": ["wax sealed order"]},
                    {"semantic": "inspect", "topics_any": ["sealed order"]},
                    {"semantic": "inspect", "topics_any": ["read", "order"]},
                    {"semantic": "study", "topics_any": ["order"]},
                    {"semantic": "open", "topics_any": ["sealed order"]},
                ],
                suggested_actions=[
                    _a(
                        "read_wax_sealed_order",
                        "I read the wax-sealed order from the hidden smuggler cache.",
                        "inspect",
                        priority=88,
                    )
                ],
                effects=[
                    {"unlock_fact": "fact:order_mentions_black_briar_contact", "text": "The order names a Black Briar contact due at the north road shrine."},
                    {"unlock_lead": "lead:decide_mill_next_step", "text": "Decide whether to set a watch or follow the north road shrine lead."},
                ],
            ),
            ProgressionNode(
                node_id="decide_mill_next_step",
                title="Decide the next move after reading the order.",
                requires=[{"lead": "lead:decide_mill_next_step"}],
                action_patterns=[
                    {"semantic": "decide", "topics_any": ["north road shrine"]},
                    {"semantic": "decide", "topics_any": ["black briar contact"]},
                    {"semantic": "decide", "topics_any": ["follow", "shrine"]},
                    {"semantic": "prepare", "topics_any": ["decide", "follow", "north road shrine"]},
                    {"semantic": "prepare", "topics_any": ["set watch", "shrine"]},
                    {"semantic": "prepare", "topics_any": ["follow", "north road"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["order", "shrine"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["order", "shrine"]},
                ],
                suggested_actions=[
                    _a(
                        "decide_mill_next_step",
                        "I decide to follow the north road shrine lead before the Black Briar contact disappears.",
                        "prepare",
                        priority=87,
                    )
                ],
                effects=[
                    {"complete_quest": "quest:mill_ruins_lead"},
                    {"unlock_fact": "fact:north_road_shrine_next", "text": "The next lead points toward the north road shrine."},
                    {"unlock_lead": "lead:north_road_shrine", "text": "Follow the north road shrine lead."},
                ],
            ),
        ],
    )
    graph.title = "Bandit Aftermath → Mill Ruins Lead"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:witness_to_quarry"]
    graph.starts_after_quest_ids = ["quest:quarry_road_ambush"]
    graph.priority = 90
    return graph


def _build_north_road_shrine_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:north_road_shrine",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="travel_to_north_road_shrine",
                title="Travel to the north road shrine.",
                requires=[{"lead": "lead:north_road_shrine"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:north_road_shrine", "topics_any": ["north road shrine"]},
                    {"semantic": "travel", "topics_any": ["north road", "shrine"]},
                    {"semantic": "travel", "topics_any": ["follow", "shrine lead"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_north_road_shrine",
                        "I travel to the north road shrine to follow the Black Briar contact lead.",
                        "travel",
                        target_type="location",
                        target_id="location:north_road_shrine",
                        priority=95,
                    ),
                ],
                effects=[
                    {"start_quest": "quest:north_road_shrine_contact", "title": "North Road Shrine Contact"},
                    {"unlock_objective": "objective:reach_north_road_shrine", "summary": "Reach the north road shrine."},
                    {"complete_objective": "objective:reach_north_road_shrine"},
                    {"set_location": "location:north_road_shrine", "name": "North Road Shrine"},
                    {"unlock_location": "location:north_road_shrine", "name": "North Road Shrine"},
                    {"unlock_fact": "fact:north_road_shrine_reached", "text": "The north road shrine has been reached."},
                    {"unlock_lead": "lead:inspect_shrine_tracks", "text": "Inspect the shrine grounds for signs of the Black Briar contact."},
                ],
            ),
            ProgressionNode(
                node_id="inspect_shrine_tracks",
                title="Inspect tracks and signs around the shrine.",
                requires=[{"lead": "lead:inspect_shrine_tracks"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["shrine", "tracks"]},
                    {"semantic": "inspect", "topics_any": ["grounds", "footprints"]},
                    {"semantic": "scout", "topics_any": ["shrine", "tracks"]},
                    {"semantic": "search", "topics_any": ["shrine", "signs"]},
                ],
                suggested_actions=[
                    _a(
                        "inspect_shrine_tracks",
                        "I inspect the shrine grounds for fresh tracks, ash, hidden marks, or signs of the Black Briar contact.",
                        "inspect",
                        target_type="location",
                        target_id="location:north_road_shrine",
                        priority=94,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:inspect_shrine_tracks", "summary": "Inspect the shrine grounds."},
                    {"complete_objective": "objective:inspect_shrine_tracks"},
                    {"unlock_fact": "fact:black_briar_tracks_at_shrine", "text": "Fresh tracks and black briar scratches mark the stones near the shrine."},
                    {"unlock_lead": "lead:find_shrine_token", "text": "Find the contact token hidden at the shrine."},
                ],
            ),
            ProgressionNode(
                node_id="find_shrine_token",
                title="Find the hidden contact token.",
                requires=[{"lead": "lead:find_shrine_token"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["token", "shrine"]},
                    {"semantic": "search", "topics_any": ["hidden token"]},
                    {"semantic": "inspect", "topics_any": ["offering bowl", "token"]},
                    {"semantic": "inspect", "topics_any": ["black briar token"]},
                ],
                suggested_actions=[
                    _a(
                        "find_shrine_token",
                        "I search the shrine stones and offering bowl for the hidden Black Briar contact token.",
                        "inspect",
                        target_type="location",
                        target_id="location:north_road_shrine",
                        priority=93,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:black_briar_token_found", "text": "A blackened token is hidden beneath the shrine's cracked offering bowl."},
                    {"unlock_lead": "lead:wait_for_contact_signal", "text": "Wait and watch for the contact signal."},
                ],
            ),
            ProgressionNode(
                node_id="wait_for_contact_signal",
                title="Wait for the contact signal.",
                requires=[{"lead": "lead:wait_for_contact_signal"}],
                action_patterns=[
                    {"semantic": "wait", "topics_any": ["contact", "signal"]},
                    {"semantic": "observe", "topics_any": ["shrine", "signal"]},
                    {"semantic": "listen", "topics_any": ["contact", "road"]},
                    {"semantic": "inspect", "topics_any": ["signal", "contact"]},
                ],
                suggested_actions=[
                    _a(
                        "wait_for_contact_signal",
                        "I hide near the north road shrine and watch for the Black Briar contact signal.",
                        "wait",
                        target_type="location",
                        target_id="location:north_road_shrine",
                        priority=92,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:watch_for_contact_signal", "summary": "Watch for the Black Briar contact signal."},
                    {"complete_objective": "objective:watch_for_contact_signal"},
                    {"unlock_fact": "fact:contact_signal_seen", "text": "A hooded contact gives a three-tap signal on the shrine stone."},
                    {"unlock_lead": "lead:shadow_black_briar_contact", "text": "Shadow the Black Briar contact without being seen."},
                ],
            ),
            ProgressionNode(
                node_id="shadow_black_briar_contact",
                title="Shadow the Black Briar contact.",
                requires=[{"lead": "lead:shadow_black_briar_contact"}],
                action_patterns=[
                    {"semantic": "follow", "topics_any": ["black briar contact"]},
                    {"semantic": "follow", "topics_any": ["hooded contact"]},
                    {"semantic": "shadow", "topics_any": ["contact"]},
                    {"semantic": "travel", "topics_any": ["follow", "contact"]},
                ],
                suggested_actions=[
                    _a(
                        "shadow_black_briar_contact",
                        "I shadow the hooded Black Briar contact from the shrine without revealing myself.",
                        "follow",
                        target_type="npc",
                        target_id="npc:black_briar_contact",
                        priority=91,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:black_briar_contact", "name": "Black Briar Contact"},
                    {"unlock_fact": "fact:black_briar_contact_shadowed", "text": "The contact leaves the shrine and heads toward a ruined tollhouse."},
                    {"unlock_location": "location:ruined_tollhouse", "name": "Ruined Tollhouse"},
                    {"unlock_lead": "lead:reach_ruined_tollhouse", "text": "Follow the contact to the ruined tollhouse."},
                ],
            ),
            ProgressionNode(
                node_id="reach_ruined_tollhouse",
                title="Reach the ruined tollhouse.",
                requires=[{"lead": "lead:reach_ruined_tollhouse"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:ruined_tollhouse", "topics_any": ["ruined tollhouse"]},
                    {"semantic": "travel", "topics_any": ["tollhouse"]},
                    {"semantic": "follow", "topics_any": ["contact", "tollhouse"]},
                ],
                suggested_actions=[
                    _a(
                        "reach_ruined_tollhouse",
                        "I follow the Black Briar contact to the ruined tollhouse.",
                        "travel",
                        target_type="location",
                        target_id="location:ruined_tollhouse",
                        priority=90,
                    ),
                ],
                effects=[
                    {"set_location": "location:ruined_tollhouse", "name": "Ruined Tollhouse"},
                    {"unlock_fact": "fact:ruined_tollhouse_reached", "text": "The ruined tollhouse is being used as a quiet meeting point."},
                    {"unlock_lead": "lead:eavesdrop_tollhouse_meeting", "text": "Eavesdrop on the tollhouse meeting."},
                ],
            ),
            ProgressionNode(
                node_id="eavesdrop_tollhouse_meeting",
                title="Eavesdrop on the tollhouse meeting.",
                requires=[{"lead": "lead:eavesdrop_tollhouse_meeting"}],
                action_patterns=[
                    {"semantic": "listen", "topics_any": ["meeting", "tollhouse"]},
                    {"semantic": "eavesdrop", "topics_any": ["meeting"]},
                    {"semantic": "observe", "topics_any": ["contact", "meeting"]},
                    {"semantic": "inspect", "topics_any": ["meeting", "contact"]},
                ],
                suggested_actions=[
                    _a(
                        "eavesdrop_tollhouse_meeting",
                        "I eavesdrop on the meeting at the ruined tollhouse to learn who the contact serves.",
                        "listen",
                        target_type="location",
                        target_id="location:ruined_tollhouse",
                        priority=89,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:eavesdrop_tollhouse_meeting", "summary": "Eavesdrop on the tollhouse meeting."},
                    {"complete_objective": "objective:eavesdrop_tollhouse_meeting"},
                    {"unlock_fact": "fact:black_briar_mentions_captain_voss", "text": "The contact names Captain Voss as the buyer behind the ambush chain."},
                    {"unlock_lead": "lead:recover_tollhouse_manifest", "text": "Recover the tollhouse manifest before the contact leaves."},
                ],
            ),
            ProgressionNode(
                node_id="recover_tollhouse_manifest",
                title="Recover the tollhouse manifest.",
                requires=[{"lead": "lead:recover_tollhouse_manifest"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["manifest", "tollhouse"]},
                    {"semantic": "search", "topics_any": ["manifest"]},
                    {"semantic": "take", "topics_any": ["manifest"]},
                    {"semantic": "read", "topics_any": ["manifest"]},
                ],
                suggested_actions=[
                    _a(
                        "recover_tollhouse_manifest",
                        "I recover the tollhouse manifest before the Black Briar contact can remove it.",
                        "inspect",
                        target_type="location",
                        target_id="location:ruined_tollhouse",
                        priority=88,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:tollhouse_manifest_recovered", "text": "The manifest lists wagon routes, payment marks, and Captain Voss's initials."},
                    {"unlock_lead": "lead:confront_black_briar_contact", "text": "Confront the Black Briar contact with the manifest."},
                ],
            ),
            ProgressionNode(
                node_id="confront_black_briar_contact",
                title="Confront the Black Briar contact.",
                requires=[{"lead": "lead:confront_black_briar_contact"}],
                action_patterns=[
                    {"semantic": "tell", "target_id": "npc:black_briar_contact", "topics_any": ["manifest", "voss"]},
                    {"semantic": "confront", "topics_any": ["black briar contact"]},
                    {"semantic": "ask", "target_id": "npc:black_briar_contact", "topics_any": ["captain voss"]},
                    {"semantic": "threaten", "topics_any": ["contact", "manifest"]},
                ],
                suggested_actions=[
                    _a(
                        "confront_black_briar_contact",
                        "I confront the Black Briar contact with the recovered manifest and demand the truth about Captain Voss.",
                        "tell",
                        target_type="npc",
                        target_id="npc:black_briar_contact",
                        priority=87,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:contact_implicates_voss", "text": "The contact admits Captain Voss paid for the wagon disruptions."},
                    {"unlock_lead": "lead:return_to_allies_with_voss_proof", "text": "Return to Bran and Garran with proof against Captain Voss."},
                ],
            ),
            ProgressionNode(
                node_id="return_to_allies_with_voss_proof",
                title="Return to Bran and Garran with proof against Voss.",
                requires=[{"lead": "lead:return_to_allies_with_voss_proof"}],
                action_patterns=[
                    {"semantic": "travel", "topics_any": ["return", "bran", "garran"]},
                    {"semantic": "report", "target_id": "npc:bran", "topics_any": ["voss", "proof"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["voss", "proof"]},
                    {"semantic": "travel", "topics_any": ["rusty flagon", "proof"]},
                ],
                suggested_actions=[
                    _a(
                        "return_to_allies_with_voss_proof",
                        "I return to Bran and Garran with the manifest proving Captain Voss is behind the attacks.",
                        "travel",
                        target_type="location",
                        target_id="location:rusty_flagon_tavern",
                        priority=86,
                    ),
                ],
                effects=[
                    {"set_location": "location:rusty_flagon_tavern", "name": "The Rusty Flagon Tavern"},
                    {"unlock_fact": "fact:allies_have_voss_proof", "text": "Bran and Garran now have proof that Captain Voss is behind the wagon attacks."},
                    {"complete_quest": "quest:north_road_shrine_contact"},
                    {"unlock_lead": "lead:captain_voss_next_arc", "text": "Plan the next move against Captain Voss."},
                ],
            ),
        ],
    )
    graph.title = "North Road Shrine → Black Briar Contact"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:bandit_aftermath"]
    graph.starts_after_quest_ids = ["quest:mill_ruins_lead"]
    graph.priority = 80
    return graph


def _build_captain_voss_consequence_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:captain_voss_consequence",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="plan_against_captain_voss",
                title="Plan the next move against Captain Voss.",
                requires=[{"lead": "lead:captain_voss_next_arc"}],
                action_patterns=[
                    {"semantic": "plan", "topics_any": ["captain voss"]},
                    {"semantic": "prepare", "topics_any": ["captain voss"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["voss", "plan"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["voss", "proof"]},
                ],
                suggested_actions=[
                    _a(
                        "plan_against_captain_voss",
                        "I gather Bran and Garran to plan how to use the proof against Captain Voss.",
                        "prepare",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=95,
                    ),
                ],
                effects=[
                    {"start_quest": "quest:captain_voss_consequence", "title": "Captain Voss Consequence"},
                    {"unlock_objective": "objective:plan_against_voss", "summary": "Plan how to use the evidence against Captain Voss."},
                    {"complete_objective": "objective:plan_against_voss"},
                    {"unlock_fact": "fact:allies_plan_against_voss", "text": "Bran and Garran agree the proof must be shown to someone with authority before Voss can bury it."},
                    {"unlock_lead": "lead:identify_voss_allies", "text": "Identify who in town still supports Captain Voss."},
                ],
            ),
            ProgressionNode(
                node_id="identify_voss_allies",
                title="Identify Captain Voss's local allies.",
                requires=[{"lead": "lead:identify_voss_allies"}],
                action_patterns=[
                    {"semantic": "ask", "target_id": "npc:bran", "topics_any": ["voss allies"]},
                    {"semantic": "ask", "topics_any": ["who supports voss"]},
                    {"semantic": "inspect", "topics_any": ["voss allies", "town"]},
                    {"semantic": "ask", "target_id": "npc:garran", "topics_any": ["voss", "guards"]},
                ],
                suggested_actions=[
                    _a(
                        "identify_voss_allies",
                        "I ask Bran and Garran who in town still supports Captain Voss.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=94,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:identify_voss_allies", "summary": "Identify Voss's local allies."},
                    {"complete_objective": "objective:identify_voss_allies"},
                    {"unlock_fact": "fact:voss_has_watch_support", "text": "Some town watchmen still answer privately to Captain Voss."},
                    {"unlock_fact": "fact:magistrate_can_hear_evidence", "text": "The magistrate can force a public hearing if given enough evidence."},
                    {"unlock_lead": "lead:seek_magistrate_hearing", "text": "Seek a magistrate hearing before Voss can react."},
                ],
            ),
            ProgressionNode(
                node_id="seek_magistrate_hearing",
                title="Seek a magistrate hearing.",
                requires=[{"lead": "lead:seek_magistrate_hearing"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:magistrate_hall", "topics_any": ["magistrate"]},
                    {"semantic": "ask", "topics_any": ["magistrate", "hearing"]},
                    {"semantic": "tell", "topics_any": ["magistrate", "evidence"]},
                    {"semantic": "travel", "topics_any": ["magistrate hall"]},
                ],
                suggested_actions=[
                    _a(
                        "seek_magistrate_hearing",
                        "I go to the magistrate hall and request a public hearing against Captain Voss.",
                        "travel",
                        target_type="location",
                        target_id="location:magistrate_hall",
                        priority=93,
                    ),
                ],
                effects=[
                    {"set_location": "location:magistrate_hall", "name": "Magistrate Hall"},
                    {"unlock_location": "location:magistrate_hall", "name": "Magistrate Hall"},
                    {"unlock_objective": "objective:seek_magistrate_hearing", "summary": "Request a hearing with the magistrate."},
                    {"complete_objective": "objective:seek_magistrate_hearing"},
                    {"unlock_fact": "fact:hearing_requested_against_voss", "text": "A formal hearing against Captain Voss has been requested."},
                    {"unlock_lead": "lead:present_manifest_to_magistrate", "text": "Present the tollhouse manifest to the magistrate."},
                ],
            ),
            ProgressionNode(
                node_id="present_manifest_to_magistrate",
                title="Present the manifest to the magistrate.",
                requires=[{"lead": "lead:present_manifest_to_magistrate"}],
                action_patterns=[
                    {"semantic": "tell", "topics_any": ["manifest", "magistrate"]},
                    {"semantic": "show", "topics_any": ["manifest", "evidence"]},
                    {"semantic": "report", "topics_any": ["voss", "manifest"]},
                    {"semantic": "read", "topics_any": ["manifest", "magistrate"]},
                ],
                suggested_actions=[
                    _a(
                        "present_manifest_to_magistrate",
                        "I present the tollhouse manifest and marked evidence to the magistrate.",
                        "tell",
                        target_type="npc",
                        target_id="npc:magistrate",
                        priority=92,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:magistrate", "name": "The Magistrate"},
                    {"unlock_objective": "objective:present_manifest", "summary": "Present the manifest as evidence."},
                    {"complete_objective": "objective:present_manifest"},
                    {"unlock_fact": "fact:magistrate_accepts_manifest", "text": "The magistrate accepts the manifest as credible evidence against Captain Voss."},
                    {"unlock_lead": "lead:secure_public_witnesses", "text": "Secure public witnesses before Voss can intimidate them."},
                ],
            ),
            ProgressionNode(
                node_id="secure_public_witnesses",
                title="Secure public witnesses.",
                requires=[{"lead": "lead:secure_public_witnesses"}],
                action_patterns=[
                    {"semantic": "ask", "target_id": "npc:bran", "topics_any": ["witness"]},
                    {"semantic": "ask", "target_id": "npc:garran", "topics_any": ["testify", "voss"]},
                    {"semantic": "tell", "topics_any": ["witnesses", "hearing"]},
                    {"semantic": "prepare", "topics_any": ["public witnesses"]},
                ],
                suggested_actions=[
                    _a(
                        "secure_public_witnesses",
                        "I ask Bran and Garran to stand as public witnesses at the hearing against Captain Voss.",
                        "ask",
                        target_type="npc",
                        target_id="npc:garran",
                        priority=91,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:secure_public_witnesses", "summary": "Secure public witnesses for the hearing."},
                    {"complete_objective": "objective:secure_public_witnesses"},
                    {"unlock_fact": "fact:bran_and_garran_will_testify", "text": "Bran and Garran agree to testify publicly against Captain Voss."},
                    {"unlock_lead": "lead:counter_voss_intimidation", "text": "Counter Voss's attempt to intimidate the witnesses."},
                ],
            ),
            ProgressionNode(
                node_id="counter_voss_intimidation",
                title="Counter Voss's intimidation attempt.",
                requires=[{"lead": "lead:counter_voss_intimidation"}],
                action_patterns=[
                    {"semantic": "confront", "topics_any": ["voss", "intimidation"]},
                    {"semantic": "protect", "topics_any": ["witnesses"]},
                    {"semantic": "tell", "topics_any": ["watchmen", "stand down"]},
                    {"semantic": "warn", "topics_any": ["voss", "witnesses"]},
                ],
                suggested_actions=[
                    _a(
                        "counter_voss_intimidation",
                        "I protect Bran and Garran from Voss's watchmen and warn the guards that the magistrate has accepted the evidence.",
                        "protect",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=90,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:counter_voss_intimidation", "summary": "Stop Voss's allies from intimidating the witnesses."},
                    {"complete_objective": "objective:counter_voss_intimidation"},
                    {"unlock_fact": "fact:voss_intimidation_failed", "text": "Voss's attempt to intimidate the witnesses fails in public view."},
                    {"unlock_lead": "lead:attend_public_hearing", "text": "Attend the public hearing against Captain Voss."},
                ],
            ),
            ProgressionNode(
                node_id="attend_public_hearing",
                title="Attend the public hearing.",
                requires=[{"lead": "lead:attend_public_hearing"}],
                action_patterns=[
                    {"semantic": "travel", "topics_any": ["public hearing"]},
                    {"semantic": "attend", "topics_any": ["hearing", "voss"]},
                    {"semantic": "tell", "topics_any": ["magistrate", "hearing"]},
                    {"semantic": "observe", "topics_any": ["hearing", "voss"]},
                ],
                suggested_actions=[
                    _a(
                        "attend_public_hearing",
                        "I attend the public hearing and stand with Bran and Garran as the evidence against Captain Voss is heard.",
                        "attend",
                        target_type="location",
                        target_id="location:magistrate_hall",
                        priority=89,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:attend_public_hearing", "summary": "Attend the hearing against Captain Voss."},
                    {"complete_objective": "objective:attend_public_hearing"},
                    {"unlock_fact": "fact:voss_public_hearing_begins", "text": "The public hearing against Captain Voss begins before the magistrate."},
                    {"unlock_lead": "lead:answer_voss_accusation", "text": "Answer Voss's accusation at the hearing."},
                ],
            ),
            ProgressionNode(
                node_id="answer_voss_accusation",
                title="Answer Voss's accusation.",
                requires=[{"lead": "lead:answer_voss_accusation"}],
                action_patterns=[
                    {"semantic": "tell", "topics_any": ["answer", "voss"]},
                    {"semantic": "confront", "topics_any": ["voss", "accusation"]},
                    {"semantic": "report", "topics_any": ["manifest", "witnesses"]},
                    {"semantic": "tell", "target_id": "npc:magistrate", "topics_any": ["proof", "voss"]},
                ],
                suggested_actions=[
                    _a(
                        "answer_voss_accusation",
                        "I answer Captain Voss's accusation by tying the manifest, the marked coin, and the witnesses together.",
                        "tell",
                        target_type="npc",
                        target_id="npc:magistrate",
                        priority=88,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:voss_accusation_countered", "text": "Voss's counter-accusation is answered with the manifest, marked coin, and witness testimony."},
                    {"unlock_lead": "lead:force_voss_response", "text": "Force Captain Voss to respond to the evidence."},
                ],
            ),
            ProgressionNode(
                node_id="force_voss_response",
                title="Force Voss to respond to the evidence.",
                requires=[{"lead": "lead:force_voss_response"}],
                action_patterns=[
                    {"semantic": "confront", "topics_any": ["voss", "evidence"]},
                    {"semantic": "ask", "topics_any": ["voss", "manifest"]},
                    {"semantic": "tell", "topics_any": ["captain voss", "proof"]},
                    {"semantic": "press", "topics_any": ["voss", "truth"]},
                ],
                suggested_actions=[
                    _a(
                        "force_voss_response",
                        "I press Captain Voss to explain why his initials appear on the tollhouse manifest.",
                        "confront",
                        target_type="npc",
                        target_id="npc:captain_voss",
                        priority=87,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:captain_voss", "name": "Captain Voss"},
                    {"unlock_fact": "fact:voss_forced_to_answer", "text": "Captain Voss is forced to answer publicly for the manifest."},
                    {"unlock_lead": "lead:choose_voss_outcome", "text": "Choose whether to demand Voss's arrest, exile, or a wider investigation."},
                ],
            ),
            ProgressionNode(
                node_id="choose_voss_outcome",
                title="Choose the outcome for Captain Voss.",
                requires=[{"lead": "lead:choose_voss_outcome"}],
                action_patterns=[
                    {"semantic": "decide", "topics_any": ["arrest", "voss"]},
                    {"semantic": "decide", "topics_any": ["exile", "voss"]},
                    {"semantic": "decide", "topics_any": ["investigation", "voss"]},
                    {"semantic": "tell", "target_id": "npc:magistrate", "topics_any": ["arrest", "voss"]},
                ],
                suggested_actions=[
                    _a(
                        "choose_voss_outcome",
                        "I ask the magistrate to arrest Captain Voss and open a wider investigation into his faction.",
                        "decide",
                        target_type="npc",
                        target_id="npc:magistrate",
                        priority=86,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:choose_voss_outcome", "summary": "Choose the public consequence for Captain Voss."},
                    {"complete_objective": "objective:choose_voss_outcome"},
                    {"unlock_fact": "fact:voss_arrest_requested", "text": "The party asks the magistrate to arrest Captain Voss and open a wider investigation."},
                    {"unlock_lead": "lead:stabilize_town_after_voss", "text": "Stabilize the town after Voss's faction is exposed."},
                ],
            ),
            ProgressionNode(
                node_id="stabilize_town_after_voss",
                title="Stabilize the town after Voss is exposed.",
                requires=[{"lead": "lead:stabilize_town_after_voss"}],
                action_patterns=[
                    {"semantic": "prepare", "topics_any": ["stabilize", "town"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["town", "safe"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["routes", "safe"]},
                    {"semantic": "plan", "topics_any": ["after voss", "town"]},
                ],
                suggested_actions=[
                    _a(
                        "stabilize_town_after_voss",
                        "I help Bran and Garran stabilize the town and reopen the wagon routes after Voss is exposed.",
                        "prepare",
                        target_type="location",
                        target_id="location:rusty_flagon_tavern",
                        priority=85,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:town_stabilized_after_voss", "text": "The town begins to stabilize as Voss's faction loses its grip."},
                    {"unlock_lead": "lead:next_faction_arc", "text": "Investigate which faction backed Captain Voss."},
                ],
            ),
            ProgressionNode(
                node_id="close_voss_consequence_arc",
                title="Close the Captain Voss consequence arc.",
                requires=[{"lead": "lead:next_faction_arc"}],
                action_patterns=[
                    {"semantic": "report", "topics_any": ["voss", "exposed"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["next faction"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["next faction"]},
                    {"semantic": "plan", "topics_any": ["which faction backed voss"]},
                ],
                suggested_actions=[
                    _a(
                        "close_voss_consequence_arc",
                        "I report back to Bran and Garran that Voss is exposed, then plan to investigate which faction backed him.",
                        "report",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=84,
                    ),
                ],
                effects=[
                    {"complete_quest": "quest:captain_voss_consequence"},
                    {"unlock_fact": "fact:voss_arc_closed", "text": "Captain Voss's local operation is exposed, but the larger faction behind him remains unknown."},
                    {"unlock_lead": "lead:investigate_voss_backers", "text": "Investigate the faction that backed Captain Voss."},
                ],
            ),
        ],
    )
    graph.title = "Captain Voss → Faction Consequence"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:north_road_shrine"]
    graph.starts_after_quest_ids = ["quest:north_road_shrine_contact"]
    graph.priority = 70
    return graph


def _build_voss_backers_investigation_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:voss_backers_investigation",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="review_voss_backer_leads",
                title="Review the leads on Voss's backers.",
                requires=[{"lead": "lead:investigate_voss_backers"}],
                action_patterns=[
                    {"semantic": "review", "topics_any": ["voss backers", "voss"]},
                    {"semantic": "plan", "topics_any": ["voss backers", "voss"]},
                    {"semantic": "ask", "target_id": "npc:bran", "topics_any": ["voss backers", "voss"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["faction backed voss", "voss"]},
                ],
                suggested_actions=[
                    _a(
                        "review_voss_backer_leads",
                        "I review the evidence with Bran and Garran to decide how to identify the faction that backed Captain Voss.",
                        "review",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=95,
                    ),
                ],
                effects=[
                    {"start_quest": "quest:voss_backers_investigation", "title": "Voss Backers Investigation"},
                    {"unlock_objective": "objective:review_voss_backer_leads", "summary": "Review the evidence pointing beyond Captain Voss."},
                    {"complete_objective": "objective:review_voss_backer_leads"},
                    {"unlock_fact": "fact:voss_backers_need_identified", "text": "The evidence shows Captain Voss had outside backing, but the faction remains unidentified."},
                    {"unlock_lead": "lead:trace_voss_payment_marks", "text": "Trace the payment marks from Voss's manifest."},
                ],
            ),
            ProgressionNode(
                node_id="trace_voss_payment_marks",
                title="Trace the payment marks from the manifest.",
                requires=[{"lead": "lead:trace_voss_payment_marks"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["payment marks", "manifest"]},
                    {"semantic": "read", "topics_any": ["manifest", "payment"]},
                    {"semantic": "trace", "topics_any": ["payment marks"]},
                    {"semantic": "study", "topics_any": ["voss manifest"]},
                ],
                suggested_actions=[
                    _a(
                        "trace_voss_payment_marks",
                        "I study the manifest payment marks to trace who funded Captain Voss.",
                        "inspect",
                        target_type="item",
                        target_id="item:tollhouse_manifest",
                        priority=94,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:trace_voss_payment_marks", "summary": "Trace the payment marks in the manifest."},
                    {"complete_objective": "objective:trace_voss_payment_marks"},
                    {"unlock_fact": "fact:payment_marks_match_silver_crow", "text": "The payment marks match an old Silver Crow trading cipher."},
                    {"unlock_lead": "lead:ask_bran_about_silver_crow", "text": "Ask Bran what he knows about the Silver Crow."},
                ],
            ),
            ProgressionNode(
                node_id="ask_bran_about_silver_crow",
                title="Ask Bran about the Silver Crow.",
                requires=[{"lead": "lead:ask_bran_about_silver_crow"}],
                action_patterns=[
                    {"semantic": "ask", "target_id": "npc:bran", "topics_any": ["silver crow"]},
                    {"semantic": "ask", "target_id": "npc:bran", "topics_any": ["trading cipher"]},
                    {"semantic": "ask", "topics_any": ["silver crow faction"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["payment marks"]},
                ],
                suggested_actions=[
                    _a(
                        "ask_bran_about_silver_crow",
                        "I ask Bran what he knows about the Silver Crow cipher on Voss's payment marks.",
                        "ask",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=93,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:identify_silver_crow", "summary": "Identify the Silver Crow connection."},
                    {"complete_objective": "objective:identify_silver_crow"},
                    {"unlock_fact": "fact:bran_knows_silver_crow_smugglers", "text": "Bran says the Silver Crow was a smuggler faction thought to be gone from the region."},
                    {"unlock_lead": "lead:question_old_teamster", "text": "Question the old teamster who once hauled Silver Crow cargo."},
                ],
            ),
            ProgressionNode(
                node_id="question_old_teamster",
                title="Question the old teamster.",
                requires=[{"lead": "lead:question_old_teamster"}],
                action_patterns=[
                    {"semantic": "ask", "target_id": "npc:old_teamster", "topics_any": ["silver crow"]},
                    {"semantic": "ask", "topics_any": ["old teamster", "cargo"]},
                    {"semantic": "question", "topics_any": ["teamster", "silver crow"]},
                    {"semantic": "travel", "topics_any": ["teamster", "wagon yard"]},
                ],
                suggested_actions=[
                    _a(
                        "question_old_teamster",
                        "I question the old teamster at the wagon yard about the Silver Crow cargo routes.",
                        "ask",
                        target_type="npc",
                        target_id="npc:old_teamster",
                        priority=92,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:old_teamster", "name": "Old Teamster"},
                    {"unlock_fact": "fact:teamster_remembers_crow_cache", "text": "The old teamster remembers a Silver Crow cache beneath the abandoned cooperage."},
                    {"unlock_location": "location:abandoned_cooperage", "name": "Abandoned Cooperage"},
                    {"unlock_lead": "lead:travel_to_abandoned_cooperage", "text": "Travel to the abandoned cooperage."},
                ],
            ),
            ProgressionNode(
                node_id="travel_to_abandoned_cooperage",
                title="Travel to the abandoned cooperage.",
                requires=[{"lead": "lead:travel_to_abandoned_cooperage"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:abandoned_cooperage", "topics_any": ["abandoned cooperage"]},
                    {"semantic": "travel", "topics_any": ["cooperage"]},
                    {"semantic": "follow", "topics_any": ["silver crow cache"]},
                    {"semantic": "travel", "topics_any": ["old cooperage"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_abandoned_cooperage",
                        "I travel to the abandoned cooperage to search for the Silver Crow cache.",
                        "travel",
                        target_type="location",
                        target_id="location:abandoned_cooperage",
                        priority=91,
                    ),
                ],
                effects=[
                    {"set_location": "location:abandoned_cooperage", "name": "Abandoned Cooperage"},
                    {"unlock_objective": "objective:reach_abandoned_cooperage", "summary": "Reach the abandoned cooperage."},
                    {"complete_objective": "objective:reach_abandoned_cooperage"},
                    {"unlock_fact": "fact:abandoned_cooperage_reached", "text": "The abandoned cooperage is reached."},
                    {"unlock_lead": "lead:inspect_cooperage_cellar", "text": "Inspect the cooperage cellar for the Silver Crow cache."},
                ],
            ),
            ProgressionNode(
                node_id="inspect_cooperage_cellar",
                title="Inspect the cooperage cellar.",
                requires=[{"lead": "lead:inspect_cooperage_cellar"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["cooperage cellar"]},
                    {"semantic": "search", "topics_any": ["cellar", "cache"]},
                    {"semantic": "inspect", "topics_any": ["silver crow cache"]},
                    {"semantic": "scout", "topics_any": ["cooperage", "cellar"]},
                ],
                suggested_actions=[
                    _a(
                        "inspect_cooperage_cellar",
                        "I inspect the cooperage cellar for hidden doors, cargo marks, or the Silver Crow cache.",
                        "inspect",
                        target_type="location",
                        target_id="location:abandoned_cooperage",
                        priority=90,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:inspect_cooperage_cellar", "summary": "Inspect the cooperage cellar."},
                    {"complete_objective": "objective:inspect_cooperage_cellar"},
                    {"unlock_fact": "fact:cooperage_cellar_has_hidden_door", "text": "The cooperage cellar contains a hidden door marked with the Silver Crow cipher."},
                    {"unlock_lead": "lead:open_silver_crow_cache", "text": "Open the hidden Silver Crow cache."},
                ],
            ),
            ProgressionNode(
                node_id="open_silver_crow_cache",
                title="Open the Silver Crow cache.",
                requires=[{"lead": "lead:open_silver_crow_cache"}],
                action_patterns=[
                    {"semantic": "open", "topics_any": ["silver crow cache"]},
                    {"semantic": "inspect", "topics_any": ["hidden door", "cache"]},
                    {"semantic": "search", "topics_any": ["cache", "ledger"]},
                    {"semantic": "open", "topics_any": ["hidden cache"]},
                ],
                suggested_actions=[
                    _a(
                        "open_silver_crow_cache",
                        "I open the hidden Silver Crow cache beneath the cooperage cellar.",
                        "open",
                        target_type="location",
                        target_id="location:abandoned_cooperage",
                        priority=89,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:silver_crow_cache_opened", "text": "The Silver Crow cache contains coded ledgers and faction seals."},
                    {"unlock_lead": "lead:read_silver_crow_ledger", "text": "Read the coded Silver Crow ledger."},
                ],
            ),
            ProgressionNode(
                node_id="read_silver_crow_ledger",
                title="Read the Silver Crow ledger.",
                requires=[{"lead": "lead:read_silver_crow_ledger"}],
                action_patterns=[
                    {"semantic": "read", "topics_any": ["silver crow ledger"]},
                    {"semantic": "study", "topics_any": ["coded ledger"]},
                    {"semantic": "decipher", "topics_any": ["ledger", "cipher"]},
                    {"semantic": "inspect", "topics_any": ["ledger", "faction seals"]},
                ],
                suggested_actions=[
                    _a(
                        "read_silver_crow_ledger",
                        "I read and decipher the coded Silver Crow ledger from the hidden cache.",
                        "read",
                        target_type="item",
                        target_id="item:silver_crow_ledger",
                        priority=88,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:ledger_names_sable_chain", "text": "The ledger shows the Silver Crow is now funded by a faction called the Sable Chain."},
                    {"unlock_lead": "lead:identify_sable_chain_agent", "text": "Identify the Sable Chain agent behind the payments."},
                ],
            ),
            ProgressionNode(
                node_id="identify_sable_chain_agent",
                title="Identify the Sable Chain agent.",
                requires=[{"lead": "lead:identify_sable_chain_agent"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["sable chain agent"]},
                    {"semantic": "read", "topics_any": ["ledger", "agent"]},
                    {"semantic": "ask", "topics_any": ["sable chain"]},
                    {"semantic": "study", "topics_any": ["faction seals"]},
                ],
                suggested_actions=[
                    _a(
                        "identify_sable_chain_agent",
                        "I compare the ledger names and seals to identify the Sable Chain agent funding the Silver Crow.",
                        "inspect",
                        target_type="item",
                        target_id="item:silver_crow_ledger",
                        priority=87,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:sable_chain_agent_is_marlowe", "text": "The ledger points to Agent Marlowe as the Sable Chain handler behind the payments."},
                    {"unlock_npc": "npc:agent_marlowe", "name": "Agent Marlowe"},
                    {"unlock_lead": "lead:locate_agent_marlowe", "text": "Locate Agent Marlowe before the Sable Chain can erase the trail."},
                ],
            ),
            ProgressionNode(
                node_id="locate_agent_marlowe",
                title="Locate Agent Marlowe.",
                requires=[{"lead": "lead:locate_agent_marlowe"}],
                action_patterns=[
                    {"semantic": "travel", "topics_any": ["agent marlowe"]},
                    {"semantic": "ask", "topics_any": ["where is marlowe"]},
                    {"semantic": "follow", "topics_any": ["ledger trail"]},
                    {"semantic": "search", "topics_any": ["agent marlowe"]},
                ],
                suggested_actions=[
                    _a(
                        "locate_agent_marlowe",
                        "I follow the ledger trail to locate Agent Marlowe before the Sable Chain can erase the evidence.",
                        "follow",
                        target_type="npc",
                        target_id="npc:agent_marlowe",
                        priority=86,
                    ),
                ],
                effects=[
                    {"unlock_location": "location:river_gate_safehouse", "name": "River Gate Safehouse"},
                    {"set_location": "location:river_gate_safehouse", "name": "River Gate Safehouse"},
                    {"unlock_fact": "fact:marlowe_safehouse_found", "text": "Agent Marlowe's trail leads to a River Gate safehouse."},
                    {"unlock_lead": "lead:confront_agent_marlowe", "text": "Confront Agent Marlowe at the safehouse."},
                ],
            ),
            ProgressionNode(
                node_id="confront_agent_marlowe",
                title="Confront Agent Marlowe.",
                requires=[{"lead": "lead:confront_agent_marlowe"}],
                action_patterns=[
                    {"semantic": "confront", "target_id": "npc:agent_marlowe", "topics_any": ["sable chain"]},
                    {"semantic": "ask", "target_id": "npc:agent_marlowe", "topics_any": ["voss", "silver crow"]},
                    {"semantic": "tell", "target_id": "npc:agent_marlowe", "topics_any": ["ledger", "proof"]},
                    {"semantic": "press", "topics_any": ["marlowe", "sable chain"]},
                ],
                suggested_actions=[
                    _a(
                        "confront_agent_marlowe",
                        "I confront Agent Marlowe with the Silver Crow ledger and demand the truth about the Sable Chain.",
                        "confront",
                        target_type="npc",
                        target_id="npc:agent_marlowe",
                        priority=85,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:marlowe_confirms_sable_chain", "text": "Agent Marlowe confirms the Sable Chain used the Silver Crow to fund Voss."},
                    {"unlock_lead": "lead:return_with_sable_chain_proof", "text": "Return to the allies with proof of the Sable Chain connection."},
                ],
            ),
            ProgressionNode(
                node_id="return_with_sable_chain_proof",
                title="Return with proof of the Sable Chain connection.",
                requires=[{"lead": "lead:return_with_sable_chain_proof"}],
                action_patterns=[
                    {"semantic": "travel", "topics_any": ["return", "sable chain proof"]},
                    {"semantic": "report", "target_id": "npc:bran", "topics_any": ["sable chain"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["marlowe", "proof"]},
                    {"semantic": "travel", "topics_any": ["rusty flagon", "proof"]},
                ],
                suggested_actions=[
                    _a(
                        "return_with_sable_chain_proof",
                        "I return to Bran and Garran with proof that the Sable Chain backed Captain Voss through the Silver Crow.",
                        "report",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=84,
                    ),
                ],
                effects=[
                    {"set_location": "location:rusty_flagon_tavern", "name": "The Rusty Flagon Tavern"},
                    {"unlock_fact": "fact:allies_have_sable_chain_proof", "text": "Bran and Garran now have proof that the Sable Chain backed Captain Voss through the Silver Crow."},
                    {"complete_quest": "quest:voss_backers_investigation"},
                    {"unlock_lead": "lead:sable_chain_next_arc", "text": "Plan how to move against the Sable Chain."},
                ],
            ),
        ],
    )
    graph.title = "Voss Backers → Sable Chain Investigation"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:captain_voss_consequence"]
    graph.starts_after_quest_ids = ["quest:captain_voss_consequence"]
    graph.priority = 60
    return graph


def _caravan_ambush_graph() -> ScenarioProgressionGraph:
    return ScenarioProgressionGraph(
        graph_id="progression:caravan_ambush_aftermath_waystation:v1",
        scenario_seed="caravan_ambush_seed",
        nodes=[
            ProgressionNode(
                node_id="ask_selka_what_happened",
                title="Ask Selka how the ambush began while helping the survivors.",
                requires=[],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:selka",
                        "topics_any": ["ambush", "attack", "survivors", "happened"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_selka_what_happened",
                        "I hurry to Selka, help stabilize the wounded, and ask how the ambush began.",
                        "ask",
                        target_type="npc",
                        target_id="npc:selka",
                        priority=100,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:ridge_crossbow_volley",
                        "text": "The attack opened with a disciplined crossbow volley from the ridge.",
                    },
                    {"unlock_location": "location:burned_wagons", "name": "Burned Wagons"},
                    {"unlock_npc": "npc:orren", "name": "Orren"},
                    {"start_quest": "quest:caravan_aftermath", "title": "Caravan Aftermath"},
                    {"unlock_objective": "objective:inspect_wreckage"},
                    {
                        "unlock_lead": "lead:inspect_wreckage",
                        "text": "Search the wreckage before smoke and scavengers erase the evidence.",
                    },
                ],
                priority=100,
            ),
            ProgressionNode(
                node_id="inspect_burned_wagons",
                title="Inspect the burned wagons for signs of a planned strike.",
                requires=[{"lead": "lead:inspect_wreckage"}],
                action_patterns=[
                    {
                        "semantic": "inspect",
                        "target_id": "location:burned_wagons",
                        "topics_any": ["wagon", "wreckage", "burned", "bolts", "oil"],
                    },
                    {
                        "semantic": "inspect",
                        "topics_any": ["burned wagons", "wreckage", "ravine"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "inspect_burned_wagons",
                        "I inspect the burned wagons for broken bolts, fire oil, and anything the attackers left behind.",
                        "inspect",
                        target_type="location",
                        target_id="location:burned_wagons",
                        priority=98,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:fire_oil_flask",
                        "text": "A smashed fire-oil flask suggests the wagons were meant to burn fast.",
                    },
                    {
                        "unlock_fact": "fact:missing_lockbox_mount",
                        "text": "One wagon has an empty mount where a lockbox was deliberately removed.",
                    },
                    {"advance_objective": "objective:inspect_wreckage", "amount": 1},
                    {"unlock_objective": "objective:ask_orren_manifest"},
                    {
                        "unlock_lead": "lead:ask_orren_manifest",
                        "text": "Ask Orren which cargo was valuable enough to target.",
                    },
                ],
                priority=98,
            ),
            ProgressionNode(
                node_id="ask_orren_about_missing_cargo",
                title="Ask Orren what cargo the attackers were really after.",
                requires=[{"lead": "lead:ask_orren_manifest"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:orren",
                        "topics_any": ["cargo", "manifest", "missing", "lockbox", "taken"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "ask_orren_about_missing_cargo",
                        "I question Orren about the missing cargo, the wagon manifest, and what the attackers chose to take.",
                        "ask",
                        target_type="npc",
                        target_id="npc:orren",
                        priority=96,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:blue_dye_crate_targeted",
                        "text": "Orren admits only the indigo-marked strongbox crate was taken.",
                    },
                    {
                        "unlock_fact": "fact:manifest_marked_for_waystation",
                        "text": "The missing crate was due for delivery at Ashfall Waystation.",
                    },
                    {"advance_objective": "objective:ask_orren_manifest", "amount": 1},
                    {"unlock_objective": "objective:follow_ravine_tracks"},
                    {
                        "unlock_lead": "lead:follow_ravine_tracks",
                        "text": "Follow the attackers' route away from the wagons before the wind wipes it out.",
                    },
                ],
                priority=96,
            ),
            ProgressionNode(
                node_id="follow_ravine_tracks",
                title="Follow the attackers' path out of Ember Ravine.",
                requires=[{"lead": "lead:follow_ravine_tracks"}],
                action_patterns=[
                    {
                        "semantic": "travel",
                        "topics_any": ["ravine", "tracks", "trail", "ridge", "follow"],
                    },
                    {
                        "semantic": "inspect",
                        "topics_any": ["tracks", "ravine", "boots", "hoofprints"],
                    },
                    {
                        "topics_any": ["follow", "tracks", "ravine", "ridge", "hoofprints"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "follow_ravine_tracks",
                        "I follow the attackers' tracks through Ember Ravine, checking the ridge and wash for hoofprints and boot marks.",
                        "travel",
                        target_type="location",
                        target_id="location:ember_ravine",
                        priority=97,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:mercenary_boot_pattern",
                        "text": "The tracks show matching boot patterns more like hired soldiers than desperate bandits.",
                    },
                    {
                        "unlock_fact": "fact:trail_to_waystation",
                        "text": "The attackers broke off toward Ashfall Waystation instead of the open hills.",
                    },
                    {"unlock_location": "location:ashfall_waystation", "name": "Ashfall Waystation"},
                    {
                        "unlock_lead": "lead:report_selka_waystation",
                        "text": "Report that the ambush points toward Ashfall Waystation.",
                    },
                ],
                priority=97,
            ),
            ProgressionNode(
                node_id="report_waystation_link_to_selka",
                title="Report the waystation lead back to Selka.",
                requires=[{"lead": "lead:report_selka_waystation"}],
                action_patterns=[
                    {
                        "semantic": "report",
                        "target_id": "npc:selka",
                        "topics_any": ["waystation", "mercenary", "tracks", "report", "evidence"],
                    },
                    {
                        "semantic": "ask",
                        "target_id": "npc:selka",
                        "topics_any": ["waystation", "mercenary", "tracks", "evidence"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "report_waystation_link_to_selka",
                        "I report to Selka that the tracks look mercenary and lead toward Ashfall Waystation.",
                        "report",
                        target_type="npc",
                        target_id="npc:selka",
                        priority=105,
                    )
                ],
                effects=[
                    {"complete_quest": "quest:caravan_aftermath"},
                    {"start_quest": "quest:waystation_conspiracy", "title": "Waystation Conspiracy"},
                    {"unlock_objective": "objective:travel_waystation"},
                    {
                        "unlock_lead": "lead:travel_waystation",
                        "text": "Reach Ashfall Waystation before whoever arranged the ambush disappears.",
                    },
                    {"unlock_npc": "npc:hadrik", "name": "Hadrik"},
                ],
                priority=105,
            ),
            ProgressionNode(
                node_id="travel_to_ashfall_waystation",
                title="Travel to Ashfall Waystation.",
                requires=[{"lead": "lead:travel_waystation"}],
                action_patterns=[
                    {
                        "semantic": "travel",
                        "target_id": "location:ashfall_waystation",
                        "topics_any": ["ashfall waystation", "waystation", "ride", "travel"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "travel_to_ashfall_waystation",
                        "I leave the ravine and travel straight to Ashfall Waystation before the trail goes cold.",
                        "travel",
                        target_type="location",
                        target_id="location:ashfall_waystation",
                        priority=108,
                    )
                ],
                effects=[
                    {"set_location": "location:ashfall_waystation", "name": "Ashfall Waystation"},
                    {
                        "unlock_fact": "fact:reached_ashfall_waystation",
                        "text": "The player reached Ashfall Waystation while the evidence was still fresh.",
                    },
                    {"advance_objective": "objective:travel_waystation", "amount": 1},
                    {"unlock_objective": "objective:question_hadrik"},
                    {
                        "unlock_lead": "lead:question_hadrik",
                        "text": "Question Hadrik about the marked crate and the mercenary traffic.",
                    },
                ],
                priority=108,
            ),
            ProgressionNode(
                node_id="question_hadrik_about_crate",
                title="Question Hadrik about the missing crate.",
                requires=[{"lead": "lead:question_hadrik"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:hadrik",
                        "topics_any": ["crate", "waystation", "mercenary", "ledger", "arrival"],
                    },
                ],
                suggested_actions=[
                    _a(
                        "question_hadrik_about_crate",
                        "I confront Hadrik and ask who expected the missing crate at Ashfall Waystation and why mercenaries were nearby.",
                        "ask",
                        target_type="npc",
                        target_id="npc:hadrik",
                        priority=110,
                    )
                ],
                effects=[
                    {
                        "unlock_fact": "fact:ledger_page_removed",
                        "text": "A ledger page covering the crate delivery has been torn out in a hurry.",
                    },
                    {
                        "unlock_fact": "fact:inside_contact_confirmed",
                        "text": "Someone at the waystation expected the ambushers and cleared the handoff.",
                    },
                ],
                priority=110,
            ),
        ],
    )


def _build_sable_chain_countermove_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:sable_chain_countermove",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="plan_against_sable_chain",
                title="Plan how to move against the Sable Chain.",
                requires=[{"lead": "lead:sable_chain_next_arc"}],
                action_patterns=[
                    {"semantic": "plan", "topics_any": ["sable chain"]},
                    {"semantic": "prepare", "topics_any": ["sable chain"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["sable chain", "plan"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["marlowe", "sable chain"]},
                ],
                suggested_actions=[
                    _a(
                        "plan_against_sable_chain",
                        "I meet with Bran and Garran to plan how to move against the Sable Chain before they strike back.",
                        "plan",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=95,
                    ),
                ],
                effects=[
                    {"start_quest": "quest:sable_chain_countermove", "title": "Sable Chain Countermove"},
                    {"unlock_objective": "objective:plan_against_sable_chain", "summary": "Plan the next move against the Sable Chain."},
                    {"complete_objective": "objective:plan_against_sable_chain"},
                    {"unlock_fact": "fact:allies_expect_sable_chain_reaction", "text": "Bran and Garran expect the Sable Chain to react now that their agent was exposed."},
                    {"unlock_lead": "lead:secure_sable_chain_evidence", "text": "Secure the evidence before the Sable Chain can steal or destroy it."},
                ],
            ),
            ProgressionNode(
                node_id="secure_sable_chain_evidence",
                title="Secure the Sable Chain evidence.",
                requires=[{"lead": "lead:secure_sable_chain_evidence"}],
                action_patterns=[
                    {"semantic": "protect", "topics_any": ["evidence", "sable chain"]},
                    {"semantic": "secure", "topics_any": ["ledger", "manifest"]},
                    {"semantic": "prepare", "topics_any": ["evidence", "safe"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["guard", "evidence"]},
                ],
                suggested_actions=[
                    _a(
                        "secure_sable_chain_evidence",
                        "I secure the Silver Crow ledger, the manifest, and Marlowe's proof before the Sable Chain can steal them.",
                        "protect",
                        target_type="item",
                        target_id="item:sable_chain_evidence",
                        priority=94,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:secure_sable_chain_evidence", "summary": "Secure the evidence against the Sable Chain."},
                    {"complete_objective": "objective:secure_sable_chain_evidence"},
                    {"unlock_fact": "fact:sable_chain_evidence_secured", "text": "The ledger, manifest, and Marlowe proof are secured under guard."},
                    {"unlock_lead": "lead:detect_safehouse_watchers", "text": "Watch for Sable Chain agents near the safehouse."},
                ],
            ),
            ProgressionNode(
                node_id="detect_safehouse_watchers",
                title="Detect watchers near the safehouse.",
                requires=[{"lead": "lead:detect_safehouse_watchers"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["safehouse", "watchers"]},
                    {"semantic": "scout", "topics_any": ["watchers", "safehouse"]},
                    {"semantic": "observe", "topics_any": ["sable chain agents"]},
                    {"semantic": "scan", "topics_any": ["street", "watchers"]},
                ],
                suggested_actions=[
                    _a(
                        "detect_safehouse_watchers",
                        "I scout the streets around the River Gate safehouse for Sable Chain watchers.",
                        "scout",
                        target_type="location",
                        target_id="location:river_gate_safehouse",
                        priority=93,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:detect_safehouse_watchers", "summary": "Detect Sable Chain watchers near the safehouse."},
                    {"complete_objective": "objective:detect_safehouse_watchers"},
                    {"unlock_fact": "fact:sable_chain_watchers_spotted", "text": "Two Sable Chain watchers are seen tracking the safehouse exits."},
                    {"unlock_lead": "lead:follow_safehouse_watchers", "text": "Follow the watchers to learn where they report."},
                ],
            ),
            ProgressionNode(
                node_id="follow_safehouse_watchers",
                title="Follow the Sable Chain watchers.",
                requires=[{"lead": "lead:follow_safehouse_watchers"}],
                action_patterns=[
                    {"semantic": "follow", "topics_any": ["safehouse watchers"]},
                    {"semantic": "shadow", "topics_any": ["sable chain watchers"]},
                    {"semantic": "track", "topics_any": ["watchers", "report"]},
                    {"semantic": "travel", "topics_any": ["follow", "watchers"]},
                ],
                suggested_actions=[
                    _a(
                        "follow_safehouse_watchers",
                        "I shadow the Sable Chain watchers from the safehouse to learn where they report.",
                        "follow",
                        target_type="npc",
                        target_id="npc:sable_chain_watcher",
                        priority=92,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:sable_chain_watcher", "name": "Sable Chain Watcher"},
                    {"unlock_fact": "fact:watchers_report_to_river_gate", "text": "The watchers report toward the old River Gate warehouses."},
                    {"unlock_location": "location:river_gate_warehouses", "name": "River Gate Warehouses"},
                    {"unlock_lead": "lead:travel_to_river_gate_warehouses", "text": "Travel to the River Gate warehouses."},
                ],
            ),
            ProgressionNode(
                node_id="travel_to_river_gate_warehouses",
                title="Travel to the River Gate warehouses.",
                requires=[{"lead": "lead:travel_to_river_gate_warehouses"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:river_gate_warehouses", "topics_any": ["river gate warehouses"]},
                    {"semantic": "travel", "topics_any": ["warehouses"]},
                    {"semantic": "follow", "topics_any": ["watchers", "warehouses"]},
                    {"semantic": "travel", "topics_any": ["river gate"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_river_gate_warehouses",
                        "I follow the watchers to the River Gate warehouses.",
                        "travel",
                        target_type="location",
                        target_id="location:river_gate_warehouses",
                        priority=91,
                    ),
                ],
                effects=[
                    {"set_location": "location:river_gate_warehouses", "name": "River Gate Warehouses"},
                    {"unlock_objective": "objective:reach_river_gate_warehouses", "summary": "Reach the River Gate warehouses."},
                    {"complete_objective": "objective:reach_river_gate_warehouses"},
                    {"unlock_fact": "fact:river_gate_warehouses_reached", "text": "The River Gate warehouses are reached."},
                    {"unlock_lead": "lead:inspect_warehouse_marks", "text": "Inspect the warehouse marks for Sable Chain signs."},
                ],
            ),
            ProgressionNode(
                node_id="inspect_warehouse_marks",
                title="Inspect the warehouse marks.",
                requires=[{"lead": "lead:inspect_warehouse_marks"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["warehouse marks"]},
                    {"semantic": "search", "topics_any": ["sable chain signs"]},
                    {"semantic": "inspect", "topics_any": ["river gate warehouses"]},
                    {"semantic": "study", "topics_any": ["marks", "warehouse"]},
                ],
                suggested_actions=[
                    _a(
                        "inspect_warehouse_marks",
                        "I inspect the River Gate warehouse marks, crates, and chalk signs for Sable Chain codes.",
                        "inspect",
                        target_type="location",
                        target_id="location:river_gate_warehouses",
                        priority=90,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:inspect_warehouse_marks", "summary": "Inspect the warehouse marks."},
                    {"complete_objective": "objective:inspect_warehouse_marks"},
                    {"unlock_fact": "fact:warehouse_marks_confirm_sable_chain", "text": "Chalk marks on the crates confirm Sable Chain staging activity."},
                    {"unlock_lead": "lead:find_countermove_orders", "text": "Find the Sable Chain countermove orders."},
                ],
            ),
            ProgressionNode(
                node_id="find_countermove_orders",
                title="Find the Sable Chain countermove orders.",
                requires=[{"lead": "lead:find_countermove_orders"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["countermove orders"]},
                    {"semantic": "search", "topics_any": ["orders", "warehouse"]},
                    {"semantic": "read", "topics_any": ["orders", "sable chain"]},
                    {"semantic": "recover", "topics_any": ["orders"]},
                ],
                suggested_actions=[
                    _a(
                        "find_countermove_orders",
                        "I search the warehouse office for Sable Chain countermove orders.",
                        "search",
                        target_type="location",
                        target_id="location:river_gate_warehouses",
                        priority=89,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:countermove_orders_found", "text": "Orders reveal the Sable Chain plans to silence witnesses and burn the safehouse evidence."},
                    {"unlock_lead": "lead:warn_allies_of_sable_chain_strike", "text": "Warn Bran and Garran about the planned strike."},
                ],
            ),
            ProgressionNode(
                node_id="warn_allies_of_sable_chain_strike",
                title="Warn allies about the Sable Chain strike.",
                requires=[{"lead": "lead:warn_allies_of_sable_chain_strike"}],
                action_patterns=[
                    {"semantic": "warn", "target_id": "npc:bran", "topics_any": ["sable chain"]},
                    {"semantic": "warn", "target_id": "npc:garran", "topics_any": ["safehouse evidence"]},
                    {"semantic": "tell", "topics_any": ["orders", "strike"]},
                    {"semantic": "travel", "topics_any": ["return", "warn allies"]},
                ],
                suggested_actions=[
                    _a(
                        "warn_allies_of_sable_chain_strike",
                        "I rush back to warn Bran and Garran that the Sable Chain plans to burn the evidence and silence witnesses.",
                        "warn",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=88,
                    ),
                ],
                effects=[
                    {"set_location": "location:rusty_flagon_tavern", "name": "The Rusty Flagon Tavern"},
                    {"unlock_fact": "fact:allies_warned_of_sable_chain_strike", "text": "Bran and Garran are warned that the Sable Chain plans a strike."},
                    {"unlock_lead": "lead:prepare_safehouse_defense", "text": "Prepare the safehouse defense before the strike begins."},
                ],
            ),
            ProgressionNode(
                node_id="prepare_safehouse_defense",
                title="Prepare the safehouse defense.",
                requires=[{"lead": "lead:prepare_safehouse_defense"}],
                action_patterns=[
                    {"semantic": "prepare", "topics_any": ["safehouse defense"]},
                    {"semantic": "protect", "topics_any": ["evidence", "witnesses"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["defense", "safehouse"]},
                    {"semantic": "plan", "topics_any": ["sable chain strike"]},
                ],
                suggested_actions=[
                    _a(
                        "prepare_safehouse_defense",
                        "I help Bran and Garran prepare the safehouse defense and protect the evidence before the Sable Chain strike.",
                        "prepare",
                        target_type="location",
                        target_id="location:river_gate_safehouse",
                        priority=87,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:prepare_safehouse_defense", "summary": "Prepare the safehouse defense."},
                    {"complete_objective": "objective:prepare_safehouse_defense"},
                    {"unlock_fact": "fact:safehouse_defense_prepared", "text": "The safehouse defense is prepared and the evidence is moved out of immediate danger."},
                    {"unlock_lead": "lead:intercept_sable_chain_strike_team", "text": "Intercept the Sable Chain strike team."},
                ],
            ),
            ProgressionNode(
                node_id="intercept_sable_chain_strike_team",
                title="Intercept the Sable Chain strike team.",
                requires=[{"lead": "lead:intercept_sable_chain_strike_team"}],
                action_patterns=[
                    {"semantic": "confront", "topics_any": ["strike team"]},
                    {"semantic": "intercept", "topics_any": ["sable chain"]},
                    {"semantic": "protect", "topics_any": ["safehouse", "evidence"]},
                    {"semantic": "prepare", "topics_any": ["ambush", "strike team"]},
                ],
                suggested_actions=[
                    _a(
                        "intercept_sable_chain_strike_team",
                        "I intercept the Sable Chain strike team before they can burn the safehouse evidence.",
                        "confront",
                        target_type="npc",
                        target_id="npc:sable_chain_strike_team",
                        priority=86,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:sable_chain_strike_team", "name": "Sable Chain Strike Team"},
                    {"unlock_fact": "fact:sable_chain_strike_team_intercepted", "text": "The Sable Chain strike team is intercepted before they can destroy the evidence."},
                    {"unlock_lead": "lead:capture_sable_chain_orders", "text": "Capture the strike team's sealed orders."},
                ],
            ),
            ProgressionNode(
                node_id="capture_sable_chain_orders",
                title="Capture the strike team's sealed orders.",
                requires=[{"lead": "lead:capture_sable_chain_orders"}],
                action_patterns=[
                    {"semantic": "take", "topics_any": ["sealed orders"]},
                    {"semantic": "recover", "topics_any": ["strike team orders"]},
                    {"semantic": "inspect", "topics_any": ["orders", "strike team"]},
                    {"semantic": "read", "topics_any": ["sealed orders"]},
                ],
                suggested_actions=[
                    _a(
                        "capture_sable_chain_orders",
                        "I capture the strike team's sealed orders before they can destroy them.",
                        "take",
                        target_type="item",
                        target_id="item:sable_chain_sealed_orders",
                        priority=85,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:sealed_orders_name_chain_handler", "text": "The sealed orders name a higher Sable Chain handler coordinating the pressure campaign."},
                    {"unlock_lead": "lead:report_sable_chain_countermove", "text": "Report the thwarted countermove and prepare to pursue the handler."},
                ],
            ),
            ProgressionNode(
                node_id="report_sable_chain_countermove",
                title="Report the thwarted Sable Chain countermove.",
                requires=[{"lead": "lead:report_sable_chain_countermove"}],
                action_patterns=[
                    {"semantic": "report", "target_id": "npc:bran", "topics_any": ["sable chain countermove"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["sealed orders"]},
                    {"semantic": "report", "topics_any": ["strike team", "handler"]},
                    {"semantic": "plan", "topics_any": ["pursue handler"]},
                ],
                suggested_actions=[
                    _a(
                        "report_sable_chain_countermove",
                        "I report to Bran and Garran that the Sable Chain countermove failed and the sealed orders point to a higher handler.",
                        "report",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=84,
                    ),
                ],
                effects=[
                    {"complete_quest": "quest:sable_chain_countermove"},
                    {"unlock_fact": "fact:sable_chain_countermove_thwarted", "text": "The Sable Chain countermove is thwarted and a higher handler is now exposed."},
                    {"unlock_lead": "lead:sable_chain_handler_next_arc", "text": "Pursue the higher Sable Chain handler."},
                ],
            ),
        ],
    )
    graph.title = "Sable Chain Pressure → Safehouse Countermove"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:voss_backers_investigation"]
    graph.starts_after_quest_ids = ["quest:voss_backers_investigation"]
    graph.priority = 50
    return graph


def _build_sable_chain_handler_route_pressure_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:sable_chain_handler_route_pressure",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="review_handler_orders",
                title="Review the sealed orders naming the Sable Chain handler.",
                requires=[{"lead": "lead:sable_chain_handler_next_arc"}],
                action_patterns=[
                    {"semantic": "review", "topics_any": ["sealed orders", "handler"]},
                    {"semantic": "read", "topics_any": ["sealed orders"]},
                    {"semantic": "study", "topics_any": ["sable chain handler"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["handler", "orders"]},
                ],
                suggested_actions=[
                    _a(
                        "review_handler_orders",
                        "I review the sealed orders with Bran and Garran to identify the higher Sable Chain handler.",
                        "review",
                        target_type="item",
                        target_id="item:sable_chain_sealed_orders",
                        priority=95,
                    ),
                ],
                effects=[
                    {"start_quest": "quest:sable_chain_handler_route_pressure", "title": "Sable Chain Handler"},
                    {"unlock_objective": "objective:review_handler_orders", "summary": "Review the sealed orders naming the Sable Chain handler."},
                    {"complete_objective": "objective:review_handler_orders"},
                    {"unlock_fact": "fact:handler_orders_reviewed", "text": "The sealed orders point to a handler using route pressure to isolate the town."},
                    {"unlock_lead": "lead:decode_handler_route_cipher", "text": "Decode the handler's route cipher."},
                ],
            ),
            ProgressionNode(
                node_id="decode_handler_route_cipher",
                title="Decode the handler's route cipher.",
                requires=[{"lead": "lead:decode_handler_route_cipher"}],
                action_patterns=[
                    {"semantic": "decipher", "topics_any": ["route cipher"]},
                    {"semantic": "read", "topics_any": ["cipher", "orders"]},
                    {"semantic": "study", "topics_any": ["handler route"]},
                    {"semantic": "inspect", "topics_any": ["cipher marks"]},
                ],
                suggested_actions=[
                    _a(
                        "decode_handler_route_cipher",
                        "I decode the handler's route cipher from the sealed orders.",
                        "decipher",
                        target_type="item",
                        target_id="item:sable_chain_sealed_orders",
                        priority=94,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:decode_handler_route_cipher", "summary": "Decode the handler's route cipher."},
                    {"complete_objective": "objective:decode_handler_route_cipher"},
                    {"unlock_fact": "fact:handler_targets_east_road", "text": "The cipher shows the handler intends to choke the east road supply route."},
                    {"unlock_lead": "lead:warn_east_road_teamsters", "text": "Warn the east road teamsters about the route pressure."},
                ],
            ),
            ProgressionNode(
                node_id="warn_east_road_teamsters",
                title="Warn the east road teamsters.",
                requires=[{"lead": "lead:warn_east_road_teamsters"}],
                action_patterns=[
                    {"semantic": "warn", "topics_any": ["east road teamsters"]},
                    {"semantic": "tell", "target_id": "npc:old_teamster", "topics_any": ["east road"]},
                    {"semantic": "travel", "topics_any": ["teamsters", "east road"]},
                    {"semantic": "warn", "topics_any": ["route pressure"]},
                ],
                suggested_actions=[
                    _a(
                        "warn_east_road_teamsters",
                        "I warn the east road teamsters that the Sable Chain handler plans to choke the supply route.",
                        "warn",
                        target_type="npc",
                        target_id="npc:old_teamster",
                        priority=93,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:warn_east_road_teamsters", "summary": "Warn the east road teamsters."},
                    {"complete_objective": "objective:warn_east_road_teamsters"},
                    {"unlock_fact": "fact:east_road_teamsters_warned", "text": "The east road teamsters are warned about the handler's route pressure plan."},
                    {"unlock_lead": "lead:scout_east_road_pressure_points", "text": "Scout the east road pressure points."},
                ],
            ),
            ProgressionNode(
                node_id="scout_east_road_pressure_points",
                title="Scout the east road pressure points.",
                requires=[{"lead": "lead:scout_east_road_pressure_points"}],
                action_patterns=[
                    {"semantic": "scout", "topics_any": ["east road", "pressure points"]},
                    {"semantic": "inspect", "topics_any": ["east road", "ambush"]},
                    {"semantic": "scan", "topics_any": ["roadblocks", "east road"]},
                    {"semantic": "travel", "topics_any": ["east road"]},
                ],
                suggested_actions=[
                    _a(
                        "scout_east_road_pressure_points",
                        "I scout the east road for roadblocks, chokepoints, and Sable Chain pressure points.",
                        "scout",
                        target_type="location",
                        target_id="location:east_road",
                        priority=92,
                    ),
                ],
                effects=[
                    {"set_location": "location:east_road", "name": "East Road"},
                    {"unlock_location": "location:east_road", "name": "East Road"},
                    {"unlock_objective": "objective:scout_east_road_pressure_points", "summary": "Scout the east road pressure points."},
                    {"complete_objective": "objective:scout_east_road_pressure_points"},
                    {"unlock_fact": "fact:east_road_pressure_points_found", "text": "Several roadblocks and false toll markers have been set along the east road."},
                    {"unlock_lead": "lead:disable_false_toll_markers", "text": "Disable the false toll markers."},
                ],
            ),
            ProgressionNode(
                node_id="disable_false_toll_markers",
                title="Disable the false toll markers.",
                requires=[{"lead": "lead:disable_false_toll_markers"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["false toll markers"]},
                    {"semantic": "disable", "topics_any": ["toll markers"]},
                    {"semantic": "remove", "topics_any": ["markers"]},
                    {"semantic": "take", "topics_any": ["false toll signs"]},
                ],
                suggested_actions=[
                    _a(
                        "disable_false_toll_markers",
                        "I disable the false toll markers the Sable Chain placed along the east road.",
                        "disable",
                        target_type="location",
                        target_id="location:east_road",
                        priority=91,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:disable_false_toll_markers", "summary": "Disable the false toll markers."},
                    {"complete_objective": "objective:disable_false_toll_markers"},
                    {"unlock_fact": "fact:false_toll_markers_disabled", "text": "The false toll markers are disabled before they can redirect wagon traffic."},
                    {"unlock_lead": "lead:find_handler_dead_drop", "text": "Find the handler's dead drop near the old milepost."},
                ],
            ),
            ProgressionNode(
                node_id="find_handler_dead_drop",
                title="Find the handler's dead drop.",
                requires=[{"lead": "lead:find_handler_dead_drop"}],
                action_patterns=[
                    {"semantic": "search", "topics_any": ["dead drop", "milepost"]},
                    {"semantic": "inspect", "topics_any": ["old milepost"]},
                    {"semantic": "scout", "topics_any": ["dead drop"]},
                    {"semantic": "find", "topics_any": ["handler dead drop"]},
                ],
                suggested_actions=[
                    _a(
                        "find_handler_dead_drop",
                        "I search the old milepost for the Sable Chain handler's dead drop.",
                        "search",
                        target_type="location",
                        target_id="location:east_road",
                        priority=90,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:handler_dead_drop_found", "text": "A dead drop at the old milepost contains route pressure instructions."},
                    {"unlock_lead": "lead:read_route_pressure_instructions", "text": "Read the route pressure instructions."},
                ],
            ),
            ProgressionNode(
                node_id="read_route_pressure_instructions",
                title="Read the route pressure instructions.",
                requires=[{"lead": "lead:read_route_pressure_instructions"}],
                action_patterns=[
                    {"semantic": "read", "topics_any": ["route pressure instructions"]},
                    {"semantic": "study", "topics_any": ["dead drop instructions"]},
                    {"semantic": "inspect", "topics_any": ["instructions", "route"]},
                    {"semantic": "decipher", "topics_any": ["instructions", "handler"]},
                ],
                suggested_actions=[
                    _a(
                        "read_route_pressure_instructions",
                        "I read the route pressure instructions from the handler's dead drop.",
                        "read",
                        target_type="item",
                        target_id="item:route_pressure_instructions",
                        priority=89,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:instructions_name_black_ford", "text": "The instructions name Black Ford as the handler's next pressure point."},
                    {"unlock_location": "location:black_ford", "name": "Black Ford"},
                    {"unlock_lead": "lead:travel_to_black_ford", "text": "Travel to Black Ford before the handler's people arrive."},
                ],
            ),
            ProgressionNode(
                node_id="travel_to_black_ford",
                title="Travel to Black Ford.",
                requires=[{"lead": "lead:travel_to_black_ford"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:black_ford", "topics_any": ["black ford"]},
                    {"semantic": "travel", "topics_any": ["ford"]},
                    {"semantic": "follow", "topics_any": ["handler", "black ford"]},
                    {"semantic": "travel", "topics_any": ["pressure point"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_black_ford",
                        "I travel to Black Ford before the Sable Chain handler's people can seize the crossing.",
                        "travel",
                        target_type="location",
                        target_id="location:black_ford",
                        priority=88,
                    ),
                ],
                effects=[
                    {"set_location": "location:black_ford", "name": "Black Ford"},
                    {"unlock_objective": "objective:reach_black_ford", "summary": "Reach Black Ford."},
                    {"complete_objective": "objective:reach_black_ford"},
                    {"unlock_fact": "fact:black_ford_reached", "text": "Black Ford is reached before the Sable Chain can fully seize the crossing."},
                    {"unlock_lead": "lead:confront_route_pressure_agents", "text": "Confront the route pressure agents at Black Ford."},
                ],
            ),
            ProgressionNode(
                node_id="confront_route_pressure_agents",
                title="Confront the route pressure agents.",
                requires=[{"lead": "lead:confront_route_pressure_agents"}],
                action_patterns=[
                    {"semantic": "confront", "topics_any": ["route pressure agents"]},
                    {"semantic": "intercept", "topics_any": ["agents", "black ford"]},
                    {"semantic": "tell", "topics_any": ["stand down", "agents"]},
                    {"semantic": "protect", "topics_any": ["ford", "teamsters"]},
                ],
                suggested_actions=[
                    _a(
                        "confront_route_pressure_agents",
                        "I confront the Sable Chain route pressure agents at Black Ford and order them to stand down.",
                        "confront",
                        target_type="npc",
                        target_id="npc:route_pressure_agents",
                        priority=87,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:route_pressure_agents", "name": "Route Pressure Agents"},
                    {"unlock_fact": "fact:route_pressure_agents_stopped", "text": "The Sable Chain route pressure agents are stopped at Black Ford."},
                    {"unlock_lead": "lead:secure_black_ford_crossing", "text": "Secure Black Ford for the teamsters."},
                ],
            ),
            ProgressionNode(
                node_id="secure_black_ford_crossing",
                title="Secure Black Ford crossing.",
                requires=[{"lead": "lead:secure_black_ford_crossing"}],
                action_patterns=[
                    {"semantic": "secure", "topics_any": ["black ford crossing"]},
                    {"semantic": "protect", "topics_any": ["crossing", "teamsters"]},
                    {"semantic": "guard", "topics_any": ["black ford"]},
                    {"semantic": "prepare", "topics_any": ["safe crossing"]},
                ],
                suggested_actions=[
                    _a(
                        "secure_black_ford_crossing",
                        "I secure the Black Ford crossing so the teamsters can keep the east road open.",
                        "secure",
                        target_type="location",
                        target_id="location:black_ford",
                        priority=86,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:secure_black_ford_crossing", "summary": "Secure Black Ford crossing."},
                    {"complete_objective": "objective:secure_black_ford_crossing"},
                    {"unlock_fact": "fact:black_ford_crossing_secured", "text": "Black Ford is secured for the teamsters and the east road remains open."},
                    {"unlock_lead": "lead:identify_handler_signature", "text": "Identify the handler's signature from the captured route papers."},
                ],
            ),
            ProgressionNode(
                node_id="identify_handler_signature",
                title="Identify the handler's signature.",
                requires=[{"lead": "lead:identify_handler_signature"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["handler signature"]},
                    {"semantic": "read", "topics_any": ["route papers"]},
                    {"semantic": "decipher", "topics_any": ["signature"]},
                    {"semantic": "study", "topics_any": ["captured route papers"]},
                ],
                suggested_actions=[
                    _a(
                        "identify_handler_signature",
                        "I study the captured route papers to identify the Sable Chain handler's signature.",
                        "inspect",
                        target_type="item",
                        target_id="item:captured_route_papers",
                        priority=85,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:handler_signature_is_veska", "text": "The route papers identify the higher Sable Chain handler as Veska."},
                    {"unlock_npc": "npc:handler_veska", "name": "Handler Veska"},
                    {"unlock_lead": "lead:return_with_veska_name", "text": "Return with Handler Veska's name."},
                ],
            ),
            ProgressionNode(
                node_id="return_with_veska_name",
                title="Return with Handler Veska's name.",
                requires=[{"lead": "lead:return_with_veska_name"}],
                action_patterns=[
                    {"semantic": "report", "target_id": "npc:bran", "topics_any": ["veska"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["handler veska"]},
                    {"semantic": "travel", "topics_any": ["return", "veska"]},
                    {"semantic": "report", "topics_any": ["sable chain handler"]},
                ],
                suggested_actions=[
                    _a(
                        "return_with_veska_name",
                        "I return to Bran and Garran with the name of the Sable Chain handler: Veska.",
                        "report",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=84,
                    ),
                ],
                effects=[
                    {"set_location": "location:rusty_flagon_tavern", "name": "The Rusty Flagon Tavern"},
                    {"complete_quest": "quest:sable_chain_handler_route_pressure"},
                    {"unlock_fact": "fact:allies_know_handler_veska", "text": "Bran and Garran now know Handler Veska is directing Sable Chain pressure against the region."},
                    {"unlock_lead": "lead:handler_veska_next_arc", "text": "Plan how to pursue Handler Veska."},
                ],
            ),
        ],
    )
    graph.title = "Sable Chain Handler → Route Pressure"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:sable_chain_countermove"]
    graph.starts_after_quest_ids = ["quest:sable_chain_countermove"]
    graph.priority = 40
    return graph


def _build_handler_veska_leadership_pursuit_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:handler_veska_leadership_pursuit",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="plan_pursuit_of_handler_veska",
                title="Plan the pursuit of Handler Veska.",
                requires=[{"lead": "lead:handler_veska_next_arc"}],
                action_patterns=[
                    {"semantic": "plan", "topics_any": ["handler veska"]},
                    {"semantic": "prepare", "topics_any": ["veska", "pursuit"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["veska", "plan"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["handler veska"]},
                ],
                suggested_actions=[
                    _a(
                        "plan_pursuit_of_handler_veska",
                        "I meet with Bran and Garran to plan how to pursue Handler Veska before the Sable Chain relocates.",
                        "plan",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=95,
                    ),
                ],
                effects=[
                    {"start_quest": "quest:handler_veska_leadership_pursuit", "title": "Handler Veska Pursuit"},
                    {"unlock_objective": "objective:plan_pursuit_of_veska", "summary": "Plan how to pursue Handler Veska."},
                    {"complete_objective": "objective:plan_pursuit_of_veska"},
                    {"unlock_fact": "fact:veska_pursuit_planned", "text": "Bran and Garran agree that Veska must be found before the Sable Chain relocates."},
                    {"unlock_lead": "lead:trace_veska_courier_route", "text": "Trace Veska's courier route."},
                ],
            ),
            ProgressionNode(
                node_id="trace_veska_courier_route",
                title="Trace Veska's courier route.",
                requires=[{"lead": "lead:trace_veska_courier_route"}],
                action_patterns=[
                    {"semantic": "trace", "topics_any": ["veska courier route"]},
                    {"semantic": "track", "topics_any": ["courier", "veska"]},
                    {"semantic": "inspect", "topics_any": ["courier marks"]},
                    {"semantic": "study", "topics_any": ["route papers", "courier"]},
                ],
                suggested_actions=[
                    _a(
                        "trace_veska_courier_route",
                        "I trace Veska's courier route from the captured route papers and sealed orders.",
                        "trace",
                        target_type="item",
                        target_id="item:captured_route_papers",
                        priority=94,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:trace_veska_courier_route", "summary": "Trace Veska's courier route."},
                    {"complete_objective": "objective:trace_veska_courier_route"},
                    {"unlock_fact": "fact:veska_courier_route_traced", "text": "The courier route points toward the old north watchpost."},
                    {"unlock_location": "location:old_north_watchpost", "name": "Old North Watchpost"},
                    {"unlock_lead": "lead:travel_to_old_north_watchpost", "text": "Travel to the old north watchpost."},
                ],
            ),
            ProgressionNode(
                node_id="travel_to_old_north_watchpost",
                title="Travel to the old north watchpost.",
                requires=[{"lead": "lead:travel_to_old_north_watchpost"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:old_north_watchpost", "topics_any": ["old north watchpost"]},
                    {"semantic": "travel", "topics_any": ["north watchpost"]},
                    {"semantic": "follow", "topics_any": ["courier route", "watchpost"]},
                    {"semantic": "travel", "topics_any": ["veska trail"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_old_north_watchpost",
                        "I travel to the old north watchpost to follow Veska's courier trail.",
                        "travel",
                        target_type="location",
                        target_id="location:old_north_watchpost",
                        priority=93,
                    ),
                ],
                effects=[
                    {"set_location": "location:old_north_watchpost", "name": "Old North Watchpost"},
                    {"unlock_objective": "objective:reach_old_north_watchpost", "summary": "Reach the old north watchpost."},
                    {"complete_objective": "objective:reach_old_north_watchpost"},
                    {"unlock_fact": "fact:old_north_watchpost_reached", "text": "The old north watchpost is reached along Veska's courier route."},
                    {"unlock_lead": "lead:inspect_watchpost_courier_signs", "text": "Inspect the watchpost for courier signs."},
                ],
            ),
            ProgressionNode(
                node_id="inspect_watchpost_courier_signs",
                title="Inspect courier signs at the watchpost.",
                requires=[{"lead": "lead:inspect_watchpost_courier_signs"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["courier signs", "watchpost"]},
                    {"semantic": "search", "topics_any": ["watchpost", "courier"]},
                    {"semantic": "scout", "topics_any": ["watchpost", "veska"]},
                    {"semantic": "study", "topics_any": ["sable chain signs"]},
                ],
                suggested_actions=[
                    _a(
                        "inspect_watchpost_courier_signs",
                        "I inspect the old north watchpost for courier signs, Sable Chain marks, and Veska's trail.",
                        "inspect",
                        target_type="location",
                        target_id="location:old_north_watchpost",
                        priority=92,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:inspect_watchpost_courier_signs", "summary": "Inspect the watchpost for courier signs."},
                    {"complete_objective": "objective:inspect_watchpost_courier_signs"},
                    {"unlock_fact": "fact:watchpost_has_fresh_courier_marks", "text": "Fresh courier marks at the watchpost show Veska's messages are still moving."},
                    {"unlock_lead": "lead:intercept_veska_courier", "text": "Intercept Veska's courier."},
                ],
            ),
            ProgressionNode(
                node_id="intercept_veska_courier",
                title="Intercept Veska's courier.",
                requires=[{"lead": "lead:intercept_veska_courier"}],
                action_patterns=[
                    {"semantic": "intercept", "topics_any": ["courier"]},
                    {"semantic": "confront", "topics_any": ["courier", "veska"]},
                    {"semantic": "stop", "topics_any": ["sable chain courier"]},
                    {"semantic": "track", "topics_any": ["courier"]},
                ],
                suggested_actions=[
                    _a(
                        "intercept_veska_courier",
                        "I intercept Veska's courier before the message can leave the old north watchpost.",
                        "intercept",
                        target_type="npc",
                        target_id="npc:veska_courier",
                        priority=91,
                    ),
                ],
                effects=[
                    {"unlock_npc": "npc:veska_courier", "name": "Veska's Courier"},
                    {"unlock_fact": "fact:veska_courier_intercepted", "text": "Veska's courier is intercepted before the message leaves the watchpost."},
                    {"unlock_lead": "lead:recover_veska_coded_message", "text": "Recover Veska's coded message from the courier."},
                ],
            ),
            ProgressionNode(
                node_id="recover_veska_coded_message",
                title="Recover Veska's coded message.",
                requires=[{"lead": "lead:recover_veska_coded_message"}],
                action_patterns=[
                    {"semantic": "recover", "topics_any": ["coded message"]},
                    {"semantic": "take", "topics_any": ["veska message"]},
                    {"semantic": "search", "topics_any": ["courier", "message"]},
                    {"semantic": "inspect", "topics_any": ["coded message", "veska"]},
                ],
                suggested_actions=[
                    _a(
                        "recover_veska_coded_message",
                        "I recover Veska's coded message from the intercepted courier.",
                        "recover",
                        target_type="item",
                        target_id="item:veska_coded_message",
                        priority=90,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:veska_coded_message_recovered", "text": "Veska's coded message is recovered from the intercepted courier."},
                    {"unlock_lead": "lead:decode_veska_coded_message", "text": "Decode Veska's coded message."},
                ],
            ),
            ProgressionNode(
                node_id="decode_veska_coded_message",
                title="Decode Veska's coded message.",
                requires=[{"lead": "lead:decode_veska_coded_message"}],
                action_patterns=[
                    {"semantic": "decipher", "topics_any": ["coded message"]},
                    {"semantic": "read", "topics_any": ["coded message", "veska"]},
                    {"semantic": "study", "topics_any": ["message", "cipher"]},
                    {"semantic": "inspect", "topics_any": ["veska message"]},
                ],
                suggested_actions=[
                    _a(
                        "decode_veska_coded_message",
                        "I decode Veska's coded message to learn where the Sable Chain leadership is moving.",
                        "decipher",
                        target_type="item",
                        target_id="item:veska_coded_message",
                        priority=89,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:decode_veska_message", "summary": "Decode Veska's coded message."},
                    {"complete_objective": "objective:decode_veska_message"},
                    {"unlock_fact": "fact:veska_message_points_to_ridge_hideout", "text": "The coded message points to a ridge hideout used by Veska's leadership cell."},
                    {"unlock_location": "location:ridge_hideout", "name": "Ridge Hideout"},
                    {"unlock_lead": "lead:travel_to_ridge_hideout", "text": "Travel to the ridge hideout."},
                ],
            ),
            ProgressionNode(
                node_id="travel_to_ridge_hideout",
                title="Travel to the ridge hideout.",
                requires=[{"lead": "lead:travel_to_ridge_hideout"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:ridge_hideout", "topics_any": ["ridge hideout"]},
                    {"semantic": "travel", "topics_any": ["hideout"]},
                    {"semantic": "follow", "topics_any": ["veska", "hideout"]},
                    {"semantic": "travel", "topics_any": ["leadership cell"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_ridge_hideout",
                        "I travel to the ridge hideout before Veska's leadership cell can relocate.",
                        "travel",
                        target_type="location",
                        target_id="location:ridge_hideout",
                        priority=88,
                    ),
                ],
                effects=[
                    {"set_location": "location:ridge_hideout", "name": "Ridge Hideout"},
                    {"unlock_objective": "objective:reach_ridge_hideout", "summary": "Reach Veska's ridge hideout."},
                    {"complete_objective": "objective:reach_ridge_hideout"},
                    {"unlock_fact": "fact:ridge_hideout_reached", "text": "The ridge hideout is reached before Veska's leadership cell can fully relocate."},
                    {"unlock_lead": "lead:scout_ridge_hideout", "text": "Scout the ridge hideout."},
                ],
            ),
            ProgressionNode(
                node_id="scout_ridge_hideout",
                title="Scout the ridge hideout.",
                requires=[{"lead": "lead:scout_ridge_hideout"}],
                action_patterns=[
                    {"semantic": "scout", "topics_any": ["ridge hideout"]},
                    {"semantic": "inspect", "topics_any": ["hideout guards"]},
                    {"semantic": "observe", "topics_any": ["veska", "hideout"]},
                    {"semantic": "scan", "topics_any": ["ridge", "guards"]},
                ],
                suggested_actions=[
                    _a(
                        "scout_ridge_hideout",
                        "I scout the ridge hideout for guards, exits, and signs of Handler Veska.",
                        "scout",
                        target_type="location",
                        target_id="location:ridge_hideout",
                        priority=87,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:scout_ridge_hideout", "summary": "Scout Veska's ridge hideout."},
                    {"complete_objective": "objective:scout_ridge_hideout"},
                    {"unlock_fact": "fact:veska_seen_at_ridge_hideout", "text": "Veska is seen coordinating the Sable Chain leadership cell at the ridge hideout."},
                    {"unlock_lead": "lead:confront_handler_veska", "text": "Confront Handler Veska."},
                ],
            ),
            ProgressionNode(
                node_id="confront_handler_veska",
                title="Confront Handler Veska.",
                requires=[{"lead": "lead:confront_handler_veska"}],
                action_patterns=[
                    {"semantic": "confront", "target_id": "npc:handler_veska", "topics_any": ["veska"]},
                    {"semantic": "tell", "target_id": "npc:handler_veska", "topics_any": ["proof", "sable chain"]},
                    {"semantic": "press", "topics_any": ["veska", "leadership"]},
                    {"semantic": "intercept", "topics_any": ["veska", "hideout"]},
                ],
                suggested_actions=[
                    _a(
                        "confront_handler_veska",
                        "I confront Handler Veska at the ridge hideout with the proof linking her to the Sable Chain route pressure.",
                        "confront",
                        target_type="npc",
                        target_id="npc:handler_veska",
                        priority=86,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:veska_confronted_at_hideout", "text": "Handler Veska is confronted at the ridge hideout with evidence of her leadership role."},
                    {"unlock_lead": "lead:secure_veska_ledgers", "text": "Secure Veska's leadership ledgers."},
                ],
            ),
            ProgressionNode(
                node_id="secure_veska_ledgers",
                title="Secure Veska's leadership ledgers.",
                requires=[{"lead": "lead:secure_veska_ledgers"}],
                action_patterns=[
                    {"semantic": "secure", "topics_any": ["ledgers"]},
                    {"semantic": "recover", "topics_any": ["leadership ledgers"]},
                    {"semantic": "take", "topics_any": ["sable chain ledgers"]},
                    {"semantic": "inspect", "topics_any": ["veska documents"]},
                ],
                suggested_actions=[
                    _a(
                        "secure_veska_ledgers",
                        "I secure Veska's leadership ledgers before the Sable Chain can destroy or move them.",
                        "secure",
                        target_type="item",
                        target_id="item:veska_leadership_ledgers",
                        priority=85,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:veska_ledgers_secured", "text": "Veska's leadership ledgers are secured before they can be destroyed."},
                    {"unlock_lead": "lead:return_with_veska_ledgers", "text": "Return to Bran and Garran with Veska's ledgers."},
                ],
            ),
            ProgressionNode(
                node_id="return_with_veska_ledgers",
                title="Return with Veska's leadership ledgers.",
                requires=[{"lead": "lead:return_with_veska_ledgers"}],
                action_patterns=[
                    {"semantic": "report", "target_id": "npc:bran", "topics_any": ["veska ledgers"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["veska", "leadership"]},
                    {"semantic": "travel", "topics_any": ["return", "veska ledgers"]},
                    {"semantic": "report", "topics_any": ["sable chain leadership"]},
                ],
                suggested_actions=[
                    _a(
                        "return_with_veska_ledgers",
                        "I return to Bran and Garran with Veska's leadership ledgers and proof of the Sable Chain command structure.",
                        "report",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=84,
                    ),
                ],
                effects=[
                    {"set_location": "location:rusty_flagon_tavern", "name": "The Rusty Flagon Tavern"},
                    {"complete_quest": "quest:handler_veska_leadership_pursuit"},
                    {"unlock_fact": "fact:allies_have_veska_ledgers", "text": "Bran and Garran now have Veska's ledgers and proof of the Sable Chain command structure."},
                    {"unlock_lead": "lead:sable_chain_endgame_next_arc", "text": "Plan the final move against the Sable Chain command structure."},
                ],
            ),
        ],
    )
    graph.title = "Handler Veska → Leadership Pursuit"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:sable_chain_handler_route_pressure"]
    graph.starts_after_quest_ids = ["quest:sable_chain_handler_route_pressure"]
    graph.priority = 30
    return graph


def _build_sable_chain_endgame_opener_graph() -> ScenarioProgressionGraph:
    graph = ScenarioProgressionGraph(
        graph_id="graph:tavern_story_seed:sable_chain_endgame_opener",
        scenario_seed="tavern_story_seed",
        nodes=[
            ProgressionNode(
                node_id="review_veska_ledgers_for_command_structure",
                title="Review Veska's ledgers for the Sable Chain command structure.",
                requires=[{"lead": "lead:sable_chain_endgame_next_arc"}],
                action_patterns=[
                    {"semantic": "review", "topics_any": ["veska ledgers", "command structure"]},
                    {"semantic": "read", "topics_any": ["veska ledgers"]},
                    {"semantic": "study", "topics_any": ["sable chain command"]},
                    {"semantic": "tell", "target_id": "npc:bran", "topics_any": ["ledgers", "command structure"]},
                ],
                suggested_actions=[
                    _a(
                        "review_veska_ledgers_for_command_structure",
                        "I review Veska's ledgers with Bran and Garran to map the Sable Chain command structure.",
                        "review",
                        target_type="item",
                        target_id="item:veska_leadership_ledgers",
                        priority=95,
                    ),
                ],
                effects=[
                    {"start_quest": "quest:sable_chain_endgame_opener", "title": "Sable Chain Endgame Opener"},
                    {"unlock_objective": "objective:review_veska_ledgers", "summary": "Review Veska's ledgers to map the Sable Chain command structure."},
                    {"complete_objective": "objective:review_veska_ledgers"},
                    {"unlock_fact": "fact:sable_chain_command_structure_mapped", "text": "Veska's ledgers reveal a command structure built around three courier captains and one hidden paymaster."},
                    {"unlock_lead": "lead:identify_hidden_paymaster", "text": "Identify the hidden Sable Chain paymaster."},
                ],
            ),
            ProgressionNode(
                node_id="identify_hidden_paymaster",
                title="Identify the hidden Sable Chain paymaster.",
                requires=[{"lead": "lead:identify_hidden_paymaster"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["hidden paymaster"]},
                    {"semantic": "read", "topics_any": ["ledger", "paymaster"]},
                    {"semantic": "decipher", "topics_any": ["paymaster cipher"]},
                    {"semantic": "study", "topics_any": ["command structure", "paymaster"]},
                ],
                suggested_actions=[
                    _a(
                        "identify_hidden_paymaster",
                        "I study the ledger entries to identify the hidden Sable Chain paymaster.",
                        "inspect",
                        target_type="item",
                        target_id="item:veska_leadership_ledgers",
                        priority=94,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:identify_hidden_paymaster", "summary": "Identify the hidden paymaster behind the Sable Chain."},
                    {"complete_objective": "objective:identify_hidden_paymaster"},
                    {"unlock_fact": "fact:hidden_paymaster_is_red_lantern", "text": "The hidden paymaster uses the Red Lantern mark in Veska's ledgers."},
                    {"unlock_lead": "lead:trace_red_lantern_payments", "text": "Trace the Red Lantern payment line."},
                ],
            ),
            ProgressionNode(
                node_id="trace_red_lantern_payments",
                title="Trace the Red Lantern payment line.",
                requires=[{"lead": "lead:trace_red_lantern_payments"}],
                action_patterns=[
                    {"semantic": "trace", "topics_any": ["red lantern payments"]},
                    {"semantic": "track", "topics_any": ["payment line"]},
                    {"semantic": "study", "topics_any": ["red lantern ledger"]},
                    {"semantic": "inspect", "topics_any": ["payments", "red lantern"]},
                ],
                suggested_actions=[
                    _a(
                        "trace_red_lantern_payments",
                        "I trace the Red Lantern payment line from Veska's ledgers to find where the Sable Chain money is moving.",
                        "trace",
                        target_type="item",
                        target_id="item:veska_leadership_ledgers",
                        priority=93,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:trace_red_lantern_payments", "summary": "Trace the Red Lantern payment line."},
                    {"complete_objective": "objective:trace_red_lantern_payments"},
                    {"unlock_fact": "fact:red_lantern_payments_point_to_counting_house", "text": "The Red Lantern payment line points to the old counting house near the market ward."},
                    {"unlock_location": "location:old_counting_house", "name": "Old Counting House"},
                    {"unlock_lead": "lead:travel_to_old_counting_house", "text": "Travel to the old counting house."},
                ],
            ),
            ProgressionNode(
                node_id="travel_to_old_counting_house",
                title="Travel to the old counting house.",
                requires=[{"lead": "lead:travel_to_old_counting_house"}],
                action_patterns=[
                    {"semantic": "travel", "target_id": "location:old_counting_house", "topics_any": ["old counting house"]},
                    {"semantic": "travel", "topics_any": ["counting house"]},
                    {"semantic": "follow", "topics_any": ["red lantern", "counting house"]},
                    {"semantic": "travel", "topics_any": ["market ward"]},
                ],
                suggested_actions=[
                    _a(
                        "travel_to_old_counting_house",
                        "I travel to the old counting house near the market ward to follow the Red Lantern payment trail.",
                        "travel",
                        target_type="location",
                        target_id="location:old_counting_house",
                        priority=92,
                    ),
                ],
                effects=[
                    {"set_location": "location:old_counting_house", "name": "Old Counting House"},
                    {"unlock_objective": "objective:reach_old_counting_house", "summary": "Reach the old counting house."},
                    {"complete_objective": "objective:reach_old_counting_house"},
                    {"unlock_fact": "fact:old_counting_house_reached", "text": "The old counting house is reached before the Sable Chain can clear the payment trail."},
                    {"unlock_lead": "lead:inspect_counting_house_records", "text": "Inspect the counting house records."},
                ],
            ),
            ProgressionNode(
                node_id="inspect_counting_house_records",
                title="Inspect the counting house records.",
                requires=[{"lead": "lead:inspect_counting_house_records"}],
                action_patterns=[
                    {"semantic": "inspect", "topics_any": ["counting house records"]},
                    {"semantic": "search", "topics_any": ["records", "payment trail"]},
                    {"semantic": "read", "topics_any": ["ledger", "counting house"]},
                    {"semantic": "study", "topics_any": ["red lantern records"]},
                ],
                suggested_actions=[
                    _a(
                        "inspect_counting_house_records",
                        "I inspect the counting house records for Red Lantern payments and Sable Chain accounts.",
                        "inspect",
                        target_type="location",
                        target_id="location:old_counting_house",
                        priority=91,
                    ),
                ],
                effects=[
                    {"unlock_objective": "objective:inspect_counting_house_records", "summary": "Inspect the counting house records."},
                    {"complete_objective": "objective:inspect_counting_house_records"},
                    {"unlock_fact": "fact:counting_house_records_found", "text": "The counting house records confirm the Red Lantern mark is tied to a Sable Chain paymaster."},
                    {"unlock_lead": "lead:secure_red_lantern_records", "text": "Secure the Red Lantern records before they vanish."},
                ],
            ),
            ProgressionNode(
                node_id="secure_red_lantern_records",
                title="Secure the Red Lantern records.",
                requires=[{"lead": "lead:secure_red_lantern_records"}],
                action_patterns=[
                    {"semantic": "secure", "topics_any": ["red lantern records"]},
                    {"semantic": "recover", "topics_any": ["counting house records"]},
                    {"semantic": "take", "topics_any": ["payment records"]},
                    {"semantic": "protect", "topics_any": ["records", "evidence"]},
                ],
                suggested_actions=[
                    _a(
                        "secure_red_lantern_records",
                        "I secure the Red Lantern payment records before the Sable Chain can destroy them.",
                        "secure",
                        target_type="item",
                        target_id="item:red_lantern_records",
                        priority=90,
                    ),
                ],
                effects=[
                    {"unlock_fact": "fact:red_lantern_records_secured", "text": "The Red Lantern payment records are secured as evidence against the Sable Chain paymaster."},
                    {"unlock_lead": "lead:return_with_red_lantern_records", "text": "Return to Bran and Garran with the Red Lantern records."},
                ],
            ),
            ProgressionNode(
                node_id="return_with_red_lantern_records",
                title="Return with the Red Lantern records.",
                requires=[{"lead": "lead:return_with_red_lantern_records"}],
                action_patterns=[
                    {"semantic": "report", "target_id": "npc:bran", "topics_any": ["red lantern records"]},
                    {"semantic": "tell", "target_id": "npc:garran", "topics_any": ["paymaster", "records"]},
                    {"semantic": "travel", "topics_any": ["return", "red lantern"]},
                    {"semantic": "report", "topics_any": ["sable chain paymaster"]},
                ],
                suggested_actions=[
                    _a(
                        "return_with_red_lantern_records",
                        "I return to Bran and Garran with the Red Lantern records proving the Sable Chain paymaster's role.",
                        "report",
                        target_type="npc",
                        target_id="npc:bran",
                        priority=89,
                    ),
                ],
                effects=[
                    {"set_location": "location:rusty_flagon_tavern", "name": "The Rusty Flagon Tavern"},
                    {"unlock_fact": "fact:allies_have_red_lantern_records", "text": "Bran and Garran now have the Red Lantern records proving the Sable Chain paymaster's role."},
                    {"complete_quest": "quest:sable_chain_endgame_opener"},
                    {"unlock_lead": "lead:red_lantern_paymaster_next_arc", "text": "Plan the move against the Red Lantern paymaster."},
                ],
            ),
        ],
    )
    graph.title = "Sable Chain Endgame → Red Lantern Paymaster"
    graph.starts_after_graph_ids = ["graph:tavern_story_seed:handler_veska_leadership_pursuit"]
    graph.starts_after_quest_ids = ["quest:handler_veska_leadership_pursuit"]
    graph.priority = 20
    return graph


_GRAPHS: Dict[str, List[ScenarioProgressionGraph]] = {
    "tavern_story_seed": [_rusty_flagon_graph(), _build_tavern_aftermath_graph(), _build_north_road_shrine_graph(), _build_captain_voss_consequence_graph(), _build_voss_backers_investigation_graph(), _build_sable_chain_countermove_graph(), _build_sable_chain_handler_route_pressure_graph(), _build_handler_veska_leadership_pursuit_graph(), _build_sable_chain_endgame_opener_graph()],
    "caravan_ambush_seed": [_caravan_ambush_graph()],
}


def get_progression_graph_for_seed(scenario_seed: str) -> ScenarioProgressionGraph | None:
    graphs = _GRAPHS.get(scenario_seed, [])
    return graphs[0] if graphs else None


def get_progression_graphs_for_seed(scenario_seed: str) -> List[ScenarioProgressionGraph]:
    return _GRAPHS.get(scenario_seed, [])


def get_progression_graph_by_id(scenario_seed: str, graph_id: str) -> ScenarioProgressionGraph | None:
    for graph in get_progression_graphs_for_seed(scenario_seed):
        if graph.graph_id == graph_id:
            return graph
    return None


def validate_progression_graph_registry() -> Dict[str, Any]:
    errors: List[str] = []
    for seed, graphs in _GRAPHS.items():
        seen_graph_ids = set()
        for graph in graphs:
            if not graph.graph_id:
                errors.append(f"{seed}:graph_missing_id")
            if graph.graph_id in seen_graph_ids:
                errors.append(f"{seed}:duplicate_graph_id:{graph.graph_id}")
            seen_graph_ids.add(graph.graph_id)
            node_ids = [node.node_id for node in graph.nodes]
            if len(node_ids) != len(set(node_ids)):
                errors.append(f"{seed}:{graph.graph_id}:duplicate_node_ids")
            if not node_ids:
                errors.append(f"{seed}:{graph.graph_id}:no_nodes")
    return {
        "ok": not errors,
        "errors": errors,
        "graph_count": sum(len(graphs) for graphs in _GRAPHS.values()),
        "seeds": sorted(_GRAPHS.keys()),
    }