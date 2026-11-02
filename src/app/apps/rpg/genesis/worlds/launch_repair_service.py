"""One-click recovery of a world and scenario for campaign launch: a generated world is recompiled from its run, an
imported one from its topics, and one written by hand or installed from a bundle republished as it stands; each with
its authored map blueprints and play sections written in (RQ-4.1)."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, Mapping, Sequence

from app.security.tenant_context import current_tenant
from app.persistence.unit_of_work import unit_of_work
from app.apps.rpg.genesis.forge.canon_audit import CanonAuditReport
from app.apps.rpg.genesis.forge.canon_compiler import compile_campaign_bible
from app.apps.rpg.genesis.forge.canon_relationships import compile_cross_domain_relationships
from app.apps.rpg.genesis.forge.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
)
from app.apps.rpg.world.map_grid_contracts import GridMapDefinition, with_grid_definition_hashes

from .contracts import ScenarioProjectCreate, ScenarioRevisionDocument, WorldReleaseDocument, WorldRevisionDocument
from .generation_publication import (
    WorldGenerationPublication,
    compile_world_generation_publication,
)
from .map_blueprint_authoring import latest_ready_blueprint_requirements
from .map_blueprint_publication import merge_authored_blueprints
from .play_section_publication import authored_play_sections, merge_authored_play_sections, play_sections_hash
from .library_service import read_world_detail
from .library_service import start_world_library_generation
from .postgres_service import create_scenario_project, publish_scenario_revision
from .service import compile_world_release, compile_world_revision
from .starter_bubble_service import promote_starter_bubble
from .topic_entries import carries_entries, entries_hash, unresolved, with_topic_entries
from .world_adoption import require_adopted_if_shared
from .world_bundle import safe_bundle_segment


def _compile_imported_topics_publication(
    world: Mapping[str, Any],
    topic_rows: Sequence[Mapping[str, Any]],
    *,
    revision: int,
    starting_location_id: str,
) -> WorldGenerationPublication:
    """Compile trusted portable lore without pretending it is fresh model output."""

    topics: list[GeneratedTopic] = []
    for row in topic_rows:
        if str(row.get("status") or "") != "ready":
            continue
        topic = GeneratedTopic.from_dict(dict(row.get("content") or {}))
        entities: list[dict[str, Any]] = []
        for entity in topic.entities:
            normalized = dict(entity)
            # Portable authoring profiles use ``place``/``actor`` while the
            # launch compiler's legacy opening contract expects these runtime
            # kinds. This is an adapter, not a lore rewrite.
            if normalized.get("kind") == "place":
                normalized["kind"] = "location"
            elif normalized.get("kind") == "actor":
                normalized["kind"] = "npc"
                normalized.setdefault("dossier_status", "complete")
            entities.append(normalized)
        topics.append(replace(topic, entities=tuple(entities)))
    if not topics:
        raise ValueError("world_imported_topics_missing")
    generation = WorldForgeGenerationResult(
        topics=tuple(topics),
        jobs=(),
        failed_topic_ids=(),
        generation_order=(),
    )
    relationships = compile_cross_domain_relationships(generation.topics)
    compilation = compile_campaign_bible(
        generation,
        compiled_relationships=relationships,
        # Bundle parsing verifies the archive and every topic content hash;
        # imported canon is not provider output and must not fail provider-only
        # provenance gates during launch recovery.
        audit=CanonAuditReport(passed=True, checks={"portable_bundle_verified": len(topics)}),
        topic_graph={},
        campaign_id=f"world-import:{world['id']}:{revision}",
        campaign_template=str(
            dict(world.get("metadata") or {}).get("campaign_template")
            or world.get("genre")
            or "classic_fantasy"
        ),
        starting_location=starting_location_id,
        canon_revision=revision,
    )
    if not compilation.launch_ready:
        raise ValueError(
            "world_imported_topics_incomplete:"
            + ",".join(compilation.missing_requirements)
        )
    canon = dict(compilation.document)
    entity_map = dict(canon.get("entities") or {})
    locations = {
        entity_id
        for entity_id, entity in entity_map.items()
        if isinstance(entity, Mapping) and entity.get("kind") == "location"
    }
    revision_document = compile_world_revision(
        world_id=str(world["id"]),
        revision=revision,
        title=str(world.get("title") or world["id"]),
        canon=canon,
        entity_manifest={"schema_version": "rpg_world_entity_manifest_v1", "entities": entity_map},
        topology={
            "schema_version": "rpg_world_topology_v1",
            "locations": sorted(locations),
            "routes": [
                dict(item)
                for item in canon.get("relationships") or ()
                if isinstance(item, Mapping)
                and str(item.get("kind") or item.get("type") or "").casefold()
                in {"route", "travel", "portal", "road", "path", "access_route"}
            ],
        },
        adventure_seeds=(
            dict(item)
            for item in canon.get("story_threads") or ()
            if isinstance(item, Mapping)
        ),
        blueprint_requirements=(
            {
                "map_id": f"map:{location_id}",
                "location_id": location_id,
                "simulation_readiness": "semantic",
                "presentation_readiness": "placeholder",
            }
            for location_id in sorted(locations)
        ),
        provenance={
            "source": "verified_imported_world_topics",
            "topic_hashes": {
                str(row.get("topic_id") or ""): str(row.get("content_hash") or "")
                for row in topic_rows
            },
        },
    )
    certification = {
        "schema_version": "rpg_imported_world_release_certification_v1",
        "launch_ready": True,
        "missing_requirements": [],
        "completeness": dict(compilation.completeness),
        "consistency_report": {"passed": True, "source": "portable_bundle_verified"},
        "imported_canon": True,
        "authorship_validated": True,
        "authorship_source": "verified_portable_bundle",
    }
    return WorldGenerationPublication(
        world_revision=revision_document,
        world_release=compile_world_release(
            revision_document,
            release=1,
            indexes=dict(compilation.retrieval_index),
            certification=certification,
        ),
        certification=certification,
    )


# What a republished revision does not carry from the one it is made from: the trust a compile attaches anew, the
# starter-bubble promotion it has yet to have, and the play-sections draft written in afresh.
_REPUBLISHED_PROVENANCE_DROPPED = frozenset({
    "authorship", "authorship_receipt", "authorship_validation", "human_authorship_event_id",
    "starter_bubble", "authored_play_sections", "republished_from_revision",
})


def _draft_topics(work: Any, context: Any, world: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The world's topics as its editor holds them (one each, as last written)."""
    return work.world_library.list_topics(context, str(world["id"]))


