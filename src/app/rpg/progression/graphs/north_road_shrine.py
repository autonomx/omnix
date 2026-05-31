from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
