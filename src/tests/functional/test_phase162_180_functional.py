"""Functional tests for Phase 16.2/18.0 — Memory inspector + GM tooling."""
from app.rpg.presentation.memory_inspector import build_memory_inspector_payload
from app.rpg.presentation.gm_tooling import build_gm_tooling_payload


def _build_full_simulation_state():
    return {
        "presentation_state": {
            "visual_state": {
                "image_requests": [
                    {"request_id": f"req:{i}", "kind": "portrait", "target_id": f"npc:{i}"}
                    for i in range(5)
                ],
                "visual_assets": [
                    {"asset_id": f"asset:{i}", "kind": "portrait", "target_id": f"npc:{i}"}
                    for i in range(3)
                ],
            }
        },
        "memory_state": {
            "actor_memory": {
                "npc:warrior": {
                    "entries": [
                        {"text": "Fought dragon", "strength": 0.9},
                        {"text": "Met at tavern", "strength": 0.4},
                    ]
                },
                "npc:mage": {
                    "entries": [
                        {"text": "Fire spell", "strength": 0.7},
                    ]
                },
            },
            "world_memory": {
                "rumors": [
                    {"text": "King ill", "strength": 0.8, "reach": 5},
                    {"text": "Dragon spotted", "strength": 0.6, "reach": 3},
                ]
            },
        },
    }


def test_memory_inspector_full_state():
    """Memory inspector should surface all actor memories and rumors."""
    state = _build_full_simulation_state()
    payload = build_memory_inspector_payload(state)
    assert len(payload["actor_memory"]) == 2
    assert len(payload["world_rumors"]) == 2
    # Actions available
    assert payload["actions"]["reinforce_route"]
    assert payload["actions"]["decay_route"]


def test_gm_tooling_full_state():
    """GM tooling should unify visual and memory inspection."""
    state = _build_full_simulation_state()
    queue_jobs = [{"job_id": "j1", "status": "pending", "session_id": "s1", "request_id": "r1"}]
    manifest = {"assets": {"a1": {"hash": "abc", "filename": "img.png"}}}

    payload = build_gm_tooling_payload(state, queue_jobs=queue_jobs, asset_manifest=manifest)

    # Visuals section
    assert payload["visuals"]["request_count"] == 5
    assert payload["visuals"]["asset_count"] == 3
    assert payload["visuals"]["queue_job_count"] == 1
    assert payload["visuals"]["manifest_asset_count"] == 1

    # Memory section
    assert len(payload["memory"]["actor_memory"]) == 2
    assert len(payload["memory"]["world_rumors"]) == 2

    # Operations
    assert len(payload["operations"]) >= 6


def test_gm_tooling_consistency_with_individual_inspectors():
    """GM tooling should produce consistent results with individual inspectors."""
    state = _build_full_simulation_state()

    memory_payload = build_memory_inspector_payload(state)
    gm_payload = build_gm_tooling_payload(state, queue_jobs=[], asset_manifest={"assets": {}})

    # Memory section should match standalone inspector
    assert gm_payload["memory"]["actor_memory"] == memory_payload["actor_memory"]
    assert gm_payload["memory"]["world_rumors"] == memory_payload["world_rumors"]


def test_gm_tooling_handles_minimal_state():
    """GM tooling should handle minimal/empty state without errors."""
    payload = build_gm_tooling_payload({})
    assert payload["visuals"]["request_count"] == 0
    assert payload["visuals"]["asset_count"] == 0
    assert payload["memory"]["actor_memory"] == []
    assert payload["memory"]["world_rumors"] == []
    assert len(payload["operations"]) >= 6
