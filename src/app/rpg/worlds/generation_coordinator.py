"""Durable world-owned topic generation using the shared generic job system."""
from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeTopicGenerator,
)

from .generation_jobs import (
    WORLD_TOPIC_JOB_TYPE,
    WorldTopicGenerationSettings,
    canonical_hash,
    generation_progress,
    plan_ready_topic_jobs,
    topic_generation_fingerprint,
    world_generation_run_id,
)

_TERMINAL_JOB_STATUSES = {"completed", "failed", "canceled", "stale"}
_ACTIVE_JOB_STATUSES = {"queued", "leased", "running", "waiting", "retrying"}
_NON_GENERATION_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}


def _database(value: Any | None) -> Any:
    if value is not None:
        return value
    from app.persistence.database import default_database

    return default_database()


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


def _settings_from_payload(value: Mapping[str, Any]) -> WorldTopicGenerationSettings:
    return WorldTopicGenerationSettings(
        generator_version=str(value.get("generator_version") or "world-generator-v1"),
        prompt_version=str(value.get("prompt_version") or "world-prompt-v1"),
        provider_route=str(value.get("provider_route") or "configured"),
        model=str(value.get("model") or "configured"),
        seed=int(value.get("seed") or 0),
        topic_contract_version=str(
            value.get("topic_contract_version") or "rpg_world_topic_job_v1"
        ),
        output_schema_version=str(
            value.get("output_schema_version") or "rpg_world_topic_output_v1"
        ),
        compiler_version=str(value.get("compiler_version") or "world-compiler-v1"),
        max_attempts=int(value.get("max_attempts") or 3),
        priority=int(value.get("priority") or 10),
    )


def _generation_topic_ids(graph: CampaignTopicGraph) -> tuple[str, ...]:
    return tuple(
        node.topic_id
        for node in graph.topological_order()
        if node.category not in _NON_GENERATION_CATEGORIES
    )


