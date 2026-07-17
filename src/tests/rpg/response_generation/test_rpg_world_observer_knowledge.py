from __future__ import annotations

from fastapi import FastAPI

from app.gateway.rpg_observer_routes import register_rpg_observer_routes
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    GridPortal,
    GridPortalEndpoint,
    GridSpawnPoint,
    GridZone,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import create_map_instance_snapshot
from app.rpg.map_observer_runtime import (
    ObserverPerceptionPolicy,
    has_line_of_sight,
    observe_map,
    project_observer_knowledge,
)


def _definition() -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:observer",
            level="interior",
            definition_revision=1,
            world_id="world:observer",
            world_revision=1,
            width=7,
            height=5,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor"),
                TerrainRule(
                    code="#",
                    terrain_id="wall",
                    walkable=False,
                    blocks_sight=True,
                ),
            ),
            terrain_rows=(
                "...#...",
                "...#...",
                "...#...",
                "...#...",
                ".......",
            ),
            portals=(
                GridPortal(
                    portal_id="portal:secret",
                    source=GridPortalEndpoint(map_id="map:observer", cell=(2, 1)),
                    target=GridPortalEndpoint(map_id="map:elsewhere", cell=(0, 0)),
                    secret=True,
                ),
            ),
            spawn_points=(
                GridSpawnPoint(
                    spawn_point_id="spawn:secret",
                    cell=(2, 3),
                    secret=True,
                ),
            ),
            zones=(
                GridZone(
                    zone_id="zone:secret",
                    name="Secret Zone",
                    cells=((2, 4),),
                    secret=True,
                ),
            ),
        )
    )


def test_observer_los_detection_memory_and_masked_projection() -> None:
    definition = _definition()
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:observer",
        campaign_id="campaign:a",
        location_id="location:observer",
        definition=definition,
        actors=(
            GridActorPlacement(actor_id="player:a", cell=(1, 2)),
            GridActorPlacement(actor_id="npc:near-hidden", cell=(2, 2), hidden=True),
            GridActorPlacement(actor_id="npc:far-hidden", cell=(5, 2), hidden=True),
            GridActorPlacement(actor_id="npc:visible", cell=(2, 0)),
        ),
    ).model_copy(update={"hazard_states": {"hazard:trap": {"armed": True}}})

    assert has_line_of_sight(definition, (1, 2), (2, 2)) is True
    assert has_line_of_sight(definition, (1, 2), (5, 2)) is False
    first, event = observe_map(
        definition,
        snapshot,
        observer_actor_id="player:a",
        policy=ObserverPerceptionPolicy(sight_radius=6, detection_radius=2),
    )

    assert first.detected_actor_ids == (
        "npc:near-hidden",
        "npc:visible",
        "player:a",
    )
    assert first.known_portal_ids == ("portal:secret",)
    assert first.known_spawn_point_ids == ("spawn:secret",)
    assert first.known_zone_ids == ("zone:secret",)
    assert "npc:far-hidden" not in event.detected_actor_ids

    moved = snapshot.model_copy(
        update={
            "actors": tuple(
                actor.model_copy(update={"cell": (5, 4)})
                if actor.actor_id == "player:a"
                else actor
                for actor in snapshot.actors
            ),
            "map_state_revision": 1,
        }
    )
    second, _ = observe_map(
        definition,
        moved,
        observer_actor_id="player:a",
        previous=first,
    )
    projection = project_observer_knowledge(definition, moved, second)

    assert set(first.known_cells) < set(second.known_cells)
    assert second.known_portal_ids == ("portal:secret",)
    assert "npc:near-hidden" not in {actor["actor_id"] for actor in projection["actors"]}
    assert "npc:far-hidden" in {actor["actor_id"] for actor in projection["actors"]}
    assert any("?" in row for row in projection["grid"]["terrain_rows"])
    assert "hazard_states" not in projection
    assert projection["object_states"] == {}


def test_observer_routes_are_hidden() -> None:
    app = FastAPI()
    register_rpg_observer_routes(app)
    expected = {
        "/api/rpg/map-instances/{map_instance_id}/observers/{observer_actor_id}/observe",
        "/api/rpg/map-instances/{map_instance_id}/observers/{observer_actor_id}/projection",
    }
    paths = {route.path for route in app.routes}
    assert expected <= paths
    assert expected.isdisjoint(app.openapi()["paths"])
