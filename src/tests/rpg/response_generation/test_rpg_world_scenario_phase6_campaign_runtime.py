from __future__ import annotations

from fastapi import FastAPI

from app.gateway.rpg_npc_spatial_routes import register_rpg_npc_spatial_routes
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    GridPortal,
    GridPortalEndpoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import create_map_instance_snapshot
from app.rpg.npc_spatial_campaign_contracts import (
    CampaignNpcSpatialRoutine,
    NpcSpatialRoutineStep,
)
from app.rpg.npc_spatial_transition import (
    replay_npc_spatial_map_events,
    resolve_portal_transition,
)


def _definitions() -> tuple[GridMapDefinition, GridMapDefinition]:
    source = with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:tavern",
            level="interior",
            definition_revision=1,
            world_id="world:spatial",
            world_revision=1,
            width=3,
            height=3,
            terrain_palette=(TerrainRule(code=".", terrain_id="floor"),),
            terrain_rows=("...", "...", "..."),
            portals=(
                GridPortal(
                    portal_id="portal:tavern-road",
                    source=GridPortalEndpoint(map_id="map:tavern", cell=(2, 1)),
                    target=GridPortalEndpoint(map_id="map:road", cell=(0, 1)),
                ),
            ),
        )
    )
    target = with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:road",
            level="encounter",
            definition_revision=1,
            world_id="world:spatial",
            world_revision=1,
            width=3,
            height=3,
            terrain_palette=(TerrainRule(code=".", terrain_id="road"),),
            terrain_rows=("...", "...", "..."),
        )
    )
    return source, target


def test_portal_transfer_replays_independently_on_both_map_streams() -> None:
    source_definition, target_definition = _definitions()
    source = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:tavern",
        campaign_id="campaign:a",
        location_id="location:tavern",
        definition=source_definition,
        actors=(GridActorPlacement(actor_id="npc:bran", cell=(2, 1)),),
    )
    target = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:road",
        campaign_id="campaign:a",
        location_id="location:road",
        definition=target_definition,
    )

    exit_event, enter_event, source_after, target_after = resolve_portal_transition(
        source_definition,
        source,
        target_definition,
        target,
        actor_id="npc:bran",
        portal_id="portal:tavern-road",
        transition_id="transition:1",
    )

    assert source_after.actors == ()
    assert target_after.actor("npc:bran").cell == (0, 1)
    assert replay_npc_spatial_map_events(source, (exit_event,)) == source_after
    assert replay_npc_spatial_map_events(target, (enter_event,)) == target_after
    assert exit_event.transition_id == enter_event.transition_id == "transition:1"


def test_routine_emits_deterministic_cross_map_goal_and_routes_are_hidden() -> None:
    routine = CampaignNpcSpatialRoutine(
        routine_id="routine:bran-evening",
        campaign_id="campaign:a",
        actor_id="npc:bran",
        interval_ticks=10,
        emission_count=2,
        steps=(
            NpcSpatialRoutineStep(
                step_id="leave-tavern",
                map_instance_id="campaign:a:map:tavern",
                goal_type="transition_via_portal",
                portal_id="portal:tavern-road",
                target_map_instance_id="campaign:a:map:road",
                priority=7,
            ),
        ),
    )

    goal = routine.emitted_goal(30)
    assert goal.goal_id == (
        "routine:routine:bran-evening:emission:3:step:leave-tavern"
    )
    assert goal.issued_tick == 30
    assert goal.goal_type == "transition_via_portal"

    app = FastAPI()
    register_rpg_npc_spatial_routes(app)
    paths = {route.path for route in app.routes}
    expected = {
        "/api/rpg/campaigns/{campaign_id}/spatial-goals",
        "/api/rpg/campaigns/{campaign_id}/spatial-routines",
        "/api/rpg/campaigns/{campaign_id}/spatial-policy",
        "/api/rpg/campaigns/{campaign_id}/spatial-ticks",
        "/api/rpg/campaigns/{campaign_id}/spatial-state",
    }
    assert expected <= paths
    assert expected.isdisjoint(app.openapi()["paths"])