def reusable_completed_topics(
    graph: CampaignTopicGraph,
    *,
    rows: Mapping[str, Mapping[str, Any]],
    generation_context: Mapping[str, Any],
    topic_directives: Mapping[str, Mapping[str, Any]],
    entity_manifest_hash: str,
    settings: WorldTopicGenerationSettings,
) -> dict[str, Mapping[str, Any]]:
    reusable: dict[str, Mapping[str, Any]] = {}
    for node in graph.topological_order():
        if node.category in _NON_GENERATION_CATEGORIES:
            continue
        row = rows.get(node.topic_id)
        if row is None or str(row.get("status") or "") != "ready":
            continue
        if not set(node.dependencies).issubset(reusable):
            continue
        dependency_hashes = {
            dependency_id: str(reusable[dependency_id]["content_hash"])
            for dependency_id in node.dependencies
        }
        fingerprint, input_hash, directive_hash = topic_generation_fingerprint(
            node,
            normalized_topic_input={
                "generation_context": dict(generation_context),
                "target_count": node.target_count,
                "visibility": node.visibility,
            },
            dependency_hashes=dependency_hashes,
            directives=dict(topic_directives.get(node.topic_id) or {}),
            entity_manifest_hash=entity_manifest_hash,
            settings=settings,
        )
        provenance = row.get("provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        if str(provenance.get("generation_fingerprint") or "") != fingerprint:
            continue
        if str(row.get("input_hash") or "") != input_hash:
            continue
        if str(provenance.get("directive_hash") or "") != directive_hash:
            continue
        if dict(row.get("dependency_hashes") or {}) != dependency_hashes:
            continue
        reusable[node.topic_id] = row
    return reusable


def start_world_generation(
    *,
    world_id: str,
    draft_revision: int,
    graph: CampaignTopicGraph,
    generation_context: Mapping[str, Any],
    topic_directives: Mapping[str, Mapping[str, Any]],
    entity_manifest_hash: str,
    settings: WorldTopicGenerationSettings,
    database: Any | None = None,
) -> dict[str, Any]:
    issues = graph.validate()
    if issues:
        raise ValueError("invalid_world_generation_graph:" + ",".join(issues))
    db = _database(database)
    from app.persistence.identity_service import bootstrap_local_tenant
    from app.persistence.unit_of_work import unit_of_work

    context = bootstrap_local_tenant(db)
    run_id = world_generation_run_id(
        world_id=world_id,
        draft_revision=draft_revision,
    )
    run_context = {
        "generation_context": dict(generation_context),
        "topic_directives": {
            topic_id: dict(value)
            for topic_id, value in sorted(topic_directives.items())
        },
        "entity_manifest_hash": entity_manifest_hash,
    }
    with unit_of_work(db) as work:
        if work.world_scenarios.get_world(context, world_id) is None:
            raise KeyError(f"world_not_found:{world_id}")
        run = work.world_generation.start(
            context,
            run_id=run_id,
            world_id=world_id,
            draft_revision=draft_revision,
            graph=graph.as_dict(),
            generation_context=run_context,
            settings=settings.as_dict(),
            plan={"job_ids": [], "topic_ids": list(_generation_topic_ids(graph))},
            progress=generation_progress(
                graph,
                completed_topic_ids=(),
                active_topic_ids=(),
            ),
        )
        work.commit()
    return reconcile_world_generation(run["run_id"], database=db)


def reconcile_world_generation(
    run_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    db = _database(database)
    from app.persistence.identity_service import bootstrap_local_tenant
    from app.persistence.unit_of_work import unit_of_work

    context = bootstrap_local_tenant(db)
    with unit_of_work(db) as work:
        run = work.world_generation.get(context, run_id)
        if run is None:
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        graph = _graph_from_payload(run["graph"])
        run_context = dict(run["context"])
        generation_context = dict(run_context.get("generation_context") or {})
        topic_directives = {
            str(key): dict(value)
            for key, value in dict(run_context.get("topic_directives") or {}).items()
            if isinstance(value, Mapping)
        }
        entity_manifest_hash = str(run_context.get("entity_manifest_hash") or "")
        settings = _settings_from_payload(run["settings"])
        topic_rows = work.world_generation.list_topics(
            context,
            world_id=run["world_id"],
            draft_revision=run["draft_revision"],
        )
        topic_map = {row["topic_id"]: row for row in topic_rows}
        reusable = reusable_completed_topics(
            graph,
            rows=topic_map,
            generation_context=generation_context,
            topic_directives=topic_directives,
            entity_manifest_hash=entity_manifest_hash,
            settings=settings,
        )
        jobs = [
            job
            for job in work.jobs.list_jobs(context, limit=500)
            if job["job_type"] == WORLD_TOPIC_JOB_TYPE
            and str(job["metadata"].get("run_id") or "") == run_id
        ]
        existing_job_ids = [job["id"] for job in jobs]
        plans = plan_ready_topic_jobs(
            graph,
            run_id=run_id,
            world_id=run["world_id"],
            draft_revision=run["draft_revision"],
            generation_context=generation_context,
            topic_directives=topic_directives,
            completed_topics=reusable,
            existing_job_ids=existing_job_ids,
            entity_manifest_hash=entity_manifest_hash,
            settings=settings,
        )
        for plan in plans:
            work.jobs.create_job(context, dict(plan.job_payload))
            existing_job_ids.append(plan.job_id)
        if plans:
            jobs.extend(
                work.jobs.get_job(context, plan.job_id)
                for plan in plans
                if work.jobs.get_job(context, plan.job_id) is not None
            )
        active_topics = [
            str(job["metadata"].get("topic_id") or "")
            for job in jobs
            if job["status"] in _ACTIVE_JOB_STATUSES
        ]
        failed_topics = [
            str(job["metadata"].get("topic_id") or "")
            for job in jobs
            if job["status"] == "failed"
        ]
        progress = generation_progress(
            graph,
            completed_topic_ids=tuple(reusable),
            active_topic_ids=active_topics,
            failed_topic_ids=failed_topics,
        )
        if failed_topics:
            status = "failed"
        elif progress["generation_complete"]:
            status = "review"
        else:
            status = "running"
        plan_payload = {
            "job_ids": sorted(set(existing_job_ids)),
            "new_job_ids": [plan.job_id for plan in plans],
            "reusable_topic_ids": sorted(reusable),
            "topic_ids": list(_generation_topic_ids(graph)),
        }
        updated = work.world_generation.update(
            context,
            run_id=run_id,
            status=status,
            plan=plan_payload,
            progress=progress,
            error=(
                {"code": "world_topic_job_failed", "topic_ids": failed_topics}
                if failed_topics
                else {}
            ),
        )
        work.commit()
    return updated


def execute_claimed_world_topic_job(
    *,
    job: Mapping[str, Any],
    worker_id: str,
    generator: WorldForgeTopicGenerator | None = None,
    database: Any | None = None,
) -> dict[str, Any]:
    if str(job.get("job_type") or "") != WORLD_TOPIC_JOB_TYPE:
        raise ValueError("not_world_topic_job")
    db = _database(database)
    payload = dict(job.get("input_payload") or {})
    run_id = str(payload.get("run_id") or "")
    world_id = str(payload.get("world_id") or "")
    topic_payload = dict(payload.get("topic") or {})
    topic_id = str(topic_payload.get("topic_id") or "")
    lease_token = str(job.get("lease_token") or "")
    from app.persistence.identity_service import bootstrap_local_tenant
    from app.persistence.unit_of_work import unit_of_work

    context = bootstrap_local_tenant(db)
    try:
        with unit_of_work(db) as work:
            run = work.world_generation.get(context, run_id)
            if run is None:
                raise KeyError(f"world_generation_run_not_found:{run_id}")
            dependency_hashes = dict(payload.get("dependency_hashes") or {})
            dependency_topics: dict[str, GeneratedTopic] = {}
            for dependency_id, expected_hash in sorted(dependency_hashes.items()):
                row = work.world_generation.get_topic(
                    context,
                    world_id=world_id,
                    topic_id=dependency_id,
                )
                if row is None or row["content_hash"] != expected_hash:
                    raise RuntimeError(
                        f"world_topic_dependency_mismatch:{topic_id}:{dependency_id}"
                    )
                dependency_topics[dependency_id] = GeneratedTopic.from_dict(
                    row["content"]
                )
            work.rollback()
        node = CampaignTopicNode(
            topic_id=topic_id,
            title=str(topic_payload.get("title") or topic_id),
            category=str(topic_payload.get("category") or "lore"),
            dependencies=tuple(
                str(item) for item in topic_payload.get("dependencies") or ()
            ),
            generator_role=str(topic_payload.get("generator_role") or "world_forge"),
            required_before_launch=bool(
                topic_payload.get("required_before_launch", True)
            ),
            visibility=str(topic_payload.get("visibility") or "game_master_canon"),
            target_count=int(topic_payload.get("target_count") or 1),
            metadata=dict(topic_payload.get("metadata") or {}),
        )
        selected_generator = generator
        if selected_generator is None:
            from app.rpg_world_forge_provider import (
                build_production_world_forge_generator,
            )

            selected_generator = build_production_world_forge_generator()
        generated = selected_generator.generate(
            node,
            seed=int(dict(payload.get("settings") or {}).get("seed") or 0),
            campaign_context={
                **dict(payload.get("generation_context") or {}),
                "world_id": world_id,
                "draft_revision": int(payload.get("draft_revision") or 1),
                "topic_directives": dict(payload.get("directives") or {}),
            },
            dependency_topics=dependency_topics,
        )
        if generated.topic_id != topic_id:
            raise RuntimeError(
                f"world_topic_generator_returned:{generated.topic_id}:expected:{topic_id}"
            )
        content = generated.as_dict()
        content_hash = canonical_hash(content)
        provenance = {
            **dict(generated.provenance),
            "generation_fingerprint": str(payload.get("fingerprint") or ""),
            "directive_hash": str(payload.get("directive_hash") or ""),
            "entity_manifest_hash": str(payload.get("entity_manifest_hash") or ""),
            "job_id": str(job.get("id") or ""),
            "run_id": run_id,
        }
        with unit_of_work(db) as work:
            work.world_scenarios.put_topic(
                context,
                world_id=world_id,
                topic_id=topic_id,
                draft_revision=int(payload.get("draft_revision") or 1),
                source="ai",
                status="ready",
                content=content,
                directives=dict(payload.get("directives") or {}),
                dependency_hashes=dict(payload.get("dependency_hashes") or {}),
                input_hash=str(payload.get("input_hash") or ""),
                content_hash=content_hash,
                provenance=provenance,
            )
            completed = work.jobs.complete(
                context,
                job_id=str(job["id"]),
                worker_id=worker_id,
                lease_token=lease_token,
                output_refs=[
                    {
                        "world_id": world_id,
                        "draft_revision": int(payload.get("draft_revision") or 1),
                        "topic_id": topic_id,
                        "content_hash": content_hash,
                    }
                ],
                progress={
                    "current": 1,
                    "total": 1,
                    "message": "world topic completed",
                },
            )
            work.commit()
        run = reconcile_world_generation(run_id, database=db)
        return {
            "ok": True,
            "status": "completed",
            "job": completed,
            "topic_id": topic_id,
            "content_hash": content_hash,
            "run": run,
        }
    except Exception as exc:
        with unit_of_work(db) as work:
            failed = work.jobs.fail(
                context,
                job_id=str(job["id"]),
                worker_id=worker_id,
                lease_token=lease_token,
                error={"code": "world_topic_generation_failed", "message": str(exc)},
                retry_delay_seconds=1,
            )
            work.commit()
        if failed["status"] == "failed":
            reconcile_world_generation(run_id, database=db)
        return {
            "ok": False,
            "status": failed["status"],
            "job": failed,
            "topic_id": topic_id,
            "error": "world_topic_generation_failed",
            "detail": str(exc),
        }
