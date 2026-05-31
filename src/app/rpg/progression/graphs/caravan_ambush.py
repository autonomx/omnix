from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
