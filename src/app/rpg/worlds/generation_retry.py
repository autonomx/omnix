"""Exact-run retry for failed reusable-world generation topics."""
from __future__ import annotations

from typing import Any, Mapping

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .generation_coordinator import (
    _graph_from_payload,
    _settings_from_payload,
    start_world_generation,
)
from .generation_diagnostics import log_world_generation_event
from .generation_scope import resolve_generation_scope
from .generation_worker import kick_world_generation_worker
from .lifecycle_service import require_world_writable


def retry_failed_world_generation(
    run_id: str,
    *,
    database: Any | None = None,
    kick_worker: bool = True,
    diagnostic_id: str | None = None,
) -> dict[str, Any]:
    """Retry terminally failed topics with the original graph and provider settings.

    Rebuilding a failed retry from the browser's current defaults can change depth,
    prompt versions, model routing, or dependency fingerprints. This operation uses
    the durable failed run as the complete source of truth and forces only the failed
    topics while reusing their already-completed dependencies.
    """

    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        failed_run = work.world_generation.get(context, run_id)
        if failed_run is None:
            work.rollback()
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        world_id = str(failed_run["world_id"])
        world = require_world_writable(work, context, world_id)
        topics = work.world_library.list_topics(context, world_id)
        work.rollback()

    failed_revision = int(failed_run["draft_revision"])
    current_revision = int(world["draft_revision"])
    if failed_revision != current_revision:
        raise ValueError(
            "world_generation_retry_revision_conflict:"
            f"run={failed_revision}:current={current_revision}"
        )

    progress = dict(failed_run.get("progress") or {})
    failed_topic_ids = tuple(
        dict.fromkeys(
            str(topic_id)
            for topic_id in progress.get("failed_topic_ids") or ()
            if str(topic_id)
        )
    )
    if not failed_topic_ids:
        raise ValueError("generation_scope_empty:failed")

    graph = _graph_from_payload(dict(failed_run.get("graph") or {}))
    targets, _ignored_forced, normalized_scope = resolve_generation_scope(
        graph,
        scope={"mode": "failed"},
        strategy="force",
        topic_rows=topics,
        latest_run=failed_run,
        replace_locked=False,
    )
    run_context = dict(failed_run.get("context") or {})
    generation_context = dict(run_context.get("generation_context") or {})
    topic_directives = {
        str(topic_id): dict(value)
        for topic_id, value in dict(run_context.get("topic_directives") or {}).items()
        if isinstance(value, Mapping)
    }
    settings = _settings_from_payload(dict(failed_run.get("settings") or {}))
    retry_scope = {
        **normalized_scope,
        "retry_of_run_id": run_id,
        "failed_topic_ids": list(failed_topic_ids),
    }

    log_world_generation_event(
        "world_generation.retry_requested",
        diagnostic_id=diagnostic_id,
        world_id=world_id,
        run_id=run_id,
        fields={
            "draft_revision": failed_revision,
            "failed_topic_ids": failed_topic_ids,
            "resolved_topic_ids": targets,
            "provider_route": settings.provider_route,
            "model": settings.model,
            "generator_version": settings.generator_version,
            "prompt_version": settings.prompt_version,
            "max_attempts": settings.max_attempts,
        },
    )

    retry_run = start_world_generation(
        world_id=world_id,
        draft_revision=failed_revision,
        graph=graph,
        generation_context=generation_context,
        topic_directives=topic_directives,
        entity_manifest_hash=str(run_context.get("entity_manifest_hash") or ""),
        settings=settings,
        target_topic_ids=targets,
        forced_topic_ids=failed_topic_ids,
        scope=retry_scope,
        strategy="force",
        database=database,
    )
    worker_started = kick_world_generation_worker(database=database) if kick_worker else False
    log_world_generation_event(
        "world_generation.retry_started",
        diagnostic_id=diagnostic_id,
        world_id=world_id,
        run_id=str(retry_run["run_id"]),
        fields={
            "retry_of_run_id": run_id,
            "failed_topic_ids": failed_topic_ids,
            "worker_started": worker_started,
            "status": retry_run.get("status"),
        },
    )
    return {
        "ok": True,
        "run": retry_run,
        "worker_started": worker_started,
        "scope": retry_scope,
        "retry_of_run_id": run_id,
        "diagnostic_id": diagnostic_id,
    }
