from __future__ import annotations

from typing import Dict

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
) -> ProgressionAction:
    return ProgressionAction(
        action_id=action_id,
        command=command,
        semantic=semantic,
        target_type=target_type,
        target_id=target_id,
        priority=priority,
    )


def _rusty_flagon_graph() -> ScenarioProgressionGraph:
    return ScenarioProgressionGraph(
        graph_id="progression:rusty_flagon_witness_bandit_road:v1",
        scenario_seed="tavern_story_seed",
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
                    {"unlock_objective": "objective:warn_garran"},
                    {"unlock_npc": "npc:garran", "name": "Garran"},
                    {
                        "unlock_location": "location:garran_wagon_yard",
                        "name": "Garran's Wagon Yard",
                    },
                    {
                        "unlock_lead": "lead:ask_bran_garran",
                        "text": "Ask Bran who travels the road before dawn.",
                    },
                ],
                priority=110,
            ),
            ProgressionNode(
                node_id="ask_bran_garran",
                title="Ask Bran who will travel the road before dawn.",
                requires=[{"quest": "quest:warn_wagon", "status": "active"}],
                action_patterns=[
                    {
                        "semantic": "ask",
                        "target_id": "npc:bran",
                        "topics_any": ["wagon", "road", "dawn", "traveler", "who"],
                    },
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
                ],
                priority=105,
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
                    {"unlock_location": "location:quarry_road", "name": "Quarry Road"},
                    {
                        "unlock_fact": "fact:quarry_road_option",
                        "text": "The quarry road can bypass the bridge.",
                    },
                    {
                        "unlock_lead": "lead:prepare_quarry_road",
                        "text": "Prepare the wagon for the quarry road.",
                    },
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
                    {"complete_objective": "objective:warn_garran"},
                    {"complete_quest": "quest:warn_wagon"},
                    {
                        "start_quest": "quest:quarry_road_ambush",
                        "title": "Quarry Road Ambush",
                    },
                    {"set_location": "location:quarry_road", "name": "Quarry Road"},
                ],
                priority=100,
            ),
        ],
    )


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


_GRAPHS: Dict[str, ScenarioProgressionGraph] = {
    "tavern_story_seed": _rusty_flagon_graph(),
    "caravan_ambush_seed": _caravan_ambush_graph(),
}


def get_progression_graph_for_seed(scenario_seed: str) -> ScenarioProgressionGraph | None:
    return _GRAPHS.get(scenario_seed)