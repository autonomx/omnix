"""Phase 14 — Actor Memory & World Memory unit tests."""
import pytest
from app.rpg.memory.actor_memory_state import (
    append_actor_long_term_memory,
    append_actor_short_term_memory,
    ensure_actor_memory_state,
    get_actor_memory,
)
from app.rpg.memory.world_memory_state import (
    append_rumor,
    ensure_world_memory_state,
)


class TestActorMemoryState:
    def test_ensure_actor_memory_state_creates_structure(self):
        state = {}
        result = ensure_actor_memory_state(state)
        assert "memory_state" in result
        assert "actor_memory" in result["memory_state"]
        assert isinstance(result["memory_state"]["actor_memory"], dict)

    def test_append_actor_short_term_memory(self):
        state = {}
        state = append_actor_short_term_memory(
            state,
            actor_id="npc_1",
            entry={"id": "e1", "summary": "saw something", "kind": "observation", "tick": 1},
        )
        memory = get_actor_memory(state, "npc_1")
        assert len(memory["short_term"]) == 1
        assert memory["short_term"][0]["id"] == "e1"

    def test_append_actor_long_term_memory(self):
        state = {}
        state = append_actor_long_term_memory(
            state,
            actor_id="npc_1",
            entry={"id": "e2", "summary": "learned a fact", "kind": "fact", "tick": 2},
        )
        memory = get_actor_memory(state, "npc_1")
        assert len(memory["long_term"]) == 1
        assert memory["long_term"][0]["id"] == "e2"

    def test_short_term_bounded(self):
        state = {}
        for i in range(15):
            state = append_actor_short_term_memory(
                state,
                actor_id="npc_1",
                entry={"id": f"e{i}", "summary": f"event {i}", "tick": i},
            )
        memory = get_actor_memory(state, "npc_1")
        assert len(memory["short_term"]) <= 10

    def test_long_term_bounded(self):
        state = {}
        for i in range(25):
            state = append_actor_long_term_memory(
                state,
                actor_id="npc_1",
                entry={"id": f"e{i}", "summary": f"fact {i}", "tick": i},
            )
        memory = get_actor_memory(state, "npc_1")
        assert len(memory["long_term"]) <= 20

    def test_get_actor_memory_empty(self):
        state = {}
        memory = get_actor_memory(state, "nonexistent")
        assert memory == {"short_term": [], "long_term": []}

    def test_actor_memory_max_actors(self):
        state = {}
        for i in range(70):
            state = append_actor_short_term_memory(
                state,
                actor_id=f"actor_{i}",
                entry={"id": f"e{i}", "summary": f"event {i}", "tick": i},
            )
        actor_memory = state["memory_state"]["actor_memory"]
        assert len(actor_memory) <= 64


class TestWorldMemoryState:
    def test_ensure_world_memory_state_creates_rumors(self):
        state = {}
        result = ensure_world_memory_state(state)
        assert "memory_state" in result
        assert "rumors" in result["memory_state"]
        assert isinstance(result["memory_state"]["rumors"], list)

    def test_append_rumor(self):
        state = {}
        state = append_rumor(
            state,
            rumor={
                "id": "r1",
                "summary": "dragon spotted",
                "origin": "village",
                "location": "mountains",
                "tick": 1,
                "reach": 0,
            },
        )
        rumors = state["memory_state"]["rumors"]
        assert len(rumors) == 1
        assert rumors[0]["id"] == "r1"

    def test_rumors_bounded(self):
        state = {}
        for i in range(40):
            state = append_rumor(
                state,
                rumor={"id": f"r{i}", "summary": f"rumor {i}", "tick": i},
            )
        rumors = state["memory_state"]["rumors"]
        assert len(rumors) <= 32

    def test_rumor_normalization(self):
        state = {}
        state = append_rumor(state, rumor={"summary": "  test  ", "tick": "not_int"})
        rumors = state["memory_state"]["rumors"]
        assert rumors[0]["summary"] == "test"
        assert rumors[0]["tick"] == 0