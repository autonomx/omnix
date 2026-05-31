from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
                    {"semantic": "secure", "topics_any": ["red lantern records", "red lantern payment records"]},
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
