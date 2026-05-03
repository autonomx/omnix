from app.rpg.memory.causal_memory import add_causal_memory, make_causal_memory
from app.rpg.memory.causal_retrieval import retrieve_causal_memories


def _add(simulation_state, *, event_id, subject_id="bran", actor_id="player", target_id="", location_id="tavern_common_room", tags=None, turn_index=1):
    add_causal_memory(
        simulation_state,
        make_causal_memory(
            subject_id=subject_id,
            event_id=event_id,
            kind="observed",
            source="manual",
            summary=f"{subject_id} remembers {event_id}",
            facts={
                "actor_id": actor_id,
                "target_id": target_id,
                "location_id": location_id,
                "action": "test",
            },
            tags=list(tags or []),
            turn_index=turn_index,
        ),
    )


def test_retrieval_prefers_actor_target_location_tags_and_recency():
    simulation_state = {}
    _add(simulation_state, event_id="evt:old", actor_id="mira", location_id="street", tags=["smalltalk"], turn_index=1)
    _add(simulation_state, event_id="evt:match", actor_id="player", target_id="mira", location_id="tavern_common_room", tags=["threat"], turn_index=2)
    _add(simulation_state, event_id="evt:new", actor_id="player", target_id="mira", location_id="tavern_common_room", tags=["threat"], turn_index=3)

    rows = retrieve_causal_memories(
        simulation_state,
        "bran",
        actor_id="player",
        target_id="mira",
        location_id="tavern_common_room",
        tags=["threat"],
        max_items=2,
    )

    assert [row["event_id"] for row in rows] == ["evt:new", "evt:match"]


def test_retrieval_is_subject_scoped_not_global():
    simulation_state = {}
    _add(simulation_state, subject_id="bran", event_id="evt:bran", actor_id="player")
    _add(simulation_state, subject_id="mira", event_id="evt:mira", actor_id="player")

    rows = retrieve_causal_memories(simulation_state, "bran", actor_id="player")

    assert [row["event_id"] for row in rows] == ["evt:bran"]


def test_retrieval_returns_compact_rows():
    simulation_state = {}
    _add(simulation_state, event_id="evt:compact", actor_id="player", tags=["threat"])

    row = retrieve_causal_memories(simulation_state, "bran", max_items=1)[0]

    assert "summary" in row
    assert "facts" in row
    assert row["facts"]["actor_id"] == "player"
    assert "timestamp" not in row