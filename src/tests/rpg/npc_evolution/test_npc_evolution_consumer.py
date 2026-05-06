from app.rpg.npc_evolution.consumer import (
    consume_accepted_advisory_projections,
    consume_evolution_signal,
)
from app.rpg.npc_evolution.arcs import ingest_evolution_signals


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