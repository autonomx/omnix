from fastapi import FastAPI

from app.gateway.rpg_world_routes import register_rpg_world_routes
from app.rpg.worlds.map_blueprint_authoring import (
    MapBlueprintDocument,
    generated_location_blueprint_documents,
    reconcile_blueprint_scenarios,
)
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_revision,
)
from app.rpg.worlds.contracts import MapInitializationOperation


def test_world_routes_register_map_blueprint_authoring_endpoints() -> None:
    app = FastAPI()
    register_rpg_world_routes(app)
    paths = {route.path for route in app.routes}

    assert "/api/rpg/worlds/{world_id}/map-blueprints" in paths
    assert "/api/rpg/worlds/{world_id}/map-blueprints/materialize" in paths
    assert "/api/rpg/worlds/{world_id}/map-blueprints/{map_id}" in paths


def test_generated_locations_receive_safe_baseline_blueprints() -> None:
    documents = generated_location_blueprint_documents(
        {
            "location:ruined_vault": {
                "name": "Ruined Vault",
                "description": "A sealed vault beneath the wasteland.",
            },
            "location:market": {"name": "Market"},
        }
    )

    by_location = {document.location_id: document for document in documents}
    assert by_location["location:ruined_vault"].map_id == "map:location:ruined_vault"
    assert by_location["location:ruined_vault"].level == "dungeon"
    assert by_location["location:market"].level == "settlement"
    assert by_location["location:market"].required_spawn_point_ids == ("spawn:arrival",)
    assert by_location["location:market"].required_zone_ids == ("zone:main",)


def test_blueprint_reconciliation_reports_scenario_semantic_ids() -> None:
    world = compile_world_revision(
        world_id="world:route-proof",
        revision=1,
        title="Route Proof",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:harbor"], "routes": []},
    )
    scenario = compile_scenario_revision(
        scenario_id="scenario:route-proof",
        revision=1,
        world_revision=world,
        starting_location_id="location:harbor",
        map_initialization=(
            MapInitializationOperation(
                operation_id="init:actor",
                map_id="map:harbor",
                type="place_actor",
                target_id="npc:captain",
                payload={"spawn_point_id": "spawn:office"},
            ),
            MapInitializationOperation(
                operation_id="init:gate",
                map_id="map:harbor",
                type="set_object_state",
                target_id="gate:eastern",
                payload={"state": "closed"},
            ),
        ),
    )
    findings = reconcile_blueprint_scenarios(
        MapBlueprintDocument(
            map_id="map:harbor",
            location_id="location:harbor",
            level="settlement",
            required_spawn_point_ids=("spawn:arrival",),
        ),
        (scenario,),
    )

    assert [(row["code"], row["target_id"]) for row in findings] == [
        ("scenario_spawn_missing", "spawn:office"),
        ("scenario_object_missing", "gate:eastern"),
    ]
