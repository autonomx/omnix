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
from .profile_authoring import require_approved_profile


def _execution_summary(run: Mapping[str, Any]) -> dict[str, Any]:
    plan = dict(run.get("plan") or {})
    progress = dict(run.get("progress") or {})
    return {
        "queued_topic_ids": list(plan.get("new_topic_ids") or ()),
        "reused_topic_ids": list(plan.get("reusable_topic_ids") or ()),
        "protected_topic_ids": list(plan.get("protected_topic_ids") or ()),
        "target_topic_ids": list(plan.get("topic_ids") or ()),
        "queued_count": len(plan.get("new_job_ids") or ()),
        "reused_count": len(plan.get("reusable_topic_ids") or ()),
        "protected_count": len(plan.get("protected_topic_ids") or ()),
        "active_count": len(progress.get("active_topic_ids") or ()),
    }


def _require_run_profile_matches_approval(
    run: Mapping[str, Any],
    graph: Any,
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject retries after profile drift or approval invalidation."""

    run_context = dict(run.get("context") or {})
    generation_context = dict(run_context.get("generation_context") or {})
    graph_metadata = dict(getattr(graph, "metadata", {}) or {})
    run_profile_hash = str(
        generation_context.get("approved_profile_hash")
        or generation_context.get("resolved_profile_hash")
        or graph_metadata.get("resolved_profile_hash")
        or ""
    )
    approved_hash = str(approval.get("approved_profile_hash") or "")
    if not run_profile_hash or run_profile_hash != approved_hash:
        raise ValueError("world_profile_approval_hash_mismatch")
    return generation_context


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

    profile_approval = require_approved_profile(world)
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
    generation_context = _require_run_profile_matches_approval(
        failed_run,
        graph,
        profile_approval,
    )
    targets, _ignored_forced, normalized_scope = resolve_generation_scope(
        graph,
        scope={"mode": "failed"},
        strategy="force",
        topic_rows=topics,
        latest_run=failed_run,
        replace_locked=False,
    )
    run_context = dict(failed_run.get("context") or {})
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
            "approved_profile_hash": profile_approval["approved_profile_hash"],
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
        tenant_context=context,
    )
    worker_started = (
        kick_world_generation_worker(
            database=database,
            provider_route=settings.provider_route,
        )
        if kick_worker
        else False
    )
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
        "execution_summary": _execution_summary(retry_run),
        "resolved_route": {
            "provider": settings.provider_route,
            "model": settings.model,
            "source": "retry_durable_run",
        },
    }


def continue_world_generation(
    run_id: str,
    *,
    database: Any | None = None,
    kick_worker: bool = True,
    diagnostic_id: str | None = None,
) -> dict[str, Any]:
    """Continue a failed generation run without discarding completed topics.

    A failed-topic retry deliberately limits its target to the failed dependency
    closure. Continuing restores the original *full* target graph. The
    coordinator reuses every topic whose original inputs are still valid, forces
    the topics that failed, and schedules downstream topics that were never
    reached.
    """

    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        previous_run = work.world_generation.get(context, run_id)
        if previous_run is None:
            work.rollback()
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        world_id = str(previous_run["world_id"])
        world = require_world_writable(work, context, world_id)
        topics = work.world_library.list_topics(context, world_id)
        work.rollback()

    profile_approval = require_approved_profile(world)
    previous_revision = int(previous_run["draft_revision"])
    current_revision = int(world["draft_revision"])
    if previous_revision != current_revision:
        raise ValueError(
            "world_generation_continue_revision_conflict:"
            f"run={previous_revision}:current={current_revision}"
        )
    if str(previous_run.get("status") or "") != "failed":
        raise ValueError("world_generation_continue_not_failed")

    progress = dict(previous_run.get("progress") or {})
    failed_topic_ids = tuple(
        dict.fromkeys(
            str(topic_id)
            for topic_id in progress.get("failed_topic_ids") or ()
            if str(topic_id)
        )
    )
    graph = _graph_from_payload(dict(previous_run.get("graph") or {}))
    generation_context = _require_run_profile_matches_approval(
        previous_run,
        graph,
        profile_approval,
    )
    targets, _ignored_forced, normalized_scope = resolve_generation_scope(
        graph,
        scope={"mode": "full"},
        strategy="reuse_unchanged",
        topic_rows=topics,
        latest_run=previous_run,
        replace_locked=False,
    )
    topic_status = {
        str(topic.get("topic_id") or ""): str(topic.get("status") or "")
        for topic in topics
    }
    remaining_topic_ids = tuple(
        topic_id
        for topic_id in targets
        if topic_id in failed_topic_ids or topic_status.get(topic_id) != "ready"
    )
    if not remaining_topic_ids:
        raise ValueError("generation_scope_empty:continue")

    run_context = dict(previous_run.get("context") or {})
    topic_directives = {
        str(topic_id): dict(value)
        for topic_id, value in dict(run_context.get("topic_directives") or {}).items()
        if isinstance(value, Mapping)
    }
    settings = _settings_from_payload(dict(previous_run.get("settings") or {}))
    continue_scope = {
        **normalized_scope,
        "mode": "continue",
        "continue_of_run_id": run_id,
        "failed_topic_ids": list(failed_topic_ids),
        "remaining_topic_ids": list(remaining_topic_ids),
    }

    log_world_generation_event(
        "world_generation.continue_requested",
        diagnostic_id=diagnostic_id,
        world_id=world_id,
        run_id=run_id,
        fields={
            "draft_revision": previous_revision,
            "failed_topic_ids": failed_topic_ids,
            "remaining_topic_ids": remaining_topic_ids,
            "resolved_topic_ids": targets,
            "provider_route": settings.provider_route,
            "model": settings.model,
            "approved_profile_hash": profile_approval["approved_profile_hash"],
        },
    )
    continuation_run = start_world_generation(
        world_id=world_id,
        draft_revision=previous_revision,
        graph=graph,
        generation_context=generation_context,
        topic_directives=topic_directives,
        entity_manifest_hash=str(run_context.get("entity_manifest_hash") or ""),
        settings=settings,
        target_topic_ids=targets,
        forced_topic_ids=failed_topic_ids,
        scope=continue_scope,
        strategy="reuse_unchanged",
        database=database,
        tenant_context=context,
    )
    worker_started = (
        kick_world_generation_worker(
            database=database,
            provider_route=settings.provider_route,
        )
        if kick_worker
        else False
    )
    log_world_generation_event(
        "world_generation.continue_started",
        diagnostic_id=diagnostic_id,
        world_id=world_id,
        run_id=str(continuation_run["run_id"]),
        fields={
            "continue_of_run_id": run_id,
            "remaining_topic_ids": remaining_topic_ids,
            "worker_started": worker_started,
            "status": continuation_run.get("status"),
        },
    )
    return {
        "ok": True,
        "run": continuation_run,
        "worker_started": worker_started,
        "scope": continue_scope,
        "continue_of_run_id": run_id,
        "diagnostic_id": diagnostic_id,
        "execution_summary": _execution_summary(continuation_run),
        "resolved_route": {
            "provider": settings.provider_route,
            "model": settings.model,
            "source": "continue_durable_run",
        },
    }
