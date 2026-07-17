from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import FastAPI

from app.gateway.rpg_world_bundle_routes import register_rpg_world_bundle_routes
from app.rpg.map_grid_contracts import (
    GridMapDefinition,
    GridSpawnPoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.worlds.contracts import MapDefinitionBinding
from app.rpg.worlds.map_blueprint_authoring import MapBlueprintDocument
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
)
from app.rpg.worlds.world_bundle import (
    WORLD_BUNDLE_DATA_PATH,
    WORLD_BUNDLE_MANIFEST_PATH,
    WorldBundleAsset,
    WorldBundlePayload,
    build_world_bundle_archive,
    parse_world_bundle_archive,
    sha256_hex,
)
from app.rpg.worlds.world_bundle_transform import transform_world_bundle


def _definition() -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:harbor",
            level="settlement",
            definition_revision=1,
            world_id="world:source",
            world_revision=1,
            width=3,
            height=3,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor"),
            ),
            terrain_rows=("...", "...", "..."),
            spawn_points=(
                GridSpawnPoint(
                    spawn_point_id="spawn:arrival",
                    cell=(1, 1),
                    tags=("player", "arrival"),
                ),
            ),
            metadata={
                "location_id": "location:harbor",
                "background_asset_id": "image:harbor",
            },
        )
    )


def _payload() -> WorldBundlePayload:
    definition = _definition()
    blueprint = MapBlueprintDocument(
        map_id=definition.map_id,
        location_id="location:harbor",
        level="settlement",
        required_spawn_point_ids=("spawn:arrival",),
        metadata={"background_asset_id": "image:harbor"},
    )
    world = compile_world_revision(
        world_id="world:source",
        revision=1,
        title="Portable Harbor",
        canon={"portrait_asset_id": "image:harbor"},
        entity_manifest={},
        topology={"locations": ["location:harbor"]},
        blueprint_requirements=(
            blueprint.requirement(
                blueprint_revision=1,
                content_hash="sha256:blueprint-source",
                semantic_interface_hash="sha256:semantic-source",
            ),
        ),
    )
    release = compile_world_release(
        world,
        release=1,
        map_bindings=(
            MapDefinitionBinding(
                map_id=definition.map_id,
                blueprint_revision=1,
                definition_revision=1,
                definition_hash=definition.definition_hash,
                semantic_interface_hash=definition.semantic_interface_hash,
            ),
        ),
        certification={"launch_ready": True, "missing_requirements": []},
    )
    scenario = compile_scenario_revision(
        scenario_id="scenario:opening",
        revision=1,
        world_revision=world,
        compatible_release=1,
        starting_location_id="location:harbor",
    )
    return WorldBundlePayload(
        world={
            "id": "world:source",
            "title": "Portable Harbor",
            "description": "Exportable test world",
            "status": "published",
            "source_mode": "hybrid",
            "genre": "fantasy",
            "tone": "bright",
            "seed": 7,
            "draft_revision": 2,
            "metadata": {"thumbnail_asset_id": "image:harbor"},
        },
        topics=(
            {
                "topic_id": "realm",
                "draft_revision": 1,
                "source": "manual",
                "status": "ready",
                "content": {"image_asset_id": "image:harbor"},
                "directives": {},
                "dependency_hashes": {},
                "input_hash": "sha256:old-input",
                "content_hash": "sha256:old-content",
                "provenance": {},
            },
        ),
        map_blueprints=(
            {
                "map_id": blueprint.map_id,
                "blueprint_revision": 1,
                "document": blueprint.model_dump(mode="json"),
                "content_hash": "sha256:blueprint-source",
                "semantic_interface_hash": "sha256:semantic-source",
                "status": "ready",
                "findings": [],
            },
        ),
        world_revisions=(
            {
                "revision": 1,
                "document": world.model_dump(mode="json"),
                "content_hash": world.content_hash,
            },
        ),
        map_definitions=(
            {
                "map_id": definition.map_id,
                "definition_revision": 1,
                "world_revision": 1,
                "document": definition.model_dump(mode="json"),
                "definition_hash": definition.definition_hash,
                "semantic_interface_hash": definition.semantic_interface_hash,
            },
        ),
        world_releases=(
            {
                "world_revision": 1,
                "release": 1,
                "document": release.model_dump(mode="json"),
                "release_hash": release.release_hash,
            },
        ),
        scenarios=(
            {
                "id": "scenario:opening",
                "title": "Opening",
                "description": "At the harbor",
                "status": "published",
                "metadata": {},
            },
        ),
        scenario_revisions=(
            {
                "scenario_id": "scenario:opening",
                "revision": 1,
                "world_revision": 1,
                "document": scenario.model_dump(mode="json"),
                "content_hash": scenario.content_hash,
            },
        ),
    )


