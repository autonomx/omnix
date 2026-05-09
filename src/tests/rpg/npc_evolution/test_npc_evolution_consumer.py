from app.rpg.npc_evolution.arcs import ingest_evolution_signals
from app.rpg.npc_evolution.consumer import (
    consume_accepted_advisory_projections,
    consume_evolution_signal,
)


def test_consume_relationship_signal_updates_npc_arc_not_authoritative_state():
    runtime_state = {}
    simulation_state = {"npcs": {"bran": {"name": "Bran"}}, "currency": {"gold": 0}}
    signal = {
        "signal_id": "s1",
        "npc_id": "bran",
        "turn_index": 2,
        "kind": "relationship_delta",
        "summary": "Bran trusts the player slightly more.",
        "payload": {"target": "bran", "axis": "trust", "delta": 1, "summary": "Trust rises."},
        "consumed": False,
    }
    ingest_evolution_signals(runtime_state=runtime_state, signals=[signal])

    before_currency = dict(simulation_state["currency"])
    runtime_state, decision = consume_evolution_signal(
        runtime_state=runtime_state,
        signal=signal,
        turn_index=2,
    )

    assert decision["ok"] is True
    assert runtime_state["npc_evolution"]["arcs"]["bran"]["axes"]["trust"] == 1
    assert simulation_state["currency"] == before_currency


def test_consume_memory_projection_adds_bounded_memory_to_arc():
    runtime_state = {
        "deferred_advisory": {
            "accepted": [
                {
                    "candidate_id": "c1",
                    "kind": "memory",
                    "projection": {
                        "candidate_id": "c1",
                        "kind": "memory",
                        "payload": {
                            "owner": "bran",
                            "summary": "Bran remembers the player asking about the mill.",
                            "importance": 0.8,
                        },
                    },
                }
            ]
        }
    }
    simulation_state = {"npcs": {"bran": {"name": "Bran"}}}

    updated, result = consume_accepted_advisory_projections(
        runtime_state=runtime_state,
        simulation_state=simulation_state,
        turn_index=2,
    )

    assert result["signals_created"] == 1
    assert result["signals_consumed"] == 1
    assert updated["npc_evolution"]["arcs"]["bran"]["memories"][0]["summary"].startswith("Bran remembers")


def test_consumer_rejects_projection_without_known_npc():
    runtime_state = {
        "deferred_advisory": {
            "accepted": [
                {
                    "candidate_id": "c1",
                    "kind": "future_hook",
                    "projection": {
                        "candidate_id": "c1",
                        "kind": "future_hook",
                        "payload": {
                            "target": "unknown_npc",
                            "summary": "Unknown NPC reacts.",
                        },
                    },
                }
            ]
        }
    }

    updated, result = consume_accepted_advisory_projections(
        runtime_state=runtime_state,
        simulation_state={"npcs": {}},
        turn_index=2,
    )

    assert result["signals_created"] == 0
    assert result["projection_decisions"][0]["status"] == "rejected"
    assert result["projection_decisions"][0]["reason"] == "npc_target_missing"


def test_consumer_uses_single_present_npc_for_future_hook_projection():
    runtime_state = {
        "deferred_advisory": {
            "accepted": [
                {
                    "candidate_id": "c1",
                    "kind": "future_hook",
                    "projection": {
                        "candidate_id": "c1",
                        "kind": "future_hook",
                        "payload": {
                            "summary": "The innkeeper may become more guarded.",
                        },
                    },
                }
            ]
        }
    }
    simulation_state = {
        "present_npcs": ["bran"],
        "npcs": {"bran": {"name": "Bran"}},
    }

    updated, result = consume_accepted_advisory_projections(
        runtime_state=runtime_state,
        simulation_state=simulation_state,
        turn_index=2,
    )

    assert result["signals_created"] == 1
    assert result["signals_consumed"] == 1
    assert updated["npc_evolution"]["arcs"]["bran"]["future_hooks"][0]["summary"].startswith("The innkeeper")


def test_consumer_does_not_reconsume_same_accepted_projection_on_later_turns():
    runtime_state = {
        "deferred_advisory": {
            "accepted": [
                {
                    "candidate_id": "adv:1:memory:abc",
                    "kind": "memory",
                    "projection": {
                        "candidate_id": "adv:1:memory:abc",
                        "kind": "memory",
                        "payload": {
                            "owner": "bran",
                            "summary": "Bran remembers the player asking about the mill.",
                            "importance": 0.8,
                        },
                    },
                }
            ]
        }
    }
    simulation_state = {"present_npcs": ["bran"], "npcs": {"bran": {"name": "Bran"}}}

    updated, first = consume_accepted_advisory_projections(
        runtime_state=runtime_state,
        simulation_state=simulation_state,
        turn_index=2,
    )
    updated, second = consume_accepted_advisory_projections(
        runtime_state=updated,
        simulation_state=simulation_state,
        turn_index=3,
    )

    assert first["signals_created"] == 1
    assert first["signals_consumed"] == 1
    assert second["signals_created"] == 0
    assert second["signals_consumed"] == 0
    assert second["already_consumed_projection_skips"] == 1
    assert len(updated["npc_evolution"]["arcs"]["bran"]["memories"]) == 1
    assert updated["npc_evolution"]["summary"]["consumed_projection_count"] == 1


