from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