def test_world_bundle_round_trip_and_clone_hash_rebuild() -> None:
    image = b"\x89PNG\r\nportable-world-image"
    descriptor = WorldBundleAsset(
        asset_id="image:harbor",
        archive_path="assets/image-harbor.png",
        module="image-generation",
        mime_type="image/png",
        byte_size=len(image),
        checksum_sha256=sha256_hex(image),
        metadata={"world_id": "world:source", "map_id": "map:harbor"},
    )
    archive = build_world_bundle_archive(
        _payload(),
        [(descriptor, image)],
        exported_at="2026-07-17T00:00:00+00:00",
    )
    parsed = parse_world_bundle_archive(archive.content)

    assert archive.filename == "world-source.omnix-world.zip"
    assert parsed.asset_bytes == {"image:harbor": image}
    assert parsed.manifest.source_world_id == "world:source"

    transformed = transform_world_bundle(
        parsed.payload,
        target_world_id="world:clone",
        bundle_sha256=parsed.bundle_sha256,
        existing_map_ids={"map:harbor"},
        existing_scenario_ids={"scenario:opening"},
        existing_asset_ids={"image:harbor"},
    )
    payload = transformed.payload
    cloned_map = payload.map_definitions[0]
    cloned_release = payload.world_releases[0]
    cloned_scenario = payload.scenario_revisions[0]

    assert payload.world["id"] == "world:clone"
    assert cloned_map["map_id"] != "map:harbor"
    assert cloned_map["document"]["world_id"] == "world:clone"
    assert cloned_release["document"]["world_revision_hash"] == (
        payload.world_revisions[0]["content_hash"]
    )
    assert cloned_release["document"]["map_bindings"][0]["definition_hash"] == (
        cloned_map["definition_hash"]
    )
    assert cloned_scenario["document"]["scenario_id"] != "scenario:opening"
    assert cloned_scenario["document"]["world_id"] == "world:clone"
    assert payload.topics[0]["content"]["image_asset_id"] != "image:harbor"
    assert payload.world_revisions[0]["content_hash"].startswith("sha256:")
    assert cloned_release["release_hash"].startswith("sha256:")
    assert cloned_scenario["content_hash"].startswith("sha256:")


def test_world_bundle_rejects_unsafe_asset_path_and_bad_checksum() -> None:
    image = b"portable-image"
    with pytest.raises(ValueError, match="world_bundle_archive_path_invalid"):
        WorldBundleAsset(
            asset_id="image:unsafe",
            archive_path="../escape.png",
            module="image-generation",
            mime_type="image/png",
            byte_size=len(image),
            checksum_sha256=sha256_hex(image),
        )

    archive = build_world_bundle_archive(_payload(), [])
    with zipfile.ZipFile(io.BytesIO(archive.content), mode="r") as source:
        manifest = json.loads(source.read(WORLD_BUNDLE_MANIFEST_PATH))
    manifest["data_sha256"] = "0" * 64
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as target:
        target.writestr(WORLD_BUNDLE_MANIFEST_PATH, json.dumps(manifest))
        target.writestr(WORLD_BUNDLE_DATA_PATH, b"{}")
    with pytest.raises(ValueError, match="world_bundle_data_checksum_mismatch"):
        parse_world_bundle_archive(output.getvalue())


def test_world_bundle_routes_are_hidden_and_registered_once() -> None:
    app = FastAPI()
    register_rpg_world_bundle_routes(app)
    register_rpg_world_bundle_routes(app)

    paths = [getattr(route, "path", "") for route in app.routes]
    assert paths.count("/api/rpg/worlds/{world_id}/export") == 1
    assert paths.count("/api/rpg/worlds/import") == 1
    assert "/api/rpg/worlds/{world_id}/export" not in app.openapi()["paths"]
    assert "/api/rpg/worlds/import" not in app.openapi()["paths"]
