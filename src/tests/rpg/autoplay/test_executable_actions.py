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