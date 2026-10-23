"""A shared world imported from a bundle launches only after someone here adopts it (PostgreSQL)."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

_AURELIA = Path(__file__).resolve().parents[3] / "resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate"


def _aurelia_bundle() -> bytes:
    spec = importlib.util.spec_from_file_location("aurelia_materialize", _AURELIA / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_bundle(_AURELIA)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=120_000,
            application_name="omnix-shared-world-adoption",
        )
    )


def _latest_opening(database: PostgresDatabase, world_id: str) -> dict:
    with unit_of_work(database) as work:
        context = current_tenant()
        scenario = next(iter(work.world_library.iter_scenarios(context, world_id=world_id)))
        latest = work.world_library.list_scenario_revisions(context, str(scenario["id"]))[0]
        work.rollback()
    document = dict(latest["document"])
    return {
        "world_id": world_id,
        "world_revision": int(document["world_revision"]),
        "world_release": int(document["compatible_release"]),
        "scenario_id": str(document["scenario_id"]),
        "scenario_revision": int(document["revision"]),
    }


def test_imported_world_launches_only_after_it_is_adopted(tmp_path, monkeypatch) -> None:
    from app.apps.rpg.genesis.worlds.authoring_service import update_world_metadata
    from app.apps.rpg.genesis.worlds.launch_repair_service import (
        prepare_opening_scenarios_for_launch,
        repair_world_for_launch,
    )
    from app.apps.rpg.genesis.worlds.postgres_service import load_published_resources, load_release_definitions
    from app.apps.rpg.genesis.worlds.semantic_validation import validate_scenario_against_release
    from app.apps.rpg.genesis.worlds.world_adoption import adopt_shared_world
    from app.apps.rpg.genesis.worlds.world_bundle_import import import_world_bundle

    monkeypatch.setenv("OMNIX_RESOURCES_DIR", str(tmp_path))
    database = _database()
    world_id = f"world:adoption-check-{os.getpid()}-{tmp_path.name[-6:]}"
    try:
        imported = import_world_bundle(_aurelia_bundle(), target_world_id=world_id, database=database)
        assert imported["launch_preparation"] == {"status": "adoption_required"}
        opening = _latest_opening(database, world_id)
        with pytest.raises(ValueError, match="world_revision_authorship_untrusted"):
            load_published_resources(**opening, database=database)
        # Nor can its openings be prepared or repaired into launchable ones before it is adopted.
        with pytest.raises(ValueError, match="world_adoption_required"):
            prepare_opening_scenarios_for_launch(world_id, database=database)
        with pytest.raises(ValueError, match="world_adoption_required"):
            repair_world_for_launch(
                world_id,
                scenario_id=opening["scenario_id"],
                starting_location_id="location:aurelia:arrival-grove",
                database=database,
            )

        # A metadata edit cannot claim an adoption: only adopting writes that record.
        with unit_of_work(database) as work:
            draft_revision = int(work.world_scenarios.get_world(current_tenant(), world_id)["draft_revision"])
            work.rollback()
        edited = update_world_metadata(
            world_id,
            expected_draft_revision=draft_revision,
            changes={"metadata": {"world_adoption": {"bundle_sha256": imported["bundle_sha256"]}, "note": "kept"}},
            database=database,
        )["world"]
        assert "world_adoption" not in edited["metadata"] and edited["metadata"]["note"] == "kept"
        assert edited["metadata"]["world_bundle_import"]["bundle_sha256"] == imported["bundle_sha256"]

        with pytest.raises(ValueError, match="world_adoption_bundle_mismatch"):
            adopt_shared_world(world_id, bundle_sha256="0" * 64, database=database)

        adopted = adopt_shared_world(world_id, bundle_sha256=imported["bundle_sha256"], database=database)
        assert adopted["status"] == "adopted" and adopted["launch_ready"] is True
        assert len(adopted["openings"]) == 3

        opening = _latest_opening(database, world_id)
        assert opening["world_revision"] == adopted["world_revision"]
        revision, release, scenario = load_published_resources(**opening, database=database)
        assert revision.provenance["adoption"]["bundle_sha256"] == imported["bundle_sha256"]
        assert release.certification["authorship_source"] == "adopted_shared_world"
        definitions = load_release_definitions(revision, release, database=database)
        assert validate_scenario_against_release(scenario, release, definitions).map_id

        again = adopt_shared_world(world_id, bundle_sha256=imported["bundle_sha256"], database=database)
        assert again["reused"] is True
    finally:
        database.close()
