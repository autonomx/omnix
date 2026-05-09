from app.rpg.advisory.candidates import normalize_advisory_candidates
from tests.rpg.autoplay.advisory_promotion_runtime import (
    run_deferred_advisory_promotions_for_transcript,
)


def test_promotion_runtime_promotes_previous_turn_candidate_without_state_mutation():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I reassure Bran.",
        turn_contract={"player_input": "I reassure Bran."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "bran",
                    "delta": 1,
                    "summary": "Bran is slightly reassured.",
                }
            ]
        },
    )
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
        {
            "turn_index": 2,
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
    ]

    result = run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    assert result["ok"] is True
    assert result["accepted"] >= 1
    assert result["mutated_authoritative_state"] is False
    assert transcript[1]["deferred_advisory_promotion_result"]["promoted_this_turn"] >= 1


def test_promotion_runtime_keeps_same_turn_candidate_pending():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=3,
        player_input="I inspect.",
        turn_contract={"player_input": "I inspect."},
        payload={"future_hook_candidates": [{"summary": "A guard may react."}]},
    )
    transcript = [
        {
            "turn_index": 3,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "simulation_state": {},
        }
    ]

    result = run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    assert result["ok"] is True
    assert result["accepted"] == 0
    assert result["rejected"] == 0
    assert result["pending"] >= 1
    decision = transcript[0]["deferred_advisory_promotion_result"]["decisions"][0]
    assert decision["status"] == "pending"
    assert decision["reason"] == "not_eligible_until_future_turn"


def test_promotion_runtime_does_not_mutate_inventory_or_currency():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I ask for payment.",
        turn_contract={"player_input": "I ask for payment."},
        payload={"future_hook_candidates": [{"summary": "Payment can be discussed later."}]},
    )
    simulation_state = {
        "inventory": {"items": []},
        "currency": {"gold": 0},
    }
    transcript = [
        {
            "turn_index": 2,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "simulation_state": simulation_state,
        }
    ]

    result = run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    assert result["mutated_authoritative_state"] is False
    assert transcript[0]["simulation_state"]["inventory"]["items"] == []
    assert transcript[0]["simulation_state"]["currency"]["gold"] == 0


def test_promotion_runtime_carries_pending_candidates_forward_to_next_turn():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I reassure Bran.",
        turn_contract={"player_input": "I reassure Bran."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "bran",
                    "delta": 1,
                    "summary": "Bran is reassured.",
                }
            ]
        },
    )
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
        {
            "turn_index": 2,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": [],
                    "accepted": [],
                    "rejected": [],
                }
            },
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
    ]

    result = run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    assert result["mutated_authoritative_state"] is False
    assert result["accepted"] >= 1
    assert transcript[0]["deferred_advisory_promotion_result"]["decisions"][0]["status"] == "pending"
    assert transcript[1]["deferred_advisory_promotion_result"]["promoted_this_turn"] >= 1
    assert transcript[1]["npc_evolution_consumption_result"]["signals_created"] >= 1
    assert transcript[1]["npc_evolution_consumption_result"]["signals_consumed"] >= 1
    assert transcript[1]["npc_evolution_summary"]["arc_count"] >= 1
    # Running the consumer again on the same carried runtime state should not
    # create another signal for the same accepted projection.
    assert transcript[1]["npc_evolution_summary"]["consumed_projection_count"] >= 1


def test_promotion_runtime_extracts_nested_turn_result_simulation_state_for_evolution():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I ask Bran about rumors.",
        turn_contract={"player_input": "I ask Bran about rumors."},
        payload={
            "future_hook_candidates": [
                {
                    "summary": "Bran may offer a rumor later.",
                }
            ]
        },
    )
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "turn_result": {
                "simulation_state": {
                    "scene": {"nearby_npcs": ["bran"]},
                    "npc_progression_state": {"npcs": {"bran": {"name": "Bran"}}},
                }
            },
        },
        {
            "turn_index": 2,
            "turn_result": {
                "simulation_state": {
                    "scene": {"nearby_npcs": ["bran"]},
                    "npc_progression_state": {"npcs": {"bran": {"name": "Bran"}}},
                }
            },
        },
    ]

    result = run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    assert result["evolution_signals_created"] >= 1
    assert result["evolution_signals_consumed"] >= 1
    assert transcript[1]["npc_evolution_summary"]["arcs_by_npc"] == ["bran"]


