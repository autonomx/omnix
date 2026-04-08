"""Phase 14.4 — Memory Decay / Reinforcement unit tests."""

from app.rpg.memory.memory_decay import (
    _decay_entries,
    _reinforce_entries,
    apply_memory_decay,
)


def test_decay_entries_removes_old():
    entries = [
        {"id": "1", "summary": "old", "tick": 0},
        {"id": "2", "summary": "recent", "tick": 10},
    ]
    result = _decay_entries(entries, current_tick=10, max_age=5)
    assert len(result) == 1
    assert result[0]["id"] == "2"


def test_reinforce_entries_deduplicates():
    entries = [
        {"id": "1", "summary": "met player", "tick": 5},
        {"id": "2", "summary": "met player", "tick": 10},
    ]
    result = _reinforce_entries(entries)
    assert len(result) == 1
    assert result[0]["tick"] == 10


def test_apply_memory_decay_returns_memory_state():
    state = {"memory_state": {"short_term": [], "long_term": [], "actor_memory": {}, "rumors": []}}
    result = apply_memory_decay(state, current_tick=10)
    assert "memory_state" in result


def test_apply_memory_decay_removes_expired_rumors():
    state = {"memory_state": {"short_term": [], "long_term": [], "actor_memory": {}, "rumors": [
        {"id": "r1", "summary": "old rumor", "tick": 0, "reach": 5}
    ]}}
    result = apply_memory_decay(state, current_tick=50)
    assert len(result["memory_state"]["rumors"]) == 0


def test_apply_memory_decay_keeps_recent_rumors():
    state = {"memory_state": {"short_term": [], "long_term": [], "actor_memory": {}, "rumors": [
        {"id": "r1", "summary": "recent rumor", "tick": 40, "reach": 5}
    ]}}
    result = apply_memory_decay(state, current_tick=50)
    assert len(result["memory_state"]["rumors"]) == 1