def _republished_latest(
    work: Any, context: Any, world_id: str, *, revision: int, topic_rows: Sequence[Mapping[str, Any]],
) -> tuple[WorldGenerationPublication, list[GridMapDefinition]]:
    """A world with nothing to recompile from (written by hand or installed from a bundle: no generation run, no
    imported topics) republished as its latest revision stands, from before that revision's starter-bubble
    promotion, so the author's play sections can be written in (RQ-4.1), and with the entries its editor holds
    (``topic_entries``, EV-6); with its map definitions issued again for the new revision, to be stored once that
    revision is."""
    latest = work.world_scenarios.latest_world_revision(context, world_id)
    if latest is None:
        raise ValueError(f"world_launch_repair_generation_missing:{world_id}")
    base = WorldRevisionDocument.model_validate(latest["document"])
    promoted_from = int(dict(base.provenance.get("starter_bubble") or {}).get("source_world_revision") or 0)
    if promoted_from:
        row = work.world_scenarios.get_world_revision(context, world_id, promoted_from)
        if row is not None:
            base = WorldRevisionDocument.model_validate(row["document"])
    releases = [row for row in work.world_library.list_world_releases(context, world_id)
                if int(row.get("world_revision") or 0) == base.revision]
    if not releases:
        raise ValueError(f"world_launch_repair_release_missing:{world_id}:{base.revision}")
    base_release = WorldReleaseDocument.model_validate(
        max(releases, key=lambda row: int(row.get("release") or 0))["document"])
    # A map definition belongs to one world revision: each the release binds is issued again for the new one.
    bindings, definitions = [], []
    for binding in base_release.map_bindings:
        stored = work.map_instances.get_definition(context, binding.map_id, binding.definition_revision)
        if stored is None:
            raise ValueError(f"world_launch_repair_map_definition_missing:{binding.map_id}")
        definition_revision = work.map_instances.next_definition_revision(context, binding.map_id)
        definition = with_grid_definition_hashes(GridMapDefinition.model_validate(
            {**dict(stored["document"]), "world_revision": revision, "definition_revision": definition_revision}))
        definitions.append(definition)
        bindings.append(binding.model_copy(update={
            "definition_revision": definition_revision,
            "definition_hash": definition.definition_hash,
            "semantic_interface_hash": definition.semantic_interface_hash,
        }))
    canon, manifest, indexes = with_topic_entries(base.canon, base.entity_manifest, base_release.indexes, topic_rows)
    dangling = unresolved(base.canon, base.entity_manifest, topic_rows)
    if dangling:  # an entry the editor added or changed names what the world does not hold
        raise ValueError(f"world_launch_repair_entry_unresolved:{'; '.join(dangling[:5])}")
    entries = entries_hash(topic_rows)
    republished = compile_world_revision(
        world_id=world_id,
        revision=revision,
        title=base.title,
        canon=canon,
        entity_manifest=manifest,
        topology=base.topology,
        adventure_seeds=base.adventure_seeds,
        blueprint_requirements=base.blueprint_requirements,
        provenance={**{key: value for key, value in base.provenance.items() if key not in _REPUBLISHED_PROVENANCE_DROPPED},
                    "republished_from_revision": base.revision, "topic_entries": entries},
    )
    release = compile_world_release(
        republished,
        release=1,
        map_bindings=bindings,
        indexes=indexes,
        asset_bindings=base_release.asset_bindings,
        compiler_provenance={**dict(base_release.compiler_provenance), "republished_from_revision": base.revision},
        # The revision it is made from, with the editor's entries, each reference checked above (``unresolved``), and
        # its maps (its play sections are checked when written in).
        certification={**dict(base_release.certification), "republished_from_revision": base.revision,
                       "topic_entries": entries},
        artifact_stage=base_release.artifact_stage,
        runtime_seed=base_release.runtime_seed,
        materialization=base_release.materialization,
        playtest_report=base_release.playtest_report,
    )
    return WorldGenerationPublication(world_revision=republished, world_release=release,
                                      certification=dict(release.certification)), definitions


