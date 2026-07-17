from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.map_grid_contracts import (
    GridMapDefinition,
    GridSpawnPoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.worlds.contracts import (
    MapDefinitionBinding,
    ScenarioProjectCreate,
    WorldProjectCreate,
)
from app.rpg.worlds.library_service import read_world_detail, save_world_topic
from app.rpg.worlds.map_blueprint_authoring import (
    MapBlueprintDocument,
    save_map_blueprint,
)
from app.rpg.worlds.postgres_service import (
    create_scenario_project,
    create_world_project,
    publish_scenario_revision,
    publish_world_release,
    publish_world_revision,
)
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
)
from app.rpg.worlds.world_bundle_export import export_world_bundle
from app.rpg.worlds.world_bundle_import import (
    WorldBundleImportConflict,
    import_world_bundle,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-world-bundle",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_map_blueprint_revisions, "
            "omnix_rpg_world_topic_history, omnix_rpg_world_generation_runs, "
            "omnix_rpg_campaign_map_events, omnix_rpg_campaign_map_instances, "
            "omnix_rpg_map_definitions, omnix_rpg_campaign_world_bindings, "
            "omnix_rpg_scenario_revisions, omnix_rpg_scenarios, "
            "omnix_rpg_world_releases, omnix_rpg_world_revisions, "
            "omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _definition(world_id: str, *, asset_id: str) -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:portable-harbor",
            level="settlement",
            definition_revision=1,
            world_id=world_id,
            world_revision=1,
            width=4,
            height=3,
            terrain_palette=(TerrainRule(code=".", terrain_id="stone"),),
            terrain_rows=("....", "....", "...."),
            spawn_points=(
                GridSpawnPoint(
                    spawn_point_id="spawn:arrival",
                    cell=(1, 1),
                    tags=("player", "arrival"),
                ),
            ),
            metadata={
                "location_id": "location:portable-harbor",
                "background_asset_id": asset_id,
            },
        )
    )


