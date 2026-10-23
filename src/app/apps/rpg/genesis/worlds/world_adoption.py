"""Adopting a shared world: a person's explicit acceptance of an imported world before it can be played.

An imported bundle carries authorship evidence signed by the install that made it, which this install cannot verify,
so its releases are refused at launch. Adoption is the deliberate step that changes that: the person who reviewed the
world accepts the exact bundle they imported (named by its SHA-256), and Omnix republishes the imported release as a
new revision under that person's authorship record. The canon, maps and openings are carried forward unchanged and
every release and scenario check still runs; only the authorship evidence is new, and it names the adoption.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

from app.apps.rpg.world.map_grid_contracts import GridMapDefinition, with_grid_definition_hashes

from .contracts import (
    MapDefinitionBinding,
    ScenarioRevisionDocument,
    WorldReleaseDocument,
    WorldRevisionDocument,
    canonical_content_hash,
)
from .lifecycle_service import require_world_writable
from .postgres_service import _definitions_from_work, _ensure_hash
from .semantic_validation import certify_world_release, validate_scenario_against_release
from .service import compile_world_release, compile_world_revision

ADOPTION_SCHEMA = "rpg_shared_world_adoption_v1"
ADOPTION_AUTHORSHIP_SOURCE = "adopted_shared_world"


def shared_world_state(world: Mapping[str, Any]) -> dict[str, Any]:
    """Whether a world came from a bundle, and whether someone here has adopted it."""

    metadata = dict(world.get("metadata") or {})
    imported = dict(metadata.get("world_bundle_import") or {})
    adoption = dict(metadata.get("world_adoption") or {})
    return {
        "shared": bool(imported.get("bundle_sha256")),
        "bundle_sha256": str(imported.get("bundle_sha256") or ""),
        "source_world_id": str(imported.get("source_world_id") or ""),
        "catalog": dict(imported.get("catalog") or {}),
        "adopted": bool(adoption),
        "adoption": adoption,
    }


def require_adopted_if_shared(world: Mapping[str, Any]) -> None:
    """Refuse to prepare or launch a world made elsewhere until someone here has adopted it."""

    state = shared_world_state(world)
    if state["shared"] and not state["adopted"]:
        raise ValueError(f"world_adoption_required:{world.get('id')}")


def _latest_release(work: Any, context: Any, world_id: str) -> tuple[WorldRevisionDocument, WorldReleaseDocument] | None:
    row = work.connection.execute(
        "SELECT world_revision, release FROM omnix_rpg_world_releases WHERE workspace_id = %s AND world_id = %s "
        "ORDER BY world_revision DESC, release DESC LIMIT 1",
        (context.workspace_id, world_id),
    ).fetchone()
    if row is None:
        return None
    revision_row = work.world_scenarios.get_world_revision(context, world_id, int(row[0]))
    release_row = work.world_scenarios.get_world_release(context, world_id, int(row[0]), int(row[1]))
    if revision_row is None or release_row is None:
        raise KeyError(f"world_release_not_found:{world_id}:{row[0]}:{row[1]}")
    return (
        WorldRevisionDocument.model_validate(revision_row["document"]),
        WorldReleaseDocument.model_validate(release_row["document"]),
    )


def _next_definition_revision(work: Any, context: Any, map_id: str) -> int:
    row = work.connection.execute(
        "SELECT COALESCE(MAX(definition_revision), 0) FROM omnix_rpg_map_definitions "
        "WHERE workspace_id = %s AND map_id = %s",
        (context.workspace_id, map_id),
    ).fetchone()
    return int(row[0]) + 1


def _adoption_record(
    state: Mapping[str, Any],
    bundle_sha256: str,
    context: Any,
    source_revision: WorldRevisionDocument | None,
    source_release: WorldReleaseDocument | None,
) -> dict[str, Any]:
    return {
        "schema_version": ADOPTION_SCHEMA,
        "bundle_sha256": bundle_sha256,
        "source_world_id": state["source_world_id"],
        "catalog": state["catalog"],
        "source_world_revision": source_revision.revision if source_revision else None,
        "source_world_release": source_release.release if source_release else None,
        "source_canon_hash": canonical_content_hash(dict(source_revision.canon)) if source_revision else None,
        "adopted_at": datetime.now(timezone.utc).isoformat(),
        "user_id": context.user_id,
    }


def _store_adoption(
    work: Any,
    context: Any,
    world: Mapping[str, Any],
    adoption: Mapping[str, Any],
    *,
    source_mode: str | None = None,
) -> None:
    metadata = {**dict(world.get("metadata") or {}), "world_adoption": dict(adoption)}
    work.connection.execute(
        "UPDATE omnix_rpg_worlds SET metadata_jsonb = %s::jsonb, source_mode = %s, updated_at = CURRENT_TIMESTAMP "
        "WHERE workspace_id = %s AND id = %s",
        (
            json.dumps(metadata, sort_keys=True),
            source_mode or str(world.get("source_mode") or "imported"),
            context.workspace_id,
            world["id"],
        ),
    )


def adopt_shared_world(
    world_id: str,
    *,
    bundle_sha256: str,
    database: Any | None = None,
) -> dict[str, Any]:
    """Accept the imported bundle ``bundle_sha256`` as this workspace's own, so its openings can launch."""

    context = current_tenant()
    with unit_of_work(database) as work:
        world = require_world_writable(work, context, world_id)
        state = shared_world_state(world)
        if not state["shared"]:
            raise ValueError(f"world_not_shared:{world_id}")
        if not bundle_sha256 or bundle_sha256 != state["bundle_sha256"]:
            # The acceptance names the bundle the person reviewed; a different import is not what they accepted.
            raise ValueError(f"world_adoption_bundle_mismatch:{world_id}")
        if state["adopted"]:
            work.rollback()
            return {"ok": True, "status": "adopted", "reused": True, "world_id": world_id, "adoption": state["adoption"]}

        latest = _latest_release(work, context, world_id)
        if latest is None:
            # An authoring-only bundle has no release to carry forward: adopting records the acceptance, and its
            # openings are then prepared from its imported lore like any imported world's.
            adoption = _adoption_record(state, bundle_sha256, context, None, None)
            _store_adoption(work, context, world, adoption, source_mode="imported")
            work.commit()
            return {"ok": True, "status": "adopted", "reused": False, "world_id": world_id, "adoption": adoption,
                    "launch_ready": False, "openings": []}
        source_revision, source_release = latest
        current = int(
            work.connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM omnix_rpg_world_revisions WHERE workspace_id = %s AND world_id = %s",
                (context.workspace_id, world_id),
            ).fetchone()[0]
        )
        target = current + 1
        adoption = _adoption_record(state, bundle_sha256, context, source_revision, source_release)
        revision = compile_world_revision(
            world_id=world_id,
            revision=target,
            title=source_revision.title,
            canon=source_revision.canon,
            entity_manifest=source_revision.entity_manifest,
            topology=source_revision.topology,
            adventure_seeds=source_revision.adventure_seeds,
            blueprint_requirements=source_revision.blueprint_requirements,
            provenance={"source": ADOPTION_AUTHORSHIP_SOURCE, "adoption": adoption},
        )
        stored_revision = work.world_scenarios.publish_world_revision(
            context,
            world_id=world_id,
            document=revision.model_dump(mode="json"),
            content_hash=revision.content_hash,
            expected_revision=current,
        )

        source_definitions = _definitions_from_work(work, context, source_release)
        definitions: dict[str, GridMapDefinition] = {}
        bindings: list[MapDefinitionBinding] = []
        for binding in source_release.map_bindings:
            definition = with_grid_definition_hashes(
                source_definitions[binding.map_id].model_copy(
                    update={
                        "definition_revision": _next_definition_revision(work, context, binding.map_id),
                        "world_revision": target,
                    }
                )
            )
            work.map_instances.put_definition(
                context,
                map_id=definition.map_id,
                definition_revision=definition.definition_revision,
                world_id=world_id,
                world_revision=target,
                document=definition.model_dump(mode="json"),
                definition_hash=definition.definition_hash,
                semantic_interface_hash=definition.semantic_interface_hash,
            )
            definitions[definition.map_id] = definition
            bindings.append(
                binding.model_copy(
                    update={
                        "definition_revision": definition.definition_revision,
                        "definition_hash": definition.definition_hash,
                        "semantic_interface_hash": definition.semantic_interface_hash,
                    }
                )
            )
        release = certify_world_release(
            revision,
            compile_world_release(
                revision,
                release=1,
                map_bindings=bindings,
                indexes=source_release.indexes,
                asset_bindings=source_release.asset_bindings,
                compiler_provenance={**dict(source_release.compiler_provenance), "adoption": adoption},
                certification={
                    **dict(source_release.certification),
                    "authorship_validated": True,
                    "authorship_source": ADOPTION_AUTHORSHIP_SOURCE,
                },
                artifact_stage=source_release.artifact_stage,
                runtime_seed=source_release.runtime_seed,
                materialization=source_release.materialization,
                playtest_report=source_release.playtest_report,
            ),
            definitions,
        )
        stored_release = work.world_scenarios.publish_world_release(
            context,
            world_id=world_id,
            world_revision=target,
            document=release.model_dump(mode="json"),
            release_hash=release.release_hash,
        )

        openings: list[dict[str, Any]] = []
        for scenario in work.world_library.iter_scenarios(context, world_id=world_id):
            history = work.world_library.list_scenario_revisions(context, str(scenario["id"]))
            if not history:
                continue
            latest = ScenarioRevisionDocument.model_validate(history[0]["document"])
            runtime_seed_hash = str(dict(release.runtime_seed).get("content_hash") or "") if latest.runtime_seed_hash else ""
            document = _ensure_hash(
                latest.model_copy(
                    update={
                        "revision": latest.revision + 1,
                        "world_revision": target,
                        "world_revision_hash": revision.content_hash,
                        "compatible_release": release.release,
                        "runtime_seed_hash": runtime_seed_hash,
                        "content_hash": "",
                    }
                ),
                "content_hash",
            )
            validate_scenario_against_release(document, release, definitions)
            work.world_scenarios.publish_scenario_revision(
                context,
                scenario_id=document.scenario_id,
                world_id=world_id,
                world_revision=target,
                document=document.model_dump(mode="json"),
                content_hash=document.content_hash,
            )
            openings.append({"scenario_id": document.scenario_id, "revision": document.revision})

        _store_adoption(work, context, world, adoption)
        work.commit()
    return {
        "ok": True,
        "status": "adopted",
        "reused": False,
        "world_id": world_id,
        "adoption": adoption,
        "world_revision": int(stored_revision["revision"]),
        "world_release": int(stored_release["release"]),
        "launch_ready": bool(release.certification.get("launch_ready")),
        "openings": openings,
    }


__all__ = [
    "ADOPTION_AUTHORSHIP_SOURCE",
    "adopt_shared_world",
    "require_adopted_if_shared",
    "shared_world_state",
]