def _existing_ready_promotion(
    world_id: str,
    *,
    starting_location_id: str,
    play_sections: str,
    database: Any | None,
    topic_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """A launch-ready promotion at ``starting_location_id`` that already carries the world's play-sections draft
    (``play_sections``, its hash, "" for none), and, for a republished world, the entries its editor holds
    (``topic_rows``): a repair reuses it rather than publishing again."""
    context = current_tenant()
    with unit_of_work(database) as work:
        revisions = work.world_library.list_world_revisions(context, world_id)
        releases = work.world_library.list_world_releases(context, world_id)
        work.rollback()
    revision_by_number = {
        int(row.get("revision") or 0): row for row in revisions
    }
    for release in releases:
        release_document = dict(release.get("document") or {})
        certification = dict(release_document.get("certification") or {})
        if not bool(certification.get("launch_ready")):
            continue
        if (
            str(certification.get("schema_version") or "")
            == "rpg_imported_world_release_certification_v1"
            and not bool(certification.get("authorship_validated"))
        ):
            # Older recovery releases predate portable-bundle certification.
            # Rebuild them rather than pinning a scenario to an unlaunchable
            # immutable release.
            continue
        revision_number = int(release.get("world_revision") or 0)
        revision = revision_by_number.get(revision_number, {})
        revision_document = dict(revision.get("document") or {})
        starter = dict(
            dict(revision_document.get("provenance") or {}).get("starter_bubble")
            or {}
        )
        provenance = dict(revision_document.get("provenance") or {})
        if topic_rows is not None and not carries_entries(revision_document, topic_rows):
            continue  # the editor has changed or added an entry since (EV-6)
        if provenance.get("republished_from_revision"):
            # A republished world's maps are its own and complete: any opening launches from it, wherever it starts,
            # while it is the world as it stands (a later revision, from an edit or another draft, supersedes it).
            if revision_number != max(revision_by_number, default=0):
                continue
        elif str(starter.get("starting_location_id") or "") != starting_location_id:
            continue
        if str(provenance.get("authored_play_sections") or "") != play_sections:
            continue  # written before the author's latest sections (RQ-4.1)
        return {
            "world_id": world_id,
            "source_world_revision": int(starter.get("source_world_revision") or 0),
            "world_revision": revision_number,
            "world_revision_hash": str(revision.get("content_hash") or ""),
            "world_release": int(release.get("release") or 0),
            "world_release_hash": str(release.get("release_hash") or ""),
            "certification": certification,
            "reused": True,
        }
    return None


def _publish_repaired_world(
    world_id: str,
    *,
    starting_location_id: str,
    database: Any | None,
) -> dict[str, Any]:
    context = current_tenant()
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id, for_update=True)
        if world is None:
            raise KeyError(f"world_not_found:{world_id}")
        # Only the latest run is used.
        runs = work.world_library.list_generation_runs(context, world_id=world_id, limit=1)
        imported_topics = str(world.get("source_mode") or "") == "imported"
        current_row = work.connection.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM omnix_rpg_world_revisions "
            "WHERE workspace_id = %s AND world_id = %s",
            (context.workspace_id, world_id),
        ).fetchone()
        current_revision = int(current_row[0])
        definitions: list[GridMapDefinition] = []
        if not runs and not imported_topics:
            compiled, definitions = _republished_latest(work, context, world_id, revision=current_revision + 1,
                                                        topic_rows=_draft_topics(work, context, world))
        else:
            run = None if imported_topics else runs[0]
            topic_rows = (
                work.world_generation.list_topics(
                    context,
                    world_id=world_id,
                    draft_revision=int(run.get("draft_revision") or 1),
                )
                if run is not None
                else work.world_library.list_topics(context, world_id)
            )
            compiled = (
                compile_world_generation_publication(
                    run=run,
                    world=world,
                    topic_rows=topic_rows,
                    revision=current_revision + 1,
                    starting_location_override=starting_location_id,
                )
                if run is not None
                else _compile_imported_topics_publication(
                    world,
                    topic_rows,
                    revision=current_revision + 1,
                    starting_location_id=starting_location_id,
                )
            )
        requirements = latest_ready_blueprint_requirements(work, context, world_id)
        revision, release = merge_authored_blueprints(
            compiled.world_revision,
            compiled.world_release,
            requirements,
        )
        from .approved_inventions import approved_inventions

        revision, release = merge_authored_play_sections(revision, release, authored_play_sections(world),
                                                         approved_inventions(world))
        compiled = WorldGenerationPublication(
            world_revision=revision,
            world_release=release,
            certification=dict(release.certification),
        )
        if not bool(compiled.certification.get("launch_ready")):
            missing = ",".join(
                str(value)
                for value in compiled.certification.get("missing_requirements") or ()
            )
            consistency = dict(compiled.certification.get("consistency_report") or {})
            issue_codes = Counter(
                str(issue.get("code") or "unknown")
                for issue in consistency.get("issues") or ()
                if isinstance(issue, dict)
            )
            findings = ",".join(
                f"{code}={count}" for code, count in issue_codes.most_common()
            )
            examples = ";".join(
                f"{issue.get('item_id')}:{issue.get('message')}"
                for issue in (consistency.get("issues") or ())[:5]
                if isinstance(issue, dict)
            )
            raise ValueError(
                f"world_launch_repair_incomplete:{missing or 'unknown'}"
                f":{findings or 'no_audit_details'}:{examples}"
            )
        stored_revision = work.world_scenarios.publish_world_revision(
            context,
            world_id=world_id,
            document=compiled.world_revision.model_dump(mode="json"),
            content_hash=compiled.world_revision.content_hash,
            expected_revision=current_revision,
        )
        for definition in definitions:
            work.map_instances.put_definition(
                context,
                map_id=definition.map_id,
                definition_revision=definition.definition_revision,
                world_id=world_id,
                world_revision=int(stored_revision["revision"]),
                document=definition.model_dump(mode="json"),
                definition_hash=definition.definition_hash,
                semantic_interface_hash=definition.semantic_interface_hash,
            )
        stored_release = work.world_scenarios.publish_world_release(
            context,
            world_id=world_id,
            world_revision=int(stored_revision["revision"]),
            document=compiled.world_release.model_dump(mode="json"),
            release_hash=compiled.world_release.release_hash,
        )
        work.commit()
    return {
        "world_revision": int(stored_revision["revision"]),
        "world_revision_hash": str(stored_revision["content_hash"]),
        "world_release": int(stored_release["release"]),
        "world_release_hash": str(stored_release["release_hash"]),
        "certification": dict(compiled.certification),
        # Republished as it stood (its maps complete, each issued again): launchable without a starter bubble.
        "republished": bool(definitions) or not (runs or imported_topics),
    }


