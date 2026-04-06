"""Unit tests for Phase 14.0 — Memory system."""
from app.rpg.memory.memory_state import (
    append_long_term_memory,
    append_short_term_memory,
    append_world_memory,
    ensure_memory_state,
)


def test_ensure_memory_state():
    result = ensure_memory_state({})
    assert "memory_state" in result


def test_append_short_term_memory():
    result = append_short_term_memory({}, {"id": "m1", "summary": "hello"})
    assert len(result["memory_state"]["short_term"]) == 1


def test_append_long_term_memory():
    result = append_long_term_memory({}, {"id": "m1", "summary": "hello"})
    assert len(result["memory_state"]["long_term"]) == 1


def test_append_world_memory():
    result = append_world_memory({}, {"id": "m1", "summary": "rumor"})
    assert len(result["memory_state"]["world_memory"]) == 1


def test_short_term_bounded():
    state = {}
    for i in range(20):
        state = append_short_term_memory(state, {"id": f"m{i}", "summary": f"msg {i}"})
    assert len(state["memory_state"]["short_term"]) <= 12


def test_long_term_bounded():
    state = {}
    for i in range(30):
        state = append_long_term_memory(state, {"id": f"m{i}", "summary": f"msg {i}"})
    assert len(state["memory_state"]["long_term"]) <= 24


def test_world_memory_bounded():
    state = {}
    for i in range(40):
        state = append_world_memory(state, {"id": f"m{i}", "summary": f"msg {i}"})
    assert len(state["memory_state"]["world_memory"]) <= 32


def test_memory_entry_normalization():
    result = append_short_term_memory({}, {"id": "  test  ", "summary": "  hello  ", "kind": "", "tick": "bad"})
    entry = result["memory_state"]["short_term"][0]
    assert entry["id"] == "test"
    assert entry["summary"] == "hello"
    assert entry["kind"] == "fact"
    assert entry["tick"] == 0