def test_consumer_grounds_innkeeper_alias_to_bran():
    runtime_state = {
        "deferred_advisory": {
            "accepted": [
                {
                    "candidate_id": "c1",
                    "kind": "future_hook",
                    "projection": {
                        "candidate_id": "c1",
                        "kind": "future_hook",
                        "payload": {
                            "target": "innkeeper",
                            "summary": "The innkeeper may become more guarded.",
                        },
                    },
                }
            ]
        }
    }
    simulation_state = {
        "scene": {"nearby_npcs": ["Bran"]},
        "npc_progression_state": {"npcs": {"Bran": {"name": "Bran", "role": "innkeeper"}}},
    }

    updated, result = consume_accepted_advisory_projections(
        runtime_state=runtime_state,
        simulation_state=simulation_state,
        turn_index=2,
    )

    assert result["signals_created"] == 1
    assert result["projection_decisions"][0]["target_grounding"]["reason"] == "explicit_role_alias"
    assert "Bran" in updated["npc_evolution"]["arcs"]


def test_consumer_uses_canonical_arc_for_prefixed_npc_id():
    runtime_state = {
        "deferred_advisory": {
            "accepted": [
                {
                    "candidate_id": "adv:1:future_hook:prefixed",
                    "kind": "future_hook",
                    "projection": {
                        "candidate_id": "adv:1:future_hook:prefixed",
                        "kind": "future_hook",
                        "payload": {
                            "target": "npc:bran",
                            "summary": "Bran may answer later.",
                        },
                    },
                }
            ]
        }
    }
    simulation_state = {
        "scene": {"nearby_npcs": ["npc:bran"]},
        "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
    }

    updated, result = consume_accepted_advisory_projections(
        runtime_state=runtime_state,
        simulation_state=simulation_state,
        turn_index=2,
    )

    assert result["signals_created"] == 1
    assert "Bran" in updated["npc_evolution"]["arcs"]
    assert "npc:bran" not in updated["npc_evolution"]["arcs"]
    assert updated["npc_evolution"]["summary"]["arcs_by_npc"] == ["Bran"]


def test_relationship_signals_advance_arc_stage_and_create_milestone():
    runtime_state = {}
    simulation_state = {
        "scene": {"nearby_npcs": ["Bran"]},
        "npc_progression_state": {"npcs": {"Bran": {"name": "Bran"}}},
    }
    runtime_state["deferred_advisory"] = {
        "accepted": [
            {
                "candidate_id": f"adv:{index}:relationship_delta:trust",
                "kind": "relationship_delta",
                "projection": {
                    "candidate_id": f"adv:{index}:relationship_delta:trust",
                    "kind": "relationship_delta",
                    "payload": {
                        "target": "Bran",
                        "axis": "trust",
                        "delta": 2,
                        "summary": "Bran trusts the player more.",
                    },
                },
            }
            for index in range(1, 4)
        ]
    }

    updated, result = consume_accepted_advisory_projections(
        runtime_state=runtime_state,
        simulation_state=simulation_state,
        turn_index=5,
    )

    arc = updated["npc_evolution"]["arcs"]["Bran"]
    assert arc["axes"]["trust"] >= 4
    assert arc["arc_stage"] == "trusting"
    assert len(arc["milestones"]) >= 1
    assert arc["milestones"][0]["from"] == "stable"
    assert arc["milestones"][0]["to"] == "trusting"
    assert arc["milestones"][0]["milestone_id"]
    assert result["summary"]["milestone_total"] >= 1


def test_milestones_are_deduped_for_same_signal():
    runtime_state = {}
    signal = {
        "signal_id": "s-trust-1",
        "npc_id": "Bran",
        "turn_index": 1,
        "kind": "relationship_delta",
        "summary": "Bran trusts the player more.",
        "payload": {"target": "Bran", "axis": "trust", "delta": 2},
        "consumed": False,
    }
    # Preload trust just below threshold so this signal causes a transition.
    runtime_state["npc_evolution"] = {
        "signals": [signal],
        "arcs": {
            "Bran": {
                "npc_id": "Bran",
                "arc_stage": "stable",
                "axes": {
                    "trust": 2,
                    "fear": 0,
                    "respect": 0,
                    "curiosity": 0,
                    "resentment": 0,
                    "loyalty": 0,
                },
                "memories": [],
                "world_signals": [],
                "future_hooks": [],
                "semantic_intents": [],
                "milestones": [],
            }
        },
    }

    updated, first = consume_evolution_signal(
        runtime_state=runtime_state,
        signal=signal,
        turn_index=2,
    )
    # Simulate accidental re-run with same signal id/stage transition.
    signal_again = dict(signal)
    signal_again["consumed"] = False
    updated["npc_evolution"]["arcs"]["Bran"]["arc_stage"] = "stable"
    updated, second = consume_evolution_signal(
        runtime_state=updated,
        signal=signal_again,
        turn_index=2,
    )

    milestones = updated["npc_evolution"]["arcs"]["Bran"]["milestones"]
    milestone_ids = [item["milestone_id"] for item in milestones]
    assert first["ok"] is True
    assert second["ok"] is True
    assert len(milestone_ids) == len(set(milestone_ids))