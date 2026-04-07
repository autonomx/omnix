"""Regression tests for Phase 16.2/18.0 — Memory inspector + GM tooling."""
from app.rpg.presentation.memory_inspector import build_memory_inspector_payload
from app.rpg.presentation.gm_tooling import build_gm_tooling_payload


def test_regression_memory_inspector_none_state():
    """None state should not crash."""
    payload = build_memory_inspector_payload(None)
    assert payload["actor_memory"] == []
    assert payload["world_rumors"] == []


def test_regression_memory_inspector_non_dict_entries():
    """Non-dict entries should be safely ignored."""
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": ["not_a_dict", 42, None]}},
            "world_memory": {"rumors": ["not_a_dict"]},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    # Non-dict entries are wrapped as empty dicts
    assert len(payload["actor_memory"]) == 1


def test_regression_gm_tooling_none_state():
    """None state should not crash GM tooling."""
    payload = build_gm_tooling_payload(None)
    assert "visuals" in payload
    assert "memory" in payload
    assert "operations" in payload


def test_regression_gm_tooling_none_queue_and_manifest():
    """None queue_jobs and asset_manifest should be handled."""
    payload = build_gm_tooling_payload({}, queue_jobs=None, asset_manifest=None)
    assert payload["visuals"]["queue_job_count"] == 0
    assert payload["visuals"]["manifest_asset_count"] == 0


def test_regression_memory_inspector_preserves_strength_values():
    """Strength values should be preserved exactly."""
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": 0.7531}]}},
            "world_memory": {"rumors": [{"text": "rumor", "strength": 0.8234, "reach": 3}]},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    assert payload["actor_memory"][0]["entries"][0]["strength"] == 0.7531
    assert payload["world_rumors"][0]["strength"] == 0.8234


def test_regression_gm_tooling_operations_stable():
    """Operations dict should have consistent keys across calls."""
    p1 = build_gm_tooling_payload({})
    p2 = build_gm_tooling_payload({})
    assert set(p1["operations"].keys()) == set(p2["operations"].keys())


def test_regression_memory_inspector_entry_count_accurate():
    """entry_count should reflect total entries, not capped list."""
    entries = [{"text": f"fact_{i}", "strength": 0.5} for i in range(30)]
    simulation_state = {
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": entries}},
            "world_memory": {"rumors": []},
        }
    }
    payload = build_memory_inspector_payload(simulation_state)
    assert payload["actor_memory"][0]["entry_count"] == 30
    assert len(payload["actor_memory"][0]["entries"]) == 20
