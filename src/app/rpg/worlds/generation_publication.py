"""Compile completed reusable-world topic runs into immutable revisions and releases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.rpg.session.genesis.canon_audit import audit_generated_canon
from app.rpg.session.genesis.canon_compiler import compile_campaign_bible
from app.rpg.session.genesis.canon_relationships import compile_cross_domain_relationships
from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
    WorldForgeJobRecord,
)
from app.rpg.session.genesis.world_forge_quality import apply_world_forge_quality_audit

from .contracts import WorldReleaseDocument, WorldRevisionDocument
from .lifecycle_service import require_world_writable
from .service import compile_world_release, compile_world_revision

_NON_GENERATION_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}


@dataclass(frozen=True)
class WorldGenerationPublication:
    world_revision: WorldRevisionDocument
    world_release: WorldReleaseDocument
    certification: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "world_revision": self.world_revision.model_dump(mode="json"),
            "world_release": self.world_release.model_dump(mode="json"),
            "certification": dict(self.certification),
        }


def _graph_from_payload(value: Mapping[str, Any]) -> CampaignTopicGraph:
    nodes = tuple(
        CampaignTopicNode(
            topic_id=str(row.get("topic_id") or ""),
            title=str(row.get("title") or ""),
            category=str(row.get("category") or "lore"),
            dependencies=tuple(str(item) for item in row.get("dependencies") or ()),
            generator_role=str(row.get("generator_role") or "world_forge"),
            required_before_launch=bool(row.get("required_before_launch", True)),
            visibility=str(row.get("visibility") or "game_master_canon"),
            target_count=int(row.get("target_count") or 1),
            metadata=dict(row.get("metadata") or {}),
        )
        for row in value.get("nodes") or ()
        if isinstance(row, Mapping)
    )
    graph = CampaignTopicGraph(
        graph_version=str(value.get("graph_version") or "rpg_world_topic_graph_v1"),
        campaign_template=str(value.get("campaign_template") or "classic_fantasy"),
        depth=str(value.get("depth") or "standard"),  # type: ignore[arg-type]
        nodes=nodes,
        metadata=dict(value.get("metadata") or {}),
    )
    issues = graph.validate()
    if issues:
        raise ValueError("invalid_world_generation_graph:" + ",".join(issues))
    return graph


def _generation_result(
    graph: CampaignTopicGraph,
    topic_rows: list[Mapping[str, Any]],
) -> WorldForgeGenerationResult:
    rows = {str(row.get("topic_id") or ""): row for row in topic_rows}
    topics: list[GeneratedTopic] = []
    jobs: list[WorldForgeJobRecord] = []
    generation_order: list[tuple[str, ...]] = []
    missing: list[str] = []
    for node in graph.topological_order():
        if node.category in _NON_GENERATION_CATEGORIES:
            continue
        row = rows.get(node.topic_id)
        if row is None or str(row.get("status") or "") != "ready":
            missing.append(node.topic_id)
            continue
        topic = GeneratedTopic.from_dict(dict(row.get("content") or {}))
        if topic.topic_id != node.topic_id:
            raise ValueError(
                f"world_generation_topic_identity_mismatch:{node.topic_id}:{topic.topic_id}"
            )
        topics.append(topic)
        jobs.append(
            WorldForgeJobRecord(
                topic_id=node.topic_id,
                status="completed",
                dependency_ids=node.dependencies,
                generator_role=node.generator_role,
                output_counts={
                    "documents": len(topic.documents),
                    "entities": len(topic.entities),
                    "facts": len(topic.facts),
                    "relationships": len(topic.relationships),
                    "knowledge_rules": len(topic.knowledge_rules),
                    "story_threads": len(topic.story_threads),
                },
            )
        )
        generation_order.append((node.topic_id,))
    if missing:
        raise ValueError("world_generation_topics_incomplete:" + ",".join(sorted(missing)))
    return WorldForgeGenerationResult(
        topics=tuple(topics),
        jobs=tuple(jobs),
        failed_topic_ids=(),
        generation_order=tuple(generation_order),
    )


def _topology(canon: Mapping[str, Any]) -> dict[str, Any]:
    entities = canon.get("entities") if isinstance(canon.get("entities"), Mapping) else {}
    locations = [
        str(entity_id)
        for entity_id, entity in sorted(dict(entities).items())
        if isinstance(entity, Mapping) and str(entity.get("kind") or "") == "location"
    ]
    relationships = [
        dict(row)
        for row in canon.get("relationships") or ()
        if isinstance(row, Mapping)
        and str(row.get("kind") or row.get("type") or "").casefold()
        in {"route", "travel", "portal", "road", "path"}
    ]
    return {
        "schema_version": "rpg_world_topology_v1",
        "locations": locations,
        "routes": relationships,
    }


def _blueprint_requirements(canon: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    entities = canon.get("entities") if isinstance(canon.get("entities"), Mapping) else {}
    return tuple(
        {
            "map_id": f"map:{entity_id}",
            "location_id": str(entity_id),
            "simulation_readiness": "semantic",
            "presentation_readiness": "placeholder",
        }
        for entity_id, entity in sorted(dict(entities).items())
        if isinstance(entity, Mapping) and str(entity.get("kind") or "") == "location"
    )


def compile_world_generation_publication(
    *,
    run: Mapping[str, Any],
    world: Mapping[str, Any],
    topic_rows: list[Mapping[str, Any]],
    revision: int,
) -> WorldGenerationPublication:
    """Build deterministic immutable publication documents from one completed run."""

    graph = _graph_from_payload(dict(run.get("graph") or {}))
    generation = _generation_result(graph, topic_rows)
    relationships = compile_cross_domain_relationships(generation.topics)
    audit = audit_generated_canon(
        generation.topics,
        compiled_relationships=relationships,
    )
    audit = apply_world_forge_quality_audit(generation.topics, audit)
    context = dict(run.get("context") or {})
    generation_context = dict(context.get("generation_context") or {})
    starting_location = str(
        generation_context.get("starting_location")
        or world.get("metadata", {}).get("starting_location")
        or ""
    )
    compilation = compile_campaign_bible(
        generation,
        compiled_relationships=relationships,
        audit=audit,
        topic_graph=graph.as_dict(),
        campaign_id=f"world-publication:{world['id']}:{revision}",
        campaign_template=graph.campaign_template,
        starting_location=starting_location,
        canon_revision=revision,
    )
    canon = dict(compilation.document)
    entity_manifest = {
        "schema_version": "rpg_world_entity_manifest_v1",
        "entities": dict(canon.get("entities") or {}),
        "manifest": dict(canon.get("manifest") or {}),
    }
    certification = {
        "schema_version": "rpg_world_release_certification_v1",
        "launch_ready": compilation.launch_ready,
        "missing_requirements": list(compilation.missing_requirements),
        "completeness": dict(compilation.completeness),
        "consistency_report": audit.as_dict(),
        "generation_run_id": str(run.get("run_id") or ""),
        "draft_revision": int(run.get("draft_revision") or 1),
    }
    world_revision = compile_world_revision(
        world_id=str(world["id"]),
        revision=revision,
        title=str(world.get("title") or world["id"]),
        canon=canon,
        entity_manifest=entity_manifest,
        topology=_topology(canon),
        adventure_seeds=tuple(
            dict(row)
            for row in canon.get("story_threads") or ()
            if isinstance(row, Mapping)
        ),
        blueprint_requirements=_blueprint_requirements(canon),
        provenance={
            "source": "durable_world_generation",
            "generation_run_id": str(run.get("run_id") or ""),
            "settings": dict(run.get("settings") or {}),
            "topic_hashes": {
                str(row.get("topic_id") or ""): str(row.get("content_hash") or "")
                for row in topic_rows
            },
        },
    )
    world_release = compile_world_release(
        world_revision,
        release=1,
        indexes=dict(compilation.retrieval_index),
        compiler_provenance={
            "compiler": "rpg_world_generation_publication_v1",
            "generation_run_id": str(run.get("run_id") or ""),
        },
        certification=certification,
    )
    return WorldGenerationPublication(
        world_revision=world_revision,
        world_release=world_release,
        certification=certification,
    )


def publish_world_generation(
    run_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    """Atomically publish a completed run and make retries return the same release."""

    from app.persistence.identity_service import bootstrap_local_tenant
    from app.persistence.unit_of_work import unit_of_work

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
        if str(run.get("status") or "") != "review":
            raise ValueError(
                f"world_generation_not_publishable:{run_id}:{run.get('status')}"
            )
        world_id = str(run.get("world_id") or "")
        world = require_world_writable(work, context, world_id)
        topic_rows = work.world_generation.list_topics(
            context,
            world_id=world_id,
            draft_revision=int(run.get("draft_revision") or 1),
        )
        current_row = work.connection.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM omnix_rpg_world_revisions "
            "WHERE workspace_id = %s AND world_id = %s",
            (context.workspace_id, world_id),
        ).fetchone()
        current_revision = int(current_row[0])
        compiled = compile_world_generation_publication(
            run=run,
            world=world,
            topic_rows=topic_rows,
            revision=current_revision + 1,
        )
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
            "certification": dict(compiled.certification),
        }
        plan = {**dict(run.get("plan") or {}), "publication": publication_payload}
        progress = {
            **dict(run.get("progress") or {}),
            "publication": publication_payload,
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
