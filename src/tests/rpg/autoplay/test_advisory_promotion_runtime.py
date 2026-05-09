from tests.rpg.autoplay.advisory_promotion_runtime import (
    run_deferred_advisory_promotions_for_transcript,
)


def test_pre_turn_fast_path_marks_promoted_and_skips_profile_evolution():
    row = {
        "turn_index": 1,
        "combined_background_llm_attach": {"phase": "pre_turn"},
        "combined_background_llm_result": {
            "deferred_advisory_candidates": [
                {
                    "candidate_id": "cand:test:1",
                    "kind": "memory",
                    "payload": {"owner": "npc:test", "text": "Test memory."},
                    "backing": {"turn_contract_action": "ask"},
                    "promotion": {"eligible_from_turn": 1},
                    "safety": {},
                }
            ]
        },
        "runtime_state": {"deferred_advisory": {"candidates": []}},
        "turn_contract": {"action": {"type": "social"}},
        "simulation_state": {
            "npcs": {"npc:test": {"id": "npc:test", "name": "Test NPC"}},
            "present_npcs": ["npc:test"],
        },
    }

    result = run_deferred_advisory_promotions_for_transcript(
        transcript=[row],
        incremental_pre_turn=True,
        mark_pre_turn_promoted=True,
        current_turn=2,
        persist_profiles=False,
        fast_pre_turn=True,
        skip_profile_load_for_pre_turn=True,
        skip_evolution_for_pre_turn=True,
        skip_mutation_compare_for_pre_turn=True,
    )

    assert result["ok"] is True
    assert result["fast_pre_turn"] is True
    assert row["pre_turn_advisory_promoted"] is True
    assert row["npc_evolution_consumption_result"]["skipped"] is True
    assert row["npc_evolution_profile_persist_result"]["skipped"] is True
    assert result["timing_breakdown"]["profile_load_ms"] >= 0
    assert result["timing_breakdown"]["evolution_consume_ms"] >= 0