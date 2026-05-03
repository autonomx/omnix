from app.rpg.memory.causal_memory import (
    add_causal_memory,
    ensure_npc_memory_state,
    make_causal_memory,
)


def test_make_causal_memory_is_json_safe_and_stable():
    memory = make_causal_memory(
        subject_id="bran",
        event_id="evt:1",
        kind="observed",
        source="manual",
        summary="Bran saw the player enter.",
        facts={"actor_id": "player", "location_id": "tavern_common_room"},
        tags=["arrival"],
        turn_index=1,
    )

    assert memory["memory_id"].startswith("mem:")
    assert memory["subject_id"] == "bran"
    assert memory["facts"]["actor_id"] == "player"


def test_add_causal_memory_dedupes_by_memory_id():
    simulation_state = {}
    memory = make_causal_memory(
        subject_id="bran",
        event_id="evt:1",
        kind="observed",
        source="manual",
        summary="Bran saw the player enter.",
        facts={"actor_id": "player"},
        turn_index=1,
    )

    first = add_causal_memory(simulation_state, memory)
    second = add_causal_memory(simulation_state, memory)

    assert first["ok"] is True
    assert second["ok"] is True
    rows = simulation_state["npc_memory_state"]["memories_by_subject"]["bran"]
    assert len(rows) == 1


def test_memory_state_bounds_per_subject():
    simulation_state = {
        "npc_memory_state": {
            "version": 1,
            "max_memories_per_subject": 3,
            "memories_by_subject": {},
        }
    }

    for i in range(10):
        add_causal_memory(
            simulation_state,
            make_causal_memory(
                subject_id="bran",
                event_id=f"evt:{i}",
                kind="observed",
                source="manual",
                summary=f"event {i}",
                facts={"actor_id": "player", "index": i},
                turn_index=i,
            ),
        )

    state = ensure_npc_memory_state(simulation_state)
    rows = state["memories_by_subject"]["bran"]
    assert len(rows) == 3
    assert [row["event_id"] for row in rows] == ["evt:7", "evt:8", "evt:9"]


def test_invalid_environment_subject_is_not_recorded():
    simulation_state = {}
    result = add_causal_memory(
        simulation_state,
        make_causal_memory(
            subject_id="Environment/NPCs (General)",
            event_id="evt:bad",
            kind="observed",
            source="manual",
            summary="bad",
        ),
    )

    assert result["ok"] is False
    assert "Environment/NPCs (General)" not in simulation_state.get("npc_memory_state", {}).get("memories_by_subject", {})