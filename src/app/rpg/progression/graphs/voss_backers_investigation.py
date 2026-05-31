from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