def test_promotion_runtime_relationship_delta_advances_npc_arc_axis_after_grounding():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I thank the innkeeper.",
        turn_contract={"player_input": "I thank the innkeeper."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "innkeeper",
                    "axis": "trust",
                    "delta": 1,
                    "summary": "The innkeeper trusts the player slightly more.",
                }
            ]
        },
    )
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "turn_result": {
                "simulation_state": {
                    "scene": {"nearby_npcs": ["Bran"]},
                    "npc_progression_state": {
                        "npcs": {"Bran": {"name": "Bran", "role": "innkeeper"}}
                    },
                }
            },
        },
        {
            "turn_index": 2,
            "turn_result": {
                "simulation_state": {
                    "scene": {"nearby_npcs": ["Bran"]},
                    "npc_progression_state": {
                        "npcs": {"Bran": {"name": "Bran", "role": "innkeeper"}}
                    },
                }
            },
        },
    ]

    result = run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    assert result["accepted"] >= 1
    arc = transcript[1]["runtime_state"]["npc_evolution"]["arcs"]["Bran"]
    assert arc["axes"]["trust"] >= 1


def test_profile_loading_does_not_break_deferred_advisory_carry_forward(tmp_path, monkeypatch):
    monkeypatch.setenv("RPG_NPC_PROFILE_ROOT", str(tmp_path))
    (tmp_path / "bran.json").write_text(
        '{"format_version":"npc_evolution_profile_v1","npc_id":"Bran","evolution":{"arc_stage":"stable","axes":{}}}',
        encoding="utf-8",
    )
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I thank the innkeeper.",
        turn_contract={"player_input": "I thank the innkeeper."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "innkeeper",
                    "axis": "trust",
                    "delta": 1,
                    "summary": "The innkeeper trusts the player slightly more.",
                }
            ]
        },
    )
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "turn_result": {
                "simulation_state": {
                    "scene": {"nearby_npcs": ["Bran"]},
                    "npc_progression_state": {
                        "npcs": {"Bran": {"name": "Bran", "role": "innkeeper"}}
                    },
                }
            },
        },
        {
            "turn_index": 2,
            "turn_result": {
                "simulation_state": {
                    "scene": {"nearby_npcs": ["Bran"]},
                    "npc_progression_state": {
                        "npcs": {"Bran": {"name": "Bran", "role": "innkeeper"}}
                    },
                }
            },
        },
    ]

    result = run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    assert result["accepted"] >= 1
    assert result["evolution_signals_created"] >= 1
    assert transcript[1]["npc_profile_load_result"]["loaded_count"] == 1
    assert transcript[1]["runtime_state"]["npc_evolution"]["arcs"]["Bran"]["axes"]["trust"] >= 1


def test_advisory_promotion_runtime_preserves_campaign_journal_namespaces():
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "campaign_calendar": {
                    "current": {"turn_index": 1, "time_label": "00:00"},
                    "history": [{"turn_index": 1, "time_label": "00:00"}],
                },
                "player_journal": {
                    "entries": [],
                    "pending_actions": ["I ask Bran."],
                    "pending_results": [],
                },
                "deferred_advisory": {
                    "candidates": [],
                    "accepted": [],
                    "rejected": [],
                },
            },
            "simulation_state": {
                "scene": {"nearby_npcs": ["Bran"]},
                "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
            },
        }
    ]

    run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    runtime_state = transcript[0]["runtime_state"]
    assert "campaign_calendar" in runtime_state
    assert "player_journal" in runtime_state
    assert runtime_state["campaign_calendar"]["current"]["time_label"] == "00:00"


def test_advisory_promotion_runtime_merges_campaign_calendar_history():
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "campaign_calendar": {
                    "current": {"turn_index": 1, "time_label": "00:00"},
                    "history": [{"turn_index": 1, "time_label": "00:00"}],
                },
                "player_journal": {"entries": [], "pending_actions": ["a1"], "pending_results": []},
                "deferred_advisory": {"candidates": [], "accepted": [], "rejected": []},
            },
            "simulation_state": {
                "scene": {"nearby_npcs": ["Bran"]},
                "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
            },
        },
        {
            "turn_index": 2,
            "runtime_state": {
                "campaign_calendar": {
                    "current": {"turn_index": 2, "time_label": "01:00"},
                    "history": [{"turn_index": 2, "time_label": "01:00"}],
                },
                "player_journal": {"entries": [], "pending_actions": ["a2"], "pending_results": []},
                "deferred_advisory": {"candidates": [], "accepted": [], "rejected": []},
            },
            "simulation_state": {
                "scene": {"nearby_npcs": ["Bran"]},
                "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
            },
        },
    ]

    run_deferred_advisory_promotions_for_transcript(transcript=transcript)

    history = transcript[1]["runtime_state"]["campaign_calendar"]["history"]
    assert [item["turn_index"] for item in history] == [1, 2]


