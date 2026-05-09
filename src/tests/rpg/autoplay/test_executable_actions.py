from tests.rpg.autoplay.executable_actions import (
    action_signature,
    choose_rotated_affordance,
    executable_action_for_context,
    is_meta_or_vague_action,
    normalize_command_label_action,
    repair_action_if_needed,
)
from tests.rpg.autoplay_llm_campaign import _repeated_affordance_loop_summary


def test_meta_action_is_detected():
    assert is_meta_or_vague_action("I choose a concrete lead for Witness Search: ask a named NPC.")
    assert is_meta_or_vague_action("I ask Bran if they know anything that can help with my current objective.")


def test_meta_action_repairs_to_executable_witness_action():
    context = {
        "active_objectives": [{"objective_text": "Find the witness."}],
        "nearby_npcs": [{"name": "Bran"}],
    }

    result = repair_action_if_needed(
        "I choose a concrete lead for Witness Search: ask a named NPC.",
        context,
    )

    assert result["changed"] is True
    assert "where the cloaked traveler went" in result["action"]
    assert "choose a concrete lead" not in result["action"].lower()
    assert "named NPC" not in result["action"]


def test_executable_action_for_bandit_context_is_concrete():
    context = {
        "active_objectives": [{"objective_text": "Follow the bandit road trail."}],
        "nearby_npcs": [{"name": "Bran"}],
    }
    action = executable_action_for_context(context, "travel toward the next known location")
    assert "bandit road trail" in action or "follow" in action.lower()
    assert "next known location" not in action.lower()


def test_command_label_action_normalizes_to_first_person_executable_command():
    action = normalize_command_label_action("Ask Bran what they personally saw about the cloaked traveler")
    assert action.startswith("I ask Bran")
    assert "personally saw" in action
    assert "side door" in action or "where they went" in action


def test_harness_style_story_arc_action_repairs_to_executable_command():
    context = {
        "active_objectives": [{"objective_text": "Find the witness."}],
        "nearby_npcs": [{"name": "Bran"}],
    }
    result = repair_action_if_needed("Investigate story arc: Witness Search", context)
    assert result["changed"] is True
    assert result["action"].startswith("I ")
    assert "current objective" not in result["action"].lower()
    assert "investigate story arc" not in result["action"].lower()


def test_repeated_completed_report_repairs_to_next_lead():
    context = {
        "autoplay_story_hook_state": {
            "fired_hooks": {
                "hook:witness:report_to_bran": {"turn_index": 4}
            }
        },
        "active_objectives": [{"objective_text": "Report witness findings to Bran."}],
        "nearby_npcs": [{"name": "Bran"}],
    }
    result = repair_action_if_needed(
        "I report to Bran that the cloaked traveler trail points toward the road and ask what danger this confirms.",
        context,
    )
    assert result["changed"] is True
    assert "leave the rusty flagon" in result["action"].lower()
    assert "follow the road" in result["action"].lower()


def test_completed_witness_search_repairs_to_bandit_road_transition():
    context = {
        "quest_progress": {
            "quests": {
                "quest:witness_search": {"status": "completed", "completed": True},
                "quest:bandit_road": {"status": "active"},
            }
        },
        "current_location": "location:rusty_flagon",
        "nearby_npcs": [{"name": "Bran"}],
    }
    result = repair_action_if_needed(
        "I ask Bran where the cloaked traveler went after leaving by the side door.",
        context,
    )
    assert result["changed"] is True
    assert "leave the Rusty Flagon" in result["action"] or "follow the road" in result["action"]
    assert "cloaked traveler went" not in result["action"]


def test_repeated_affordance_action_repairs_to_alternate_affordance():
    context = {
        "quest_log_state": {
            "quests": {
                "quest:scout": {
                    "title": "Missing Scout",
                    "quest_giver": "Captain Arlen",
                    "objectives": [
                        {
                            "objective_id": "objective:find_scout",
                            "summary": "Find the missing scout.",
                            "objective_type": "find",
                            "subject": "missing scout",
                            "known_leads": ["forest trail"],
                        }
                    ],
                }
            }
        },
        "recent_turns": [
            {"player_action": "I ask Captain Arlen what they personally know about missing scout, where it was last seen, and who or what I should inspect next."},
            {"player_action": "I ask Captain Arlen what they personally know about missing scout, where it was last seen, and who or what I should inspect next."},
        ],
    }

    result = repair_action_if_needed("I ask Captain Arlen what they personally know about missing scout, where it was last seen, and who or what I should inspect next.", context)

    assert result["changed"] is True
    assert result["action"] != "I ask Captain Arlen what they personally know about missing scout, where it was last seen, and who or what I should inspect next."
    assert result["reason"] == "repeated_affordance_action_repaired_to_alternate_objective_affordance"