def repair_world_for_launch(
    world_id: str,
    *,
    scenario_id: str,
    starting_location_id: str,
    database: Any | None = None,
) -> dict[str, Any]:
    """Repair canon, materialize starter maps, and repin the selected scenario."""

    if not scenario_id.strip():
        raise ValueError("world_launch_repair_scenario_required")
    if not starting_location_id.strip():
        raise ValueError("world_launch_repair_starting_location_required")

    context = current_tenant()
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id)
        if world is None:
            raise KeyError(f"world_not_found:{world_id}")
        require_adopted_if_shared(world)
        scenario = next(
            (
                row
                for row in work.world_library.iter_scenarios(context, world_id=world_id)
                if str(row.get("id") or "") == scenario_id
            ),
            None,
        )
        if scenario is None:
            raise KeyError(f"scenario_not_found:{scenario_id}")
        if str(scenario.get("world_id") or "") != world_id:
            raise ValueError(f"scenario_world_mismatch:{scenario_id}:{world_id}")
        revisions = work.world_library.list_scenario_revisions(context, scenario_id)
        # A world with nothing to recompile from carries its editor's entries when it is published (EV-6).
        republishes = (str(world.get("source_mode") or "") != "imported"
                       and not work.world_library.list_generation_runs(context, world_id=world_id, limit=1))
        topic_rows = _draft_topics(work, context, world) if republishes else None
        work.rollback()

    promotion = _existing_ready_promotion(
        world_id,
        starting_location_id=starting_location_id,
        play_sections=play_sections_hash(authored_play_sections(world)),
        database=database,
        topic_rows=topic_rows,
    )
    repaired: dict[str, Any] = {}
    if promotion is None:
        repaired = _publish_repaired_world(
            world_id,
            starting_location_id=starting_location_id,
            database=database,
        )
        if repaired["republished"]:
            promotion = {"world_id": world_id, **{key: repaired[key] for key in (
                "world_revision", "world_revision_hash", "world_release", "world_release_hash", "certification")}}
        else:
            promoted_result = promote_starter_bubble(
                world_id=world_id,
                source_world_revision=int(repaired["world_revision"]),
                starting_location_id=starting_location_id,
                database=database,
            )
            promotion = dict(promoted_result.get("promotion") or {})
    promoted_revision = int(promotion.get("world_revision") or 0)
    promoted_release = int(promotion.get("world_release") or 0)
    promoted_hash = str(promotion.get("world_revision_hash") or "")
    release_document = dict(promotion.get("release_document") or {})
    final_certification = dict(
        promotion.get("certification")
        or release_document.get("certification")
        or {}
    )
    if not promoted_revision or not promoted_release or not promoted_hash:
        raise ValueError("world_launch_repair_map_promotion_failed")
    if not bool(final_certification.get("launch_ready")):
        raise ValueError("world_launch_repair_map_certification_failed")

    previous_document = dict(revisions[0].get("document") or {}) if revisions else {}
    if (
        revisions
        and int(previous_document.get("world_revision") or 0) == promoted_revision
        and int(previous_document.get("compatible_release") or 0) == promoted_release
        and str(previous_document.get("starting_location_id") or "")
        == starting_location_id
    ):
        return {
            "ok": True,
            "status": "ready",
            "reused": True,
            "world": repaired,
            "promotion": promotion,
            "scenario_revision": revisions[0],
            "certification": final_certification,
        }
    scenario_document = {
        **previous_document,
        "scenario_id": scenario_id,
        "revision": max((int(row.get("revision") or 0) for row in revisions), default=0) + 1,
        "world_id": world_id,
        "world_revision": promoted_revision,
        "world_revision_hash": promoted_hash,
        "compatible_release": promoted_release,
        "starting_epoch": str(previous_document.get("starting_epoch") or "Day 1"),
        "starting_location_id": starting_location_id,
        "activated_conflict_ids": list(previous_document.get("activated_conflict_ids") or ()),
        "initial_npc_ids": list(previous_document.get("initial_npc_ids") or ()),
        "protagonist_options": list(previous_document.get("protagonist_options") or ()),
        "starting_resources": dict(previous_document.get("starting_resources") or {}),
        "opening_seed_ids": list(previous_document.get("opening_seed_ids") or ()),
        "map_initialization": list(previous_document.get("map_initialization") or ()),
        "content_hash": "",
    }
    stored_scenario = publish_scenario_revision(
        ScenarioRevisionDocument.model_validate(scenario_document),
        database=database,
    )
    return {
        "ok": True,
        "status": "ready",
        "reused": False,
        "world": repaired,
        "promotion": promotion,
        "scenario_revision": stored_scenario,
        "certification": final_certification,
    }