def test_world_bundle_exports_and_imports_world_maps_scenarios_and_images(tmp_path) -> None:
    database = _database()
    asset_store = SharedAssetStore(
        manifest_path=tmp_path / "asset-store" / "manifest.json"
    )
    source_world_id = "world:portable-source"
    target_world_id = "world:portable-clone"
    source_asset_id = "image:portable-harbor"
    image_bytes = b"\x89PNG\r\nworld-bundle-round-trip"
    image_path = tmp_path / "portable-harbor.png"
    image_path.write_bytes(image_bytes)

    try:
        _reset(database)
        create_world_project(
            WorldProjectCreate(
                world_id=source_world_id,
                title="Portable Harbor",
                source_mode="hybrid",
                metadata={
                    "campaign_template": "harbor_adventure",
                    "thumbnail_asset_id": source_asset_id,
                },
            ),
            database=database,
        )
        save_world_topic(
            source_world_id,
            topic_id="realm",
            content={
                "topic_id": "realm",
                "facts": ["The harbor survives the storm."],
                "image_asset_id": source_asset_id,
            },
            database=database,
        )
        blueprint = save_map_blueprint(
            source_world_id,
            MapBlueprintDocument(
                map_id="map:portable-harbor",
                location_id="location:portable-harbor",
                level="settlement",
                required_spawn_point_ids=("spawn:arrival",),
                metadata={"background_asset_id": source_asset_id},
            ),
            expected_revision=0,
            database=database,
        )["map_blueprint"]
        world = compile_world_revision(
            world_id=source_world_id,
            revision=1,
            title="Portable Harbor",
            canon={"thumbnail_asset_id": source_asset_id},
            entity_manifest={},
            topology={"locations": ["location:portable-harbor"]},
            blueprint_requirements=(
                {
                    "map_id": "map:portable-harbor",
                    "location_id": "location:portable-harbor",
                    "level": "settlement",
                    "navigation_kind": "square_grid",
                    "blueprint_revision": 1,
                    "blueprint_hash": blueprint["content_hash"],
                    "semantic_interface_hash": blueprint["semantic_interface_hash"],
                    "required_spawn_point_ids": ["spawn:arrival"],
                    "simulation_readiness": "certified",
                    "presentation_readiness": "ready",
                },
            ),
        )
        publish_world_revision(world, expected_revision=0, database=database)
        definition = _definition(source_world_id, asset_id=source_asset_id)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.map_instances.put_definition(
                context,
                map_id=definition.map_id,
                definition_revision=definition.definition_revision,
                world_id=source_world_id,
                world_revision=1,
                document=definition.model_dump(mode="json"),
                definition_hash=definition.definition_hash,
                semantic_interface_hash=definition.semantic_interface_hash,
            )
            work.commit()
        release = compile_world_release(
            world,
            release=1,
            map_bindings=(
                MapDefinitionBinding(
                    map_id=definition.map_id,
                    blueprint_revision=1,
                    definition_revision=definition.definition_revision,
                    definition_hash=definition.definition_hash,
                    semantic_interface_hash=definition.semantic_interface_hash,
                    simulation_readiness="certified",
                    presentation_readiness="ready",
                ),
            ),
            asset_bindings={"harbor": source_asset_id},
            certification={"launch_ready": True, "missing_requirements": []},
        )
        publish_world_release(release, database=database)
        create_scenario_project(
            ScenarioProjectCreate(
                scenario_id="scenario:portable-opening",
                world_id=source_world_id,
                title="Portable Opening",
            ),
            database=database,
        )
        scenario = compile_scenario_revision(
            scenario_id="scenario:portable-opening",
            revision=1,
            world_revision=world,
            compatible_release=1,
            starting_location_id="location:portable-harbor",
        )
        publish_scenario_revision(scenario, database=database)
        asset_store.upsert_asset(
            AssetRecord(
                id=source_asset_id,
                module="image-generation",
                type=AssetType.IMAGE,
                mime_type="image/png",
                storage_path=str(image_path),
                source_job_id="job:portable-image",
                created_at=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "world_id": source_world_id,
                    "map_id": definition.map_id,
                    "title": "Portable Harbor",
                },
                compat={"contract": "image_generation_asset_v1"},
            )
        )

        bundle = export_world_bundle(
            source_world_id,
            database=database,
            asset_store=asset_store,
        )
        result = import_world_bundle(
            bundle.content,
            target_world_id=target_world_id,
            database=database,
            asset_store=asset_store,
        )

        assert result["status"] == "imported"
        assert result["counts"]["topics"] == 1
        assert result["counts"]["topic_history"] == 1
        assert result["counts"]["map_blueprints"] == 1
        assert result["counts"]["map_definitions"] == 1
        assert result["counts"]["world_releases"] == 1
        assert result["counts"]["scenarios"] == 1
        assert result["counts"]["scenario_revisions"] == 1
        assert result["counts"]["images_created"] == 1

        source_detail = read_world_detail(source_world_id, database=database)
        clone_detail = read_world_detail(target_world_id, database=database)
        assert source_detail["world"]["title"] == "Portable Harbor"
        assert clone_detail["world"]["title"] == "Portable Harbor"
        assert clone_detail["topics"][0]["content"]["image_asset_id"] != source_asset_id
        assert clone_detail["map_blueprints"][0]["map_id"] != definition.map_id
        assert clone_detail["releases"][0]["release_hash"].startswith("sha256:")
        assert clone_detail["scenario_revisions"]

        cloned_asset_id = result["identifier_map"][source_asset_id]
        cloned_asset = asset_store.get_asset(cloned_asset_id)
        assert cloned_asset is not None
        assert cloned_asset.metadata["world_bundle_import"]["target_world_id"] == target_world_id
        assert open(cloned_asset.storage_path, "rb").read() == image_bytes

        with unit_of_work(database) as work:
            imported_maps = work.connection.execute(
                "SELECT map_id, document_jsonb FROM omnix_rpg_map_definitions "
                "WHERE workspace_id = %s AND world_id = %s",
                (context.workspace_id, target_world_id),
            ).fetchall()
            source_count = work.connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_worlds WHERE workspace_id = %s "
                "AND id IN (%s, %s)",
                (context.workspace_id, source_world_id, target_world_id),
            ).fetchone()
            work.rollback()
        assert len(imported_maps) == 1
        assert imported_maps[0][1]["world_id"] == target_world_id
        assert int(source_count[0]) == 2

        before_assets = {asset.id for asset in asset_store.list_assets().assets}
        with pytest.raises(WorldBundleImportConflict, match="world_bundle_target_exists"):
            import_world_bundle(
                bundle.content,
                target_world_id=target_world_id,
                database=database,
                asset_store=asset_store,
            )
        assert {asset.id for asset in asset_store.list_assets().assets} == before_assets
    finally:
        database.close()