def test_repeated_affordance_loop_summary_flags_signature_streak():
    transcript = [
        {"player_action": "I ask Captain Arlen who last saw the missing scout."},
        {"player_action": "I ask Captain Arlen who last saw the missing scout."},
        {"player_action": "I ask Captain Arlen who last saw the missing scout."},
        {"player_action": "I ask Captain Arlen who last saw the missing scout."},
    ]

    summary = _repeated_affordance_loop_summary(transcript, threshold=4)

    assert summary["ok"] is False
    assert summary["max_streak"] == 4


def test_repeated_inspect_affordance_rotates_to_different_semantic():
    repeated = (
        "I inspect the forest trail for signs of missing scout: tracks, marks, "
        "damage, residue, missing items, witnesses, or hidden clues."
    )
    context = {
        "quest_log_state": {
            "quests": {
                "quest:scout": {
                    "title": "Missing Scout",
                    "quest_giver": "Captain Arlen",
                    "objectives": [
                        {
                            "objective_id": "objective:find_scout",
                            "summary": "Find the missing scout.",
                            "objective_type": "find",
                            "subject": "missing scout",
                            "known_leads": ["forest trail"],
                        }
                    ],
                }
            }
        },
    }
    transcript = [
        {"player_action": repeated},
        {"player_action": repeated},
        {"player_action": repeated},
    ]

    rotated = choose_rotated_affordance(context, repeated)

    assert rotated
    assert action_signature(rotated) != action_signature(repeated)

    repaired = repair_action_if_needed(repeated, context, transcript)
    assert repaired["changed"] is True
    assert repaired["reason"] == "repeated_affordance_action_repaired_by_semantic_rotation"
    assert action_signature(repaired["action"]) != action_signature(repeated)


def test_review_quest_log_meta_action_repairs_to_concrete_world_action():
    result = repair_action_if_needed(
        "I review my quest log and decide what objective to pursue next.",
        {"recent_turns": []},
    )

    assert result["changed"] is True
    assert "review my quest log" not in result["action"].lower()
    assert result["action"].startswith("I ")


def test_executable_action_prefers_authority_commit_handoff_quest():
    context = {
        "campaign_state_commit_summary": {
            "quest_progress_summary": {
                "quests": [
                    {
                        "title": "Investigate Lead: wagon ruts near old bridge",
                        "status": "active",
                        "completed": False,
                        "source": "campaign_state_authority_commit",
                        "objectives": [
                            {
                                "summary": "Investigate the unresolved lead: wagon ruts near old bridge.",
                                "completed": False,
                            }
                        ],
                    }
                ]
            }
        },
        "active_objectives": [{"objective_text": "Old stale objective"}],
    }

    action = executable_action_for_context(context, "travel toward the next known location")

    assert "investigate" in action.lower()
    assert "wagon ruts near old bridge" in action.lower()


def test_repeated_old_search_repairs_to_committed_handoff_action():
    context = {
        "campaign_state_commit_summary": {
            "quest_progress_summary": {
                "quests": [
                    {
                        "quest_id": "quest:done",
                        "title": "Old Quest",
                        "status": "completed",
                        "completed": True,
                    },
                    {
                        "quest_id": "quest:investigate_lead:test",
                        "title": "Investigate Lead: old mill bridge",
                        "status": "active",
                        "completed": False,
                        "source": "campaign_state_authority_commit",
                        "handoff_quest": True,
                        "lead": {"name": "old mill bridge"},
                        "objectives": [
                            {
                                "objective_id": "objective:lead",
                                "summary": "Investigate the unresolved lead: old mill bridge.",
                                "status": "active",
                                "completed": False,
                                "subject": "old mill bridge",
                                "handoff_objective": True,
                            }
                        ],
                    },
                ]
            }
        },
        "recent_turns": [
            {
                "player_action": "I inspect the road outside the tavern for fresh tracks, wagon ruts, black cord, torn cloth, ambush signs, or bridge markings."
            }
        ] * 4,
    }

    result = repair_action_if_needed(
        "I inspect the road outside the tavern for fresh tracks, wagon ruts, black cord, torn cloth, ambush signs, or bridge markings.",
        context,
    )

    assert result["changed"] is True
    assert result["reason"] == "committed_handoff_quest_priority_repair"
    assert "old mill bridge" in result["action"].lower()