def _opening_scenario_id(
    opening_id: str,
    world_id: str,
    existing_ids: set[str],
    taken_ids: set[str],
) -> str:
    """The scenario id of an opening: ``scenario:<opening>``, unless another world (a second import of the
    same bundle) holds it; then it is qualified by the world, as a bundle import qualifies its ids."""
    base = f"scenario:{opening_id.split(':')[-1]}"
    if base in existing_ids or base not in taken_ids:
        return base
    return f"scenario:{safe_bundle_segment(world_id)}:{opening_id.split(':')[-1]}"


def prepare_opening_scenarios_for_launch(
    world_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    """Promote authored opening-scenario canon into launchable scenario projects.

    Imported bundles can carry complete opening scenario lore without the
    publication records that a campaign launch needs. Materialize those canon
    entries deterministically, then use the normal repair/promotion pipeline
    to produce certified scenario revisions and releases.
    """
    detail = read_world_detail(world_id, database=database)
    require_adopted_if_shared(dict(detail.get("world") or {}))
    openings: list[Mapping[str, Any]] = []
    for topic in detail.get("topics") or ():
        if str(topic.get("topic_id") or "") != "opening_scenarios":
            continue
        content = raw_content if isinstance(raw_content := topic.get("content"), Mapping) else {}
        openings.extend(  # the entries the topic keeps, in either list the editor writes them to (EV-6)
            entity for key in ("entities", "opening_scenarios") for entity in content.get(key) or ()
            if isinstance(entity, Mapping)
        )
    if not openings:
        raise ValueError("world_opening_scenarios_not_found")

    context = current_tenant()
    with unit_of_work(database) as work:
        runs = work.world_library.list_generation_runs(context, world_id=world_id, limit=1)
        existing_ids = {
            str(row.get("id") or "")
            for row in work.world_library.iter_scenarios(context, world_id=world_id)
        }
        taken_ids = {
            str(row[0])
            for row in work.connection.execute(
                "SELECT id FROM omnix_rpg_scenarios WHERE workspace_id = %s",
                (context.workspace_id,),
            ).fetchall()
        }
        work.rollback()

    imported_world = str(detail.get("world", {}).get("source_mode") or "") == "imported"
    if not runs and not imported_world:
        first_opening = openings[0]
        generation = start_world_library_generation(
            world_id,
            starting_location=str(
                first_opening.get("starting_place_id")
                or first_opening.get("starting_location_id")
                or ""
            ),
            database=database,
        )
        return {
            "ok": True,
            "world_id": world_id,
            "status": "generating",
            "prepared": [],
            "generation_run_id": str(generation["run"].get("run_id") or ""),
        }
    if runs and not imported_world and str(runs[0].get("status") or "") != "ready":
        status = str(runs[0].get("status") or "")
        return {
            "ok": True,
            "world_id": world_id,
            "status": "review_required" if status == "review" else "generating",
            "prepared": [],
            "generation_run_id": str(runs[0].get("run_id") or ""),
        }

    prepared: list[dict[str, Any]] = []
    for opening in openings:
        opening_id = str(opening.get("id") or "").strip()
        title = str(opening.get("name") or opening.get("title") or "").strip()
        starting_location_id = str(
            opening.get("starting_place_id") or opening.get("starting_location_id") or ""
        ).strip()
        if not opening_id or not title or not starting_location_id:
            continue
        scenario_id = _opening_scenario_id(opening_id, world_id, existing_ids, taken_ids)
        if scenario_id not in existing_ids:
            create_scenario_project(
                ScenarioProjectCreate(
                    scenario_id=scenario_id,
                    world_id=world_id,
                    title=title,
                    description=str(opening.get("description") or opening.get("short_summary") or ""),
                    metadata={"source_opening_entity_id": opening_id, "materialized_from": "opening_scenarios"},
                ),
                database=database,
            )
        result = repair_world_for_launch(
            world_id,
            scenario_id=scenario_id,
            starting_location_id=starting_location_id,
            database=database,
        )
        prepared.append({"scenario_id": scenario_id, "title": title, "result": result})
    if not prepared:
        raise ValueError("world_opening_scenarios_missing_launch_fields")
    return {"ok": True, "world_id": world_id, "prepared": prepared}
