from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
