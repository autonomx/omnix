"""Atomic certified publication for durable World Forge runs."""
from __future__ import annotations

from typing import Any, Mapping

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .generation_compilation import compile_world_generation_certified_artifact
from .generation_publication import WorldGenerationPublication
from .generation_publication_transaction import (
    require_certified_publication,
    require_publication_run_ready,
)
from .lifecycle_service import require_world_writable
from .map_blueprint_authoring import (
    latest_ready_blueprint_requirements,
    materialize_generated_location_blueprints,
)
from .map_blueprint_publication import merge_authored_blueprints
from .service import compile_world_release
from .world_image_bindings import approved_world_asset_bindings


def _release_with_certification(
    publication: WorldGenerationPublication,
    *,
    certification: Mapping[str, Any],
) -> WorldGenerationPublication:
    release = publication.world_release
    rebuilt = compile_world_release(
        publication.world_revision,
        release=release.release,
        map_bindings=release.map_bindings,
        indexes=release.indexes,
        asset_bindings=release.asset_bindings,
        compiler_provenance=release.compiler_provenance,
        certification=certification,
        artifact_stage=release.artifact_stage,
        runtime_seed=release.runtime_seed,
        materialization=release.materialization,
        playtest_report=release.playtest_report,
    )
    return WorldGenerationPublication(
        world_revision=publication.world_revision,
        world_release=rebuilt,
        certification=dict(certification),
    )


def publish_certified_world_generation(
    run_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    """Persist a revision and release only after final certification passes."""

    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        run = work.world_generation.get(context, run_id)
        if run is None:
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        publication = dict(run.get("plan") or {}).get("publication")
        if isinstance(publication, Mapping):
            work.rollback()
            return {
                "ok": True,
                "status": "ready",
                "run": run,
                "publication": dict(publication),
                "reused": True,
            }

        require_publication_run_ready(run)
        world_id = str(run.get("world_id") or "")
        world = require_world_writable(work, context, world_id)
        topic_rows = work.world_generation.list_topics(
            context,
            world_id=world_id,
            draft_revision=int(run.get("draft_revision") or 1),
        )
        review_results = work.world_generation.list_topic_results(
            context,
            run_id=run_id,
        )
        current_row = work.connection.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM omnix_rpg_world_revisions "
            "WHERE workspace_id = %s AND world_id = %s",
            (context.workspace_id, world_id),
        ).fetchone()
        current_revision = int(current_row[0])
        asset_bindings = approved_world_asset_bindings(work, context, world_id)

        artifact = compile_world_generation_certified_artifact(
            run=run,
            world=world,
            topic_rows=topic_rows,
            review_results=review_results,
            revision=current_revision + 1,
            asset_bindings=asset_bindings,
        )
        compiled = artifact.publication
        require_certified_publication(run, artifact.certification)

        canon_entities = compiled.world_revision.canon.get("entities")
        materialization = dict(compiled.world_release.materialization)
        selected_locations = {
            str(materialization.get("hub_location_id") or ""),
            *(str(item) for item in materialization.get("sublocation_ids") or ()),
            *(str(item) for item in materialization.get("nearby_location_ids") or ()),
        }
        selected_locations.discard("")
        generated_locations = {
            str(entity_id): dict(entity)
            for entity_id, entity in dict(canon_entities or {}).items()
            if isinstance(entity, Mapping) and str(entity_id) in selected_locations
        }
        materialize_generated_location_blueprints(
            work,
            context,
            world_id,
            generated_locations,
        )
        requirements = latest_ready_blueprint_requirements(work, context, world_id)
        revision_document, release_document = merge_authored_blueprints(
            compiled.world_revision,
            compiled.world_release,
            requirements,
        )
        final_certification = {
            **dict(artifact.certification),
            "authored_map_blueprint_count": len(requirements),
        }
        compiled = _release_with_certification(
            WorldGenerationPublication(
                world_revision=revision_document,
                world_release=release_document,
                certification=final_certification,
            ),
            certification=final_certification,
        )
        require_certified_publication(run, compiled.certification)

        stored_revision = work.world_scenarios.publish_world_revision(
            context,
            world_id=world_id,
            document=compiled.world_revision.model_dump(mode="json"),
            content_hash=compiled.world_revision.content_hash,
            expected_revision=current_revision,
        )
        stored_release = work.world_scenarios.publish_world_release(
            context,
            world_id=world_id,
            world_revision=int(stored_revision["revision"]),
            document=compiled.world_release.model_dump(mode="json"),
            release_hash=compiled.world_release.release_hash,
        )
        publication_payload = {
            "world_id": world_id,
            "world_revision": int(stored_revision["revision"]),
            "world_revision_hash": str(stored_revision["content_hash"]),
            "world_release": int(stored_release["release"]),
            "world_release_hash": str(stored_release["release_hash"]),
            "artifact_stage": compiled.world_release.artifact_stage,
            "certification": dict(compiled.certification),
            "authored_map_blueprint_count": len(requirements),
            "approved_image_binding_count": len(asset_bindings),
        }
        plan = {**dict(run.get("plan") or {}), "publication": publication_payload}
        progress = {
            **dict(run.get("progress") or {}),
            "publication": publication_payload,
            "artifact_stage": compiled.world_release.artifact_stage,
            "percent": 100,
        }
        updated = work.world_generation.update(
            context,
            run_id=run_id,
            status="ready",
            plan=plan,
            progress=progress,
            error={},
        )
        work.commit()
    return {
        "ok": True,
        "status": "ready",
        "run": updated,
        "publication": publication_payload,
        "reused": False,
    }


__all__ = ["publish_certified_world_generation"]
