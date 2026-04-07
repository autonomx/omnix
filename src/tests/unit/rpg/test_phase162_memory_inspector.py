"""Unit tests for Phase 16.2 — Memory inspector builder."""
from app.rpg.presentation.memory_inspector import build_memory_inspector_payload


def test_build_memory_inspector_payload_surfaces_actor_memory_and_rumors():
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "Known fact", "strength": 0.7}]}},
            "world_memory": {"rumors": [{"text": "Bridge rumor", "strength": 0.8, "reach": 2}]},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    assert len(payload["actor_memory"]) == 1
    assert len(payload["world_rumors"]) == 1


def test_memory_inspector_sorts_actors_alphabetically():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "npc:z": {"entries": [{"text": "z fact", "strength": 0.5}]},
                "npc:a": {"entries": [{"text": "a fact", "strength": 0.5}]},
                "npc:m": {"entries": [{"text": "m fact", "strength": 0.5}]},
            },
            "world_memory": {"rumors": []},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    actor_ids = [row["actor_id"] for row in payload["actor_memory"]]
    assert actor_ids == ["npc:a", "npc:m", "npc:z"]


def test_memory_inspector_sorts_entries_by_strength():
    simulation_state = {
        "memory_state": {
            "actor_memory": {
                "npc:a": {
                    "entries": [
                        {"text": "weak", "strength": 0.2},
                        {"text": "strong", "strength": 0.9},
                        {"text": "medium", "strength": 0.5},
                    ]
                }
            },
            "world_memory": {"rumors": []},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    entries = payload["actor_memory"][0]["entries"]
    assert entries[0]["text"] == "strong"
    assert entries[-1]["text"] == "weak"


def test_memory_inspector_caps_entries_at_20():
    entries = [{"text": f"fact_{i}", "strength": float(i) / 100.0} for i in range(30)]
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": entries}},
            "world_memory": {"rumors": []},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    assert len(payload["actor_memory"][0]["entries"]) == 20
    assert payload["actor_memory"][0]["entry_count"] == 30


def test_memory_inspector_caps_rumors_at_50():
    rumors = [{"text": f"rumor_{i}", "strength": float(i) / 100.0, "reach": 1} for i in range(60)]
    simulation_state = {
        "memory_state": {
            "actor_memory": {},
            "world_memory": {"rumors": rumors},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    assert len(payload["world_rumors"]) == 50


def test_memory_inspector_sorts_rumors_by_strength_then_reach():
    simulation_state = {
        "memory_state": {
            "actor_memory": {},
            "world_memory": {
                "rumors": [
                    {"text": "local", "strength": 0.5, "reach": 1},
                    {"text": "widespread", "strength": 0.5, "reach": 10},
                    {"text": "strong", "strength": 0.9, "reach": 1},
                ]
            },
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    assert payload["world_rumors"][0]["text"] == "strong"
    # Among same strength, higher reach comes first
    assert payload["world_rumors"][1]["text"] == "widespread"


def test_memory_inspector_includes_action_routes():
    payload = build_memory_inspector_payload({})
    assert "reinforce_route" in payload["actions"]
    assert "decay_route" in payload["actions"]


def test_memory_inspector_handles_empty_state():
    payload = build_memory_inspector_payload({})
    assert payload["actor_memory"] == []
    assert payload["world_rumors"] == []


def test_memory_inspector_handles_none():
    payload = build_memory_inspector_payload(None)
    assert payload["actor_memory"] == []
    assert payload["world_rumors"] == []
