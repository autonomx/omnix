from __future__ import annotations

from app.rpg.progression.graph_helpers import _a
from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph


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
