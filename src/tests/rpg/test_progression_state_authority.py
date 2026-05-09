from tests.rpg.autoplay_llm_campaign import (
    _authoritative_progression_state,
    _progression_node_count,
    _progression_revision,
)


def test_authoritative_progression_state_refuses_lower_node_count_candidate():
    base = {
        "progression_state_revision": 20200,
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
            "fact:cloaked_traveler": {},
        },
    }
    stale = {
        "progression_state_revision": 10100,
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
        },
    }

    merged = _authoritative_progression_state(
        base,
        stale,
        reason="test_stale_merge",
        turn_index=3,
    )

    assert _progression_node_count(merged) == 2
    assert "ask_bran_who_left_side_door" in merged["progression_completed_nodes"]
    assert merged["progression_stale_merge_log"]


def test_authoritative_progression_state_accepts_higher_node_count_candidate():
    base = {
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
        },
    }
    newer = {
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
        },
        "progression_facts": {
            "fact:witness_left_side_door": {},
            "fact:cloaked_traveler": {},
        },
    }

    merged = _authoritative_progression_state(
        base,
        newer,
        reason="test_newer_merge",
        turn_index=2,
    )

    assert _progression_node_count(merged) == 2
    base_rev = _progression_revision(base)
    merged_rev = _progression_revision(merged)
    assert merged_rev >= base_rev