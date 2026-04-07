"""Unit tests for Phase 14.4 — Memory decay / reinforcement engine."""
from app.rpg.memory.decay import decay_memory_state, reinforce_actor_memory


def test_decay_memory_state_reduces_strength():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "hero": {
                    "entries": [
                        {"text": "Strong memory", "strength": 0.9},
                    ]
                }
            },
            "world_memory": {"rumors": []},
        }
    }
    result = decay_memory_state(simulation_state, decay_step=0.1)
    entries = result["memory_state"]["actor_memory"]["hero"]["entries"]
    assert abs(entries[0]["strength"] - 0.8) < 0.001


def test_decay_memory_state_does_not_go_below_zero():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "hero": {
                    "entries": [
                        {"text": "Weak memory", "strength": 0.02},
                    ]
                }
            },
            "world_memory": {"rumors": []},
        }
    }
    result = decay_memory_state(simulation_state, decay_step=0.1)
    entries = result["memory_state"]["actor_memory"]["hero"]["entries"]
    assert entries[0]["strength"] >= 0.0


def test_decay_memory_state_dedupes_and_caps_rumors():
    """Test that duplicate rumors are deduplicated, keeping the highest strength."""
    simulation_state = {
        "memory_state": {
            "actor_memory": {},
            "world_memory": {
                "rumors": [
                    {"text": "Same", "strength": 0.9, "reach": 2},
                    {"text": "Same", "strength": 0.4, "reach": 1},
                ]
            },
        }
    }
    out = decay_memory_state(simulation_state, decay_step=0.0)
    rumors = out["memory_state"]["world_memory"]["rumors"]
    assert len(rumors) == 1
    assert rumors[0]["text"] == "Same"


def test_reinforce_actor_memory_increases_existing():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "hero": {
                    "entries": [
                        {"text": "Met the king", "strength": 0.5},
                    ]
                }
            },
            "world_memory": {"rumors": []},
        }
    }
    result = reinforce_actor_memory(simulation_state, "hero", "Met the king", amount=0.3)
    entries = result["memory_state"]["actor_memory"]["hero"]["entries"]
    assert abs(entries[0]["strength"] - 0.8) < 0.001


def test_reinforce_actor_memory_adds_new():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "hero": {"entries": []}
            },
            "world_memory": {"rumors": []},
        }
    }
    result = reinforce_actor_memory(simulation_state, "hero", "New memory", amount=0.4)
    entries = result["memory_state"]["actor_memory"]["hero"]["entries"]
    assert len(entries) == 1
    assert entries[0]["text"] == "New memory"
    assert abs(entries[0]["strength"] - 0.4) < 0.001