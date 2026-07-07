from __future__ import annotations

from copy import deepcopy

import pytest

from app.rpg.map_projection import project_session_map_overlay
from app.rpg.map_world_integration import (
    MapWorldIntegrationError,
    canonical_route_id_for_locations,
    canonical_world_map_model,
    integrate_canonical_world_map_state,
    map_repository_for_session,
    resolve_map_id_for_location,
)


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:world", "session_id": "session:world"},
        "state": {
            "current_turn": 9,
            "player": {"location_id": "frost_haven"},
            "world_graph": {
                "schema_version": 1,
                "seed": 4812,
                "current_location_id": "frost_haven",
                "discovered_location_ids": ["frost_haven", "old_quarry"],
                "locations": [
                    {
                        "id": "frost_haven",
                        "name": "Frost Haven",
                        "region_id": "northern_pass",
                        "status": "expanded",
                        "tags": ["settlement"],
                        "services": ["inn", "smithy", "market"],
                    },
                    {
                        "id": "old_quarry",
                        "name": "Old Quarry",
                        "region_id": "northern_pass",
                        "status": "expanded",
                        "tags": ["danger", "quarry"],
                        "danger": 4,
                    },
                    {
                        "id": "glimmerdeep_pass",
                        "name": "Glimmerdeep Pass",
                        "region_id": "northern_pass",
                        "status": "stub",
                        "tags": ["pass"],
                    },
                ],
                "routes": [
                    {
                        "id": "road:quarry-lock",
                        "from_id": "frost_haven",
                        "to_id": "old_quarry",
                        "direction": "both",
                        "status": "locked",
                        "known": True,
                        "safe": True,
                    },
                    {
                        "id": "road:high-pass",
                        "from_id": "frost_haven",
                        "to_id": "glimmerdeep_pass",
                        "direction": "forward",
                        "status": "open",
                        "known": True,
                        "safe": False,
                        "tags": ["trail"],
                    },
                ],
            },
        },
    }


def test_canonical_world_model_preserves_route_truth() -> None:
    model = canonical_world_map_model(_session())

    assert model is not None
    assert model.current_location_id == "frost_haven"
    assert model.discovered_location_ids == ("frost_haven", "old_quarry")
    assert model.graph.get_route("road:quarry-lock").status == "locked"
    assert model.graph.get_route("road:high-pass").direction == "forward"
    assert canonical_route_id_for_locations(_session(), "frost_haven", "old_quarry") == "road:quarry-lock"
    assert canonical_route_id_for_locations(_session(), "glimmerdeep_pass", "frost_haven") is None


def test_repository_builds_region_and_settlement_from_world_graph() -> None:
    repository = map_repository_for_session(_session())
    region = repository.get("region:generated:northern_pass")
    settlement = repository.get("settlement:generated:frost_haven")

    assert region.level == "region"
    assert {item.location_id for item in region.objects} == {
        "frost_haven",
        "old_quarry",
        "glimmerdeep_pass",
    }
    assert {route.route_id for route in region.route_geometry} == {
        "road:quarry-lock",
        "road:high-pass",
    }
    assert settlement.parent_map_id == region.map_id
    assert any(item.location_id == "frost_haven" for item in settlement.objects)
    quarry_gate = next(item for item in settlement.objects if item.location_id == "old_quarry")
    assert "route_id:road:quarry-lock" in quarry_gate.tags
    assert "road:quarry-lock" in {route.route_id for route in settlement.route_geometry}


def test_map_state_and_overlay_use_canonical_world_truth() -> None:
    session = integrate_canonical_world_map_state(deepcopy(_session()))
    map_state = session["state"]["map_state"]

    assert map_state["source"] == "canonical_world_graph"
    assert map_state["current_map_id"] == "settlement:generated:frost_haven"
    assert map_state["route_states"]["road:quarry-lock"]["status"] == "locked"

    repository = map_repository_for_session(session)
    overlay = project_session_map_overlay(session, map_state["current_map_id"], repository)

    assert overlay.availability == "ready"
    player = next(marker for marker in overlay.markers if marker.kind == "player")
    assert player.object_id == "landmark:frost_haven:center"
    quarry_gate = next(
        capability
        for capability in overlay.capabilities
        if capability.type == "travel" and capability.target_location_id == "old_quarry"
    )
    assert quarry_gate.route_id == "road:quarry-lock"
    assert quarry_gate.enabled is False
    assert quarry_gate.disabled_reason == "route_locked"


def test_explicit_binding_selects_curated_definition() -> None:
    session = _session()
    session["state"]["world_graph"]["map_bindings"] = {
        "frost_haven": "settlement:frost_haven",
    }

    repository = map_repository_for_session(session)

    assert resolve_map_id_for_location(session, "frost_haven", repository) == "settlement:frost_haven"


def test_invalid_schema_is_typed() -> None:
    session = _session()
    session["state"]["world_graph"]["schema_version"] = 4

    with pytest.raises(MapWorldIntegrationError, match="unsupported_world_graph_schema:4"):
        canonical_world_map_model(session)


def test_display_labels_do_not_create_canonical_world_maps() -> None:
    session = {
        "manifest": {"id": "session:legacy"},
        "state": {"location": "Frost Haven", "current_location": "Frost Haven"},
    }

    assert canonical_world_map_model(session) is None
    assert map_repository_for_session(session).find("region:generated:northern_pass") is None
