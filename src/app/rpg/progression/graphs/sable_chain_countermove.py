from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
