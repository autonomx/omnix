"""Unit tests for Phase 18.0 — Unified GM tooling."""
from app.rpg.presentation.gm_tooling import build_gm_tooling_payload


def test_build_gm_tooling_payload_contains_visual_memory_and_operations():
    simulation_state = {
        "presentation_state": {"visual_state": {"image_requests": [], "visual_assets": []}},
        "memory_state": {"actor_memory": {}, "world_memory": {"rumors": []}},
    }
    payload = build_gm_tooling_payload(simulation_state, queue_jobs=[], asset_manifest={"assets": {}})
    assert "visuals" in payload
    assert "memory" in payload
    assert "operations" in payload


def test_gm_tooling_visuals_section():
    simulation_state = {
        "presentation_state": {
            "visual_state": {
                "image_requests": [{"request_id": "r1", "kind": "portrait", "target_id": "npc:a"}],
                "visual_assets": [{"asset_id": "a1", "kind": "portrait", "target_id": "npc:a"}],
            }
        },
        "memory_state": {"actor_memory": {}, "world_memory": {"rumors": []}},
    }
    payload = build_gm_tooling_payload(simulation_state, queue_jobs=[], asset_manifest={"assets": {}})
    assert payload["visuals"]["request_count"] == 1
    assert payload["visuals"]["asset_count"] == 1


def test_gm_tooling_memory_section():
    simulation_state = {
        "presentation_state": {"visual_state": {}},
        "memory_state": {
            "actor_memory": {"npc:a": {"entries": [{"text": "fact", "strength": 0.5}]}},
            "world_memory": {"rumors": [{"text": "rumor", "strength": 0.7, "reach": 2}]},
        },
    }
    payload = build_gm_tooling_payload(simulation_state, queue_jobs=[], asset_manifest={"assets": {}})
    assert len(payload["memory"]["actor_memory"]) == 1
    assert len(payload["memory"]["world_rumors"]) == 1


def test_gm_tooling_operations_list():
    payload = build_gm_tooling_payload({}, queue_jobs=[], asset_manifest={"assets": {}})
    ops = payload["operations"]
    assert "visual_inspector_route" in ops
    assert "memory_reinforce_route" in ops
    assert "memory_decay_route" in ops
    assert "queue_normalize_route" in ops
    assert "session_export_route" in ops
    assert "session_import_route" in ops


def test_gm_tooling_handles_empty_state():
    payload = build_gm_tooling_payload({})
    assert "visuals" in payload
    assert "memory" in payload
    assert "operations" in payload


def test_gm_tooling_handles_none():
    payload = build_gm_tooling_payload(None)
    assert "visuals" in payload
    assert "memory" in payload


def test_gm_tooling_queue_jobs_passed_through():
    simulation_state = {
        "presentation_state": {"visual_state": {}},
        "memory_state": {},
    }
    jobs = [{"job_id": "j1", "session_id": "s1", "request_id": "r1", "status": "pending"}]
    payload = build_gm_tooling_payload(simulation_state, queue_jobs=jobs, asset_manifest={"assets": {}})
    assert payload["visuals"]["queue_job_count"] == 1


def test_gm_tooling_asset_manifest_passed_through():
    simulation_state = {
        "presentation_state": {"visual_state": {}},
        "memory_state": {},
    }
    manifest = {"assets": {"a1": {"hash": "abc", "filename": "img.png", "mime_type": "image/png", "size": 1024, "kind": "portrait", "target_id": "npc:a"}}}
    payload = build_gm_tooling_payload(simulation_state, queue_jobs=[], asset_manifest=manifest)
    assert payload["visuals"]["manifest_asset_count"] == 1
