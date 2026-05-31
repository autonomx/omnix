from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