def test_promotion_runtime_can_process_only_recent_rows_with_seeded_carry_state():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I reassure Bran.",
        turn_contract={"player_input": "I reassure Bran."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "bran",
                    "delta": 1,
                    "summary": "Bran is reassured.",
                }
            ]
        },
    )
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                }
            },
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
        {
            "turn_index": 2,
            "runtime_state": {},
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
        {
            "turn_index": 3,
            "runtime_state": {},
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
    ]

    full = run_deferred_advisory_promotions_for_transcript(transcript=transcript)
    assert full["accepted"] >= 1
    assert transcript[1]["runtime_state"]["deferred_advisory"]["accepted"]

    # Simulate a later pre-turn incremental pass: it should seed carry from
    # row 2 and only process row 3.
    bounded = run_deferred_advisory_promotions_for_transcript(
        transcript=transcript,
        max_rows=1,
        persist_profiles=False,
    )

    assert bounded["ok"] is True
    assert bounded["turns"] == 1
    assert bounded["source_transcript_turns"] == 3
    assert bounded["max_rows"] == 1
    assert bounded["persist_profiles"] is False
    assert transcript[2]["npc_evolution_profile_persist_result"]["skipped"] is True


def test_promotion_runtime_can_skip_profile_persistence_for_pre_turn_pass():
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": [],
                    "accepted": [],
                    "rejected": [],
                }
            },
            "simulation_state": {},
        }
    ]

    result = run_deferred_advisory_promotions_for_transcript(
        transcript=transcript,
        persist_profiles=False,
    )

    assert result["ok"] is True
    assert result["persist_profiles"] is False
    assert transcript[0]["npc_evolution_profile_persist_result"]["ok"] is True
    assert transcript[0]["npc_evolution_profile_persist_result"]["skipped"] is True
    assert (
        transcript[0]["npc_evolution_profile_persist_result"]["reason"]
        == "pre_turn_promotion_no_disk_persist"
    )


def test_incremental_pre_turn_promotion_marks_rows_and_skips_reprocessing():
    candidates = normalize_advisory_candidates(
        session_id="s",
        turn_index=1,
        player_input="I reassure Bran.",
        turn_contract={"player_input": "I reassure Bran."},
        payload={
            "relationship_delta_candidates": [
                {
                    "target": "bran",
                    "delta": 1,
                    "summary": "Bran is reassured.",
                }
            ]
        },
    )
    transcript = [
        {
            "turn_index": 1,
            "combined_background_llm_result": {"ok": True},
            "combined_background_llm_attach": {"phase": "pre_turn"},
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": candidates,
                    "accepted": [],
                    "rejected": [],
                    "pending": [],
                }
            },
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
    ]

    first = run_deferred_advisory_promotions_for_transcript(
        transcript=transcript,
        max_rows=6,
        persist_profiles=False,
        incremental_pre_turn=True,
        mark_pre_turn_promoted=True,
        current_turn=2,
    )

    assert first["ok"] is True
    assert first["turns"] == 1
    assert first["incremental_pre_turn"] is True
    assert transcript[0]["pre_turn_advisory_promoted"] is True
    assert transcript[0]["pre_turn_advisory_promoted_at_turn"] == 2

    second = run_deferred_advisory_promotions_for_transcript(
        transcript=transcript,
        max_rows=6,
        persist_profiles=False,
        incremental_pre_turn=True,
        mark_pre_turn_promoted=True,
        current_turn=3,
    )

    assert second["ok"] is True
    assert second["turns"] == 0


def test_incremental_pre_turn_promotion_compacts_carry_state_backlog():
    big_candidates = [
        {
            "id": f"candidate:{idx}",
            "kind": "relationship_delta",
            "target": "bran",
            "delta": 1,
            "summary": f"candidate {idx}",
        }
        for idx in range(200)
    ]
    transcript = [
        {
            "turn_index": 1,
            "runtime_state": {
                "deferred_advisory": {
                    "candidates": big_candidates,
                    "pending": big_candidates,
                    "accepted": big_candidates,
                    "rejected": big_candidates,
                }
            },
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
        {
            "turn_index": 2,
            "combined_background_llm_result": {"ok": True},
            "combined_background_llm_attach": {"phase": "pre_turn"},
            "runtime_state": {"deferred_advisory": {"candidates": []}},
            "simulation_state": {"npcs": {"bran": {"name": "Bran"}}},
        },
    ]

    result = run_deferred_advisory_promotions_for_transcript(
        transcript=transcript,
        max_rows=6,
        persist_profiles=False,
        incremental_pre_turn=True,
        mark_pre_turn_promoted=True,
        current_turn=3,
        carry_candidate_limit=7,
        carry_pending_limit=8,
        carry_accepted_limit=9,
        carry_rejected_limit=10,
    )

    assert result["ok"] is True
    assert result["turns"] == 1
    advisory = transcript[1]["runtime_state"]["deferred_advisory"]
    assert len(advisory["candidates"]) <= 7
    assert len(advisory["pending"]) <= 8
    assert len(advisory["accepted"]) <= 9
    assert len(advisory["rejected"]) <= 10