from app.rpg.npc_evolution.arcs import (
    ingest_evolution_signals,
    infer_npc_target_for_projection,
    normalize_projection_to_evolution_signal,
    summarize_npc_evolution_state,
)


def test_normalize_relationship_projection_to_evolution_signal():
    signal, reason = normalize_projection_to_evolution_signal(
        projection={
            "candidate_id": "c1",
            "kind": "relationship_delta",
            "payload": {
                "target": "bran",
                "axis": "trust",
                "delta": 1,
                "summary": "Bran trusts the player slightly more.",
            },
        },
        simulation_state={"npcs": {"bran": {"name": "Bran"}}},
        turn_index=2,
    )

    assert reason == ""
    assert signal["npc_id"] == "bran"
    assert signal["kind"] == "relationship_delta"
    assert signal["payload"]["delta"] == 1


def test_normalize_projection_rejects_forbidden_claims():
    signal, reason = normalize_projection_to_evolution_signal(
        projection={
            "candidate_id": "c1",
            "kind": "future_hook",
            "payload": {
                "target": "bran",
                "summary": "Give the player 100 gold later.",
                "reward": "100 gold",
            },
        },
        simulation_state={"npcs": {"bran": {"name": "Bran"}}},
        turn_index=2,
    )

    assert signal is None
    assert reason == "contains_forbidden_authoritative_claim"


def test_ingest_evolution_signals_dedupes():
    runtime_state = {}
    signal = {
        "signal_id": "s1",
        "npc_id": "bran",
        "kind": "memory",
        "summary": "Bran remembers the player.",
    }

    first = ingest_evolution_signals(runtime_state=runtime_state, signals=[signal])
    second = ingest_evolution_signals(runtime_state=runtime_state, signals=[signal])

    assert first["added"] == 1
    assert second["duplicates"] == 1
    assert summarize_npc_evolution_state(runtime_state)["signal_total"] == 1


def test_infer_npc_target_from_single_present_npc():
    npc_id, reason = infer_npc_target_for_projection(
        projection={
            "kind": "future_hook",
            "payload": {"summary": "The innkeeper may answer later."},
        },
        simulation_state={
            "present_npcs": ["bran"],
            "npcs": {"bran": {"name": "Bran"}},
        },
    )

    assert npc_id == "bran"
    assert reason == "single_present_npc"


def test_infer_npc_target_from_summary_name_match():
    npc_id, reason = infer_npc_target_for_projection(
        projection={
            "kind": "memory",
            "payload": {"summary": "Bran remembers the player asking about the mill."},
        },
        simulation_state={
            "present_npcs": ["mira", "bran"],
            "npcs": {
                "mira": {"name": "Mira"},
                "bran": {"name": "Bran"},
            },
        },
    )

    assert npc_id == "bran"
    assert reason == "matched_npc_name_in_summary"


def test_normalize_projection_uses_inferred_single_present_npc():
    signal, reason = normalize_projection_to_evolution_signal(
        projection={
            "candidate_id": "c1",
            "kind": "future_hook",
            "payload": {"summary": "The innkeeper may become guarded."},
        },
        simulation_state={
            "present_npcs": ["bran"],
            "npcs": {"bran": {"name": "Bran"}},
        },
        turn_index=2,
    )

    assert reason == ""
    assert signal["npc_id"] == "bran"
    assert signal["target_inference"] == "single_present_npc"


def test_infer_npc_target_from_nested_scene_nearby_npcs_and_progression_state():
    npc_id, reason = infer_npc_target_for_projection(
        projection={
            "kind": "future_hook",
            "payload": {"summary": "The innkeeper may become more guarded."},
        },
        simulation_state={
            "scene": {"nearby_npcs": ["bran"]},
            "npc_progression_state": {"npcs": {"bran": {"name": "Bran", "role": "innkeeper"}}},
        },
    )

    assert npc_id == "bran"
    assert reason == "single_present_npc"


def test_explicit_unknown_target_falls_back_to_summary_name_match():
    signal, reason = normalize_projection_to_evolution_signal(
        projection={
            "candidate_id": "c1",
            "kind": "memory",
            "payload": {
                "owner": "Player",
                "summary": "Bran remembers that the player asked about gossip.",
            },
        },
        simulation_state={
            "scene": {"nearby_npcs": ["bran", "mira"]},
            "npc_progression_state": {
                "npcs": {
                    "bran": {"name": "Bran"},
                    "mira": {"name": "Mira"},
                }
            },
        },
        turn_index=2,
    )

    assert reason == ""
    assert signal["npc_id"] == "bran"
    assert signal["target_inference"] == "matched_npc_name_in_summary"