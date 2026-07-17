from __future__ import annotations

from fastapi import FastAPI

from app.gateway.rpg_grid_performance_routes import register_rpg_grid_performance_routes
from app.rpg.grid_runtime_performance import (
    GridRuntimeMetrics,
    GridRuntimeTimings,
    assess_grid_renderer,
    profile_grid_runtime,
)
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import create_map_instance_snapshot
from app.rpg.map_observer_runtime import ObserverPerceptionPolicy, observe_map


def _metrics(**overrides: int | str) -> GridRuntimeMetrics:
    values = {
        "cells": 100,
        "actors": 4,
        "footprint_cells": 4,
        "terrain_overrides": 0,
        "object_states": 0,
        "route_states": 0,
        "portals": 0,
        "spawn_points": 0,
        "zones": 0,
        "visible_cells": 100,
        "known_cells": 100,
        "projection_bytes": 10_000,
        "event_count": 10,
        "path_probe_status": "resolved",
        "path_probe_length": 8,
        "path_probe_cost": 70,
        "path_probe_error": "",
    }
    values.update(overrides)
    return GridRuntimeMetrics.model_validate(values)


def _definition(width: int = 10, height: int = 10) -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:performance",
            level="encounter",
            definition_revision=1,
            world_id="world:performance",
            world_revision=1,
            width=width,
            height=height,
            terrain_palette=(TerrainRule(code=".", terrain_id="floor"),),
            terrain_rows=tuple("." * width for _ in range(height)),
        )
    )


def test_small_grid_retains_svg() -> None:
    decision = assess_grid_renderer(
        _metrics(),
        GridRuntimeTimings(projection_ms=2.0, pathfinding_ms=4.0),
    )

    assert decision.renderer == "svg"
    assert decision.recommendation == "retain_svg"
    assert decision.renderer_reasons == ()
    assert decision.runtime_warnings == ()


def test_backend_latency_warns_without_forcing_renderer_escalation() -> None:
    decision = assess_grid_renderer(
        _metrics(),
        GridRuntimeTimings(projection_ms=30.0, pathfinding_ms=80.0),
    )

    assert decision.renderer == "svg"
    assert decision.recommendation == "retain_svg"
    assert decision.renderer_reasons == ()
    assert decision.runtime_warnings == (
        "projection_ms_exceeds_runtime_budget:30.000>16.000",
        "pathfinding_ms_exceeds_runtime_budget:80.000>50.000",
    )


def test_visual_workload_thresholds_recommend_pixi_with_exact_reasons() -> None:
    decision = assess_grid_renderer(
        _metrics(
            cells=4_225,
            actors=300,
            footprint_cells=600,
            projection_bytes=1_600_000,
        ),
        GridRuntimeTimings(projection_ms=2.0, pathfinding_ms=4.0),
    )

    assert decision.renderer == "pixi"
    assert decision.recommendation == "escalate_to_pixi"
    assert decision.renderer_reasons == (
        "cells_exceeds_svg_budget:4225>4096",
        "actors_exceeds_svg_budget:300>256",
        "footprint_cells_exceeds_svg_budget:600>512",
        "projection_bytes_exceeds_svg_budget:1600000>1500000",
    )


def test_profile_measures_observer_projection_and_path_probe() -> None:
    definition = _definition()
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:performance",
        campaign_id="campaign:a",
        location_id="location:performance",
        definition=definition,
        actors=(
            GridActorPlacement(actor_id="observer:a", cell=(1, 1)),
            GridActorPlacement(actor_id="npc:a", cell=(4, 4)),
        ),
    )
    knowledge, _ = observe_map(
        definition,
        snapshot,
        observer_actor_id="observer:a",
        policy=ObserverPerceptionPolicy(sight_radius=5, detection_radius=2),
    )

    profile = profile_grid_runtime(
        definition,
        snapshot,
        observer_knowledge=knowledge,
        path_probe_actor_id="observer:a",
        path_probe_destination=(8, 8),
        event_count=3,
    )

    assert profile.map_instance_id == snapshot.map_instance_id
    assert profile.observer_actor_id == "observer:a"
    assert profile.decision.metrics.cells == 100
    assert profile.decision.metrics.actors == 2
    assert profile.decision.metrics.visible_cells == len(knowledge.visible_cells)
    assert profile.decision.metrics.known_cells == len(knowledge.known_cells)
    assert profile.decision.metrics.event_count == 3
    assert profile.decision.metrics.path_probe_status == "resolved"
    assert profile.decision.metrics.path_probe_length > 1
    assert profile.decision.metrics.path_probe_cost > 0
    assert profile.decision.metrics.projection_bytes > 0
    assert profile.decision.timings.projection_ms >= 0
    assert profile.decision.timings.pathfinding_ms is not None


def test_grid_performance_route_is_hidden_and_installed() -> None:
    path = "/api/rpg/map-instances/{map_instance_id}/performance-profile"
    app = FastAPI()
    register_rpg_grid_performance_routes(app)
    assert path in {route.path for route in app.routes}
    assert path not in app.openapi()["paths"]

    gateway = FastAPI(title="Omnix Web Gateway")
    gateway_paths = {
        route_path
        for route in gateway.routes
        if (route_path := getattr(route, "path", None)) is not None
    }
    assert path in gateway_paths
    assert path not in gateway.openapi()["paths"]
