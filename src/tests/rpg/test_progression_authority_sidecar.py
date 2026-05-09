from tests.rpg.autoplay_llm_campaign import (
    _extract_progression_authority_sidecar,
    _overlay_progression_authority_sidecar,
    _progression_node_count,
    _progression_revision,
    _update_progression_authority_sidecar,
)


def test_sidecar_restores_progression_fields_after_stale_runtime_overwrite():
    advanced_runtime = {
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
            "fact:cloaked_traveler": {},
            "fact:traveler_feared_patrol_or_bandits": {},
        },
        "scenario_progression_actions": [
            {"action_id": "ask_bran_direction", "command": "I ask Bran what direction the traveler went."}
        ],
    }
    sidecar = _extract_progression_authority_sidecar(advanced_runtime)

    stale_runtime = {
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
        },
        "scenario_progression_actions": [
            {"action_id": "ask_bran_who_left_side_door", "command": "I ask Bran who left."}
        ],
    }

    restored = _overlay_progression_authority_sidecar(
        stale_runtime,
        sidecar,
        reason="test_overlay",
        turn_index=3,
    )

    assert _progression_node_count(restored) == 2
    assert "ask_bran_who_left_side_door" in restored["progression_completed_nodes"]
    assert restored["scenario_progression_actions"][0]["action_id"] == "ask_bran_direction"
    assert restored["progression_stale_merge_log"]


def test_sidecar_update_refuses_stale_candidate():
    sidecar = _extract_progression_authority_sidecar(
        {
            "progression_completed_nodes": {
                "ask_bran_about_tension": {},
                "ask_bran_who_left_side_door": {},
            },
            "progression_facts": {
                "fact:witness_left_side_door": {},
                "fact:cloaked_traveler": {},
            },
        }
    )
    stale_runtime = {
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
        },
    }

    updated = _update_progression_authority_sidecar(
        sidecar,
        stale_runtime,
        reason="test_update",
        turn_index=3,
    )

    assert _progression_node_count(updated) == 2
    assert _progression_revision(updated) >= _progression_revision(sidecar)


def test_sidecar_update_accepts_newer_candidate():
    sidecar = _extract_progression_authority_sidecar(
        {
            "progression_completed_nodes": {
                "ask_bran_about_tension": {},
            },
            "progression_facts": {
                "fact:witness_left_side_door": {},
            },
        }
    )
    newer_runtime = {
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
            "fact:cloaked_traveler": {},
        },
    }

    updated = _update_progression_authority_sidecar(
        sidecar,
        newer_runtime,
        reason="test_update_newer",
        turn_index=2,
    )

    assert _progression_node_count(updated) == 2
    assert "ask_bran_who_left_side_door" in updated["progression_completed_nodes"]


def test_sidecar_preserves_graph_created_warn_wagon_quest():
    from tests.rpg.autoplay_llm_campaign import (
        _extract_progression_authority_sidecar,
        _overlay_progression_authority_sidecar,
    )

    advanced = {
        "quest_progress": {
            "quests": {
                "quest:witness_search": {
                    "quest_id": "quest:witness_search",
                    "status": "completed",
                    "completed": True,
                    "source": "scenario_progression_graph",
                },
                "quest:warn_wagon": {
                    "quest_id": "quest:warn_wagon",
                    "title": "Warn the Wagon",
                    "status": "active",
                    "completed": False,
                    "source": "scenario_progression_graph",
                    "objectives": [
                        {"objective_id": "objective:warn_garran", "status": "active", "completed": False}
                    ],
                },
            }
        },
        "progression_completed_nodes": {"report_findings_to_bran": {}},
    }
    sidecar = _extract_progression_authority_sidecar(advanced)

    stale_runtime = {
        "quest_progress": {
            "quests": {
                "quest:witness_search": {
                    "quest_id": "quest:witness_search",
                    "status": "completed",
                    "completed": True,
                }
            }
        },
        "progression_completed_nodes": {"report_findings_to_bran": {}},
    }

    restored = _overlay_progression_authority_sidecar(
        stale_runtime,
        sidecar,
        reason="test",
        turn_index=9,
    )

    quests = restored["quest_progress"]["quests"]
    assert "quest:warn_wagon" in quests
    assert quests["quest:warn_wagon"]["status"] == "active"
