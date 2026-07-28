from __future__ import annotations

from typing import Any

import pytest

from app.rpg.worlds import generation_certified_publication as certified_publication
from app.rpg.worlds.contracts import canonical_content_hash
from app.rpg.worlds.generation_compilation import WorldGenerationCertifiedArtifact
from app.rpg.worlds.generation_publication import WorldGenerationPublication
from app.rpg.worlds.generation_publication_guard import publish_world_generation
from app.rpg.worlds.service import compile_world_release
from app.rpg.worlds.starter_bubble import (
    build_starter_bubble,
    build_starter_map_definitions,
    starter_bubble_certification,
)
from tests.persistence.test_rpg_world_generation_publication_integration import (
    _completed_generation,
    _database,
    _forced_launch_ready_artifact,
)


def _forced_starter_artifact(**kwargs: Any) -> WorldGenerationCertifiedArtifact:
    artifact = _forced_launch_ready_artifact(**kwargs)
    publication = artifact.publication
    revision = publication.world_revision
    plan = build_starter_bubble(
        world_id=revision.world_id,
        source_world_revision=revision.revision,
        starting_location_id="location:harbor",
        neighboring_location_id="location:ridge",
    )
    definitions = build_starter_map_definitions(
        plan,
        target_world_revision=revision.revision,
        definition_revisions={
            slot.map_id: revision.revision
            for slot in plan.map_slots()
            if slot.map_id
        },
    )
    native = starter_bubble_certification(plan, definitions)
    certificate = {
        "schema_version": "rpg_world_starter_bubble_release_v1",
        "contract_enabled": True,
        "skipped": False,
        "simulation_certified": True,
        "presentation_complete": False,
        "optional_art_blocks_gameplay": False,
        "plan": plan.model_dump(mode="json"),
        "map_definitions": [
            definition.model_dump(mode="json")
            for definition in definitions
        ],
        "native_certification": native,
        "component_statuses": {
            "starter_topology": True,
            "starter_region": True,
            "starter_core_locations": True,
            "starter_neighbor": True,
            "starter_neighbor_artifacts": True,
            "starting_market": True,
        },
        "component_reports": {},
        "starting_market": {
            "place_id": "location:harbor",
            "vendor_count": 1,
            "inventory_item_count": 1,
            "vendors": [
                {
                    "vendor_id": "actor:harbor-vendor",
                    "place_id": "location:harbor",
                    "inventory": [
                        {
                            "item_id": "item:ration",
                            "price": 12,
                            "quantity": 3,
                        }
                    ],
                }
            ],
        },
        "content_hash": "",
    }
    certificate["content_hash"] = canonical_content_hash(certificate)
    certification = {
        **dict(publication.certification),
        "starter_bubble_release": {
            "schema_version": "rpg_world_starter_bubble_release_report_v1",
            "passed": True,
            "issues": [],
            "materialization": certificate,
        },
    }
    source = publication.world_release
    release = compile_world_release(
        revision,
        release=source.release,
        map_bindings=source.map_bindings,
        indexes=source.indexes,
        asset_bindings=source.asset_bindings,
        compiler_provenance=source.compiler_provenance,
        certification=certification,
        artifact_stage=source.artifact_stage,
        runtime_seed=source.runtime_seed,
        materialization=source.materialization,
        playtest_report=source.playtest_report,
    )
    return WorldGenerationCertifiedArtifact(
        publication=WorldGenerationPublication(
            world_revision=revision,
            world_release=release,
            certification=certification,
        )
    )


def test_certified_publication_persists_starter_maps_and_exact_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database()
    try:
        context, started = _completed_generation(database)
        monkeypatch.setattr(
            certified_publication,
            "compile_world_generation_certified_artifact",
            _forced_starter_artifact,
        )

        published = publish_world_generation(started["run_id"], database=database)
        repeated = publish_world_generation(started["run_id"], database=database)

        assert published["status"] == "ready"
        assert published["publication"]["starter_map_definition_count"] == 3
        assert published["publication"]["starter_map_binding_count"] == 3
        assert repeated["reused"] is True
        assert repeated["publication"] == published["publication"]

        with database.transaction() as connection:
            definition_rows = connection.execute(
                "SELECT map_id, definition_revision, world_revision, "
                "definition_hash, semantic_interface_hash "
                "FROM omnix_rpg_map_definitions "
                "WHERE workspace_id = %s AND world_id = %s "
                "ORDER BY map_id",
                (context.workspace_id, "world:publication"),
            ).fetchall()
        with certified_publication.unit_of_work(database) as work:
            revision = work.world_scenarios.get_world_revision(
                context,
                "world:publication",
                1,
            )
            release = work.world_scenarios.get_world_release(
                context,
                "world:publication",
                1,
                1,
            )
            work.rollback()

        assert revision is not None
        assert release is not None
        assert len(definition_rows) == 3
        assert all(int(row[1]) == 1 and int(row[2]) == 1 for row in definition_rows)
        assert revision["document"]["topology"]["starter_bubble"][
            "starting_location_id"
        ] == "location:harbor"
        bindings = release["document"]["map_bindings"]
        assert len(bindings) == 3
        stored_by_map = {
            str(row[0]): {
                "definition_revision": int(row[1]),
                "definition_hash": str(row[3]),
                "semantic_interface_hash": str(row[4]),
            }
            for row in definition_rows
        }
        for binding in bindings:
            stored = stored_by_map[binding["map_id"]]
            assert binding["definition_revision"] == stored["definition_revision"]
            assert binding["definition_hash"] == stored["definition_hash"]
            assert (
                binding["semantic_interface_hash"]
                == stored["semantic_interface_hash"]
            )
        indexes = release["document"]["indexes"]
        assert indexes["starter_bubble"]["starting_location_id"] == "location:harbor"
        assert indexes["predictive_materialization"]
        assert indexes["starting_market"]["vendor_count"] == 1
        certification = release["document"]["certification"]
        assert certification["starter_bubble_publication"]["passed"] is True
        assert certification["starter_map_definition_count"] == 3
    finally:
        database.close()
