from tests.rpg.autoplay_llm_campaign import (
    _extract_progression_authority_sidecar,
    _overlay_and_assert_progression_sidecar,
    _progression_node_count,
    _progression_revision,
    _update_sidecar_and_overlay,
)


def test_overlay_and_assert_restores_runtime_from_sidecar():
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
            "scenario_progression_actions": [
                {
                    "action_id": "ask_bran_direction",
                    "command": "I ask Bran where the traveler went.",
                }
            ],
        }
    )
    stale_runtime = {
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
        },
        "scenario_progression_actions": [
            {
                "action_id": "ask_bran_who_left_side_door",
                "command": "I ask Bran who left.",
            }
        ],
    }

    restored = _overlay_and_assert_progression_sidecar(
        stale_runtime,
        sidecar,
        reason="test",
        turn_index=3,
    )

    assert _progression_node_count(restored) == 2
    assert restored["scenario_progression_actions"][0]["action_id"] == "ask_bran_direction"


def test_update_sidecar_and_overlay_accepts_newer_runtime():
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

    runtime, updated_sidecar = _update_sidecar_and_overlay(
        newer_runtime,
        sidecar,
        reason="test_update",
        turn_index=2,
    )

    assert _progression_node_count(updated_sidecar) == 2
    assert _progression_node_count(runtime) == 2
    assert _progression_revision(runtime) >= _progression_revision(sidecar)