def test_scenario_specific_witness_repair_disabled_when_handoff_active():
    context = {
        "campaign_state_commit_summary": {
            "quest_progress_summary": {
                "quests": [
                    {
                        "quest_id": "quest:investigate_lead:test",
                        "title": "Investigate Lead: Bandit Road",
                        "status": "active",
                        "completed": False,
                        "source": "campaign_state_authority_commit",
                        "handoff_quest": True,
                        "lead": {"name": "Bandit Road"},
                        "objectives": [
                            {
                                "objective_id": "objective:lead",
                                "summary": "Investigate the unresolved lead: Bandit Road.",
                                "status": "active",
                                "completed": False,
                                "subject": "Bandit Road",
                                "handoff_objective": True,
                            }
                        ],
                    }
                ]
            }
        },
        "quest_progress": {
            "quests": {
                "quest:witness_search": {"status": "completed", "completed": True},
            }
        },
        "recent_turns": [
            {
                "player_action": "I inspect the road outside the tavern for fresh tracks, wagon ruts, black cord, torn cloth, ambush signs, or bridge markings."
            }
        ] * 4,
    }

    result = repair_action_if_needed(
        "I ask Bran where the cloaked traveler went after leaving by the side door.",
        context,
    )

    assert result["reason"] == "committed_handoff_quest_priority_repair"
    assert "bandit road" in result["action"].lower()


def test_handoff_action_rotation_avoids_recent_semantic_repeat():
    from tests.rpg.autoplay.executable_actions import repair_action_if_needed

    context = {
        "campaign_state_commit_summary": {
            "quest_progress_summary": {
                "quests": [
                    {
                        "quest_id": "quest:investigate_lead:test",
                        "title": "Investigate Lead: ruined observatory",
                        "status": "active",
                        "completed": False,
                        "source": "campaign_state_authority_commit",
                        "handoff_quest": True,
                        "lead": {"name": "ruined observatory"},
                        "objectives": [
                            {
                                "objective_id": "objective:lead",
                                "summary": "Investigate the unresolved lead: ruined observatory.",
                                "status": "active",
                                "completed": False,
                                "subject": "ruined observatory",
                                "handoff_objective": True,
                                "semantic_action_templates": [
                                    {
                                        "semantic": "ask_about_lead",
                                        "command": "I ask nearby people what they know about ruined observatory.",
                                    },
                                    {
                                        "semantic": "inspect_lead",
                                        "command": "I inspect evidence connected to ruined observatory, looking for concrete next steps.",
                                    },
                                ],
                                "handoff_semantic_history": [
                                    {"semantic": "ask_about_lead", "turn": 2}
                                ],
                            }
                        ],
                    }
                ]
            }
        },
        "recent_turns": [
            {
                "player_action": "I ask nearby people what they know about ruined observatory.",
                "handoff_semantic": "ask_about_lead",
            }
        ],
    }

    result = repair_action_if_needed(
        "I ask nearby people what they know about ruined observatory.",
        context,
    )

    assert result["changed"] is True
    assert result["reason"] == "committed_handoff_quest_priority_repair"
    assert result["handoff_semantic"] == "inspect_lead"
    assert "inspect" in result["action"].lower()


def test_repair_replaces_stale_active_wagon_objective_after_arc_complete():
    from tests.rpg.autoplay.executable_actions import repair_action_if_needed

    result = repair_action_if_needed(
        "I check in with Garran and focus on the active wagon-road objective.",
        {
            "scenario_arc_complete": True,
            "scenario_progression_arc_summary": {"arc_complete": True},
            "scenario_progression_actions": [
                {
                    "action_id": "arc_complete_ask_next_lead",
                    "command": "I ask Garran what threat or lead we should follow next now that the wagon is safe.",
                    "source": "scenario_progression_arc_complete_bridge",
                }
            ],
        },
    )

    assert result["changed"] is True
    assert result["reason"] == "scenario_progression_arc_complete_repaired_stale_objective_text"
    assert "next" in result["action"].lower()