"""Explicit Game Master retry for reviewed World Forge topic candidates."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

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
        "flagged_count": len(progress.get("flagged_topic_ids") or ()),
        "failed_count": len(progress.get("failed_topic_ids") or ()),
        "blocked_count": len(progress.get("blocked_topic_ids") or ()),
    }


def _require_run_profile_matches_approval(
    run: Mapping[str, Any],
    graph: Any,
    approval: Mapping[str, Any],
) -> dict[str, Any]:
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


def _reviewable_topic_ids(run: Mapping[str, Any]) -> tuple[str, ...]:
    progress = dict(run.get("progress") or {})
    return tuple(
        dict.fromkeys(
            str(topic_id)
            for key in (
                "flagged_topic_ids",
                "failed_topic_ids",
                "blocked_topic_ids",
            )
            for topic_id in progress.get(key) or ()
            if str(topic_id)
        )
    )


def _manual_retry_directives(
    original: Mapping[str, Mapping[str, Any]],
    *,
    selected_topic_ids: Sequence[str],
    previous_results: Mapping[str, Mapping[str, Any]],
    retry_scopes: Mapping[str, Mapping[str, Any]],
    parent_run_id: str,
) -> dict[str, dict[str, Any]]:
    directives = {
        str(topic_id): dict(value)
        for topic_id, value in original.items()
        if isinstance(value, Mapping)
    }
    for topic_id in selected_topic_ids:
        previous = dict(previous_results.get(topic_id) or {})
        validation = dict(previous.get("validation") or {})
        requested = dict(retry_scopes.get(topic_id) or {})
        prior_candidate = previous.get("candidate")
        directives[topic_id] = {
            **directives.get(topic_id, {}),
            "manual_retry": {
                "parent_run_id": parent_run_id,
                "prior_status": str(previous.get("status") or ""),
                "prior_candidate_hash": str(previous.get("candidate_hash") or ""),
                "prior_candidate": (
                    dict(prior_candidate)
                    if isinstance(prior_candidate, Mapping)
                    else None
                ),
                "reason_codes": list(validation.get("reason_codes") or ()),
                "issues": list(validation.get("issues") or ()),
                "scope": str(requested.get("scope") or "topic"),
                "entity_ids": list(requested.get("entity_ids") or ()),
                "fields": list(requested.get("fields") or ()),
                "instructions": list(requested.get("instructions") or ()),
                "required_behavior": (
                    "Create a new complete candidate for the selected scope. Preserve "
                    "stable IDs and valid unaffected canon. Resolve the listed validation "
                    "issues without inventing unresolved references."
                ),
            },
        }
    return directives


def _pin_parent_run(
    child_run_id: str,
    parent_run: Mapping[str, Any],
    *,
    database: Any | None,
) -> None:
    """Pin retry lineage to the explicitly selected parent, not merely latest run."""

    context = bootstrap_local_tenant(database)
    parent_run_id = str(parent_run["run_id"])
    parent_lineage = dict(parent_run.get("lineage") or {})
    root_run_id = str(parent_lineage.get("root_run_id") or parent_run_id)
    lineage = {
        "root_run_id": root_run_id,
        "parent_run_id": parent_run_id,
        "parent_draft_revision": int(parent_run["draft_revision"]),
        "draft_revision": int(parent_run["draft_revision"]),
        "manual_retry": True,
    }
    with unit_of_work(database) as work:
        work.connection.execute(
            "UPDATE omnix_rpg_world_generation_runs "
            "SET parent_run_id = %s, lineage_jsonb = %s::jsonb, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE workspace_id = %s AND run_id = %s",
            (
                parent_run_id,
                json.dumps(lineage, sort_keys=True),
                context.workspace_id,
                child_run_id,
            ),
        )
        work.commit()


def retry_failed_world_generation(
    run_id: str,
    *,
    selected_topic_ids: Sequence[str] = (),
    retry_scopes: Mapping[str, Mapping[str, Any]] | None = None,
    database: Any | None = None,
    kick_worker: bool = True,
    diagnostic_id: str | None = None,
) -> dict[str, Any]:
    """Explicitly retry selected review outcomes using the original durable settings.

    Despite the legacy function name, this handles ``needs_review``, ``failed``, and
    ``blocked`` results. Nothing is scheduled without this Game Master action.
    """

    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        parent_run = work.world_generation.get(context, run_id)
        if parent_run is None:
            work.rollback()
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        world_id = str(parent_run["world_id"])
        world = require_world_writable(work, context, world_id)
        topics = work.world_library.list_topics(context, world_id)
        result_rows = work.world_generation.list_topic_results(context, run_id=run_id)
        work.rollback()

    if str(parent_run.get("status") or "") not in {"review", "failed"}:
        raise ValueError("world_generation_retry_requires_completed_review")
    profile_approval = require_approved_profile(world)
    draft_revision = int(parent_run["draft_revision"])
    if draft_revision != int(world["draft_revision"]):
        raise ValueError(
            "world_generation_retry_revision_conflict:"
            f"run={draft_revision}:current={world['draft_revision']}"
        )

    reviewable = _reviewable_topic_ids(parent_run)
    requested = tuple(
        dict.fromkeys(str(value) for value in selected_topic_ids if str(value))
    )
    if requested:
        invalid = sorted(set(requested) - set(reviewable))
        if invalid:
            raise ValueError("generation_topics_not_reviewable:" + ",".join(invalid))
    selected = requested or reviewable
    if not selected:
        raise ValueError("generation_scope_empty:review")

    graph = _graph_from_payload(dict(parent_run.get("graph") or {}))
    generation_context = _require_run_profile_matches_approval(
        parent_run,
        graph,
        profile_approval,
    )
    targets, forced, normalized_scope = resolve_generation_scope(
        graph,
        scope={"mode": "review", "topic_ids": list(selected)},
        strategy="force",
        topic_rows=topics,
        latest_run=parent_run,
        replace_locked=False,
    )
    previous_results = {
        str(row.get("topic_id") or ""): row for row in result_rows
    }
    run_context = dict(parent_run.get("context") or {})
    topic_directives = _manual_retry_directives(
        {
            str(topic_id): dict(value)
            for topic_id, value in dict(run_context.get("topic_directives") or {}).items()
            if isinstance(value, Mapping)
        },
        selected_topic_ids=forced,
        previous_results=previous_results,
        retry_scopes=dict(retry_scopes or {}),
        parent_run_id=run_id,
    )
    settings = _settings_from_payload(dict(parent_run.get("settings") or {}))
    retry_scope = {
        **normalized_scope,
        "mode": "review",
        "retry_of_run_id": run_id,
        "selected_topic_ids": list(forced),
        "previous_results": {
            topic_id: {
                "status": str(previous_results.get(topic_id, {}).get("status") or ""),
                "candidate_hash": str(
                    previous_results.get(topic_id, {}).get("candidate_hash") or ""
                ),
            }
            for topic_id in forced
        },
    }
    generation_context = {
        **generation_context,
        "manual_retry_of_run_id": run_id,
        "manual_retry_topic_ids": list(forced),
    }

    log_world_generation_event(
        "world_generation.manual_retry_requested",
        diagnostic_id=diagnostic_id,
        world_id=world_id,
        run_id=run_id,
        fields={
            "draft_revision": draft_revision,
            "selected_topic_ids": forced,
            "resolved_topic_ids": targets,
            "provider_route": settings.provider_route,
            "model": settings.model,
            "approved_profile_hash": profile_approval["approved_profile_hash"],
        },
    )
    child_run = start_world_generation(
        world_id=world_id,
        draft_revision=draft_revision,
        graph=graph,
        generation_context=generation_context,
        topic_directives=topic_directives,
        entity_manifest_hash=str(run_context.get("entity_manifest_hash") or ""),
        settings=settings,
        target_topic_ids=targets,
        forced_topic_ids=forced,
        scope=retry_scope,
        strategy="force",
        database=database,
        tenant_context=context,
    )
    _pin_parent_run(str(child_run["run_id"]), parent_run, database=database)
    worker_started = (
        kick_world_generation_worker(
            database=database,
            provider_route=settings.provider_route,
        )
        if kick_worker
        else False
    )
    log_world_generation_event(
        "world_generation.manual_retry_started",
        diagnostic_id=diagnostic_id,
        world_id=world_id,
        run_id=str(child_run["run_id"]),
        fields={
            "retry_of_run_id": run_id,
            "selected_topic_ids": forced,
            "worker_started": worker_started,
            "status": child_run.get("status"),
        },
    )
    return {
        "ok": True,
        "run": child_run,
        "worker_started": worker_started,
        "scope": retry_scope,
        "retry_of_run_id": run_id,
        "diagnostic_id": diagnostic_id,
        "execution_summary": _execution_summary(child_run),
        "resolved_route": {
            "provider": settings.provider_route,
            "model": settings.model,
            "source": "manual_retry_durable_run",
        },
    }


def continue_world_generation(
    run_id: str,
    *,
    database: Any | None = None,
    kick_worker: bool = True,
    diagnostic_id: str | None = None,
) -> dict[str, Any]:
    """Compatibility alias for explicitly retrying every non-accepted result."""

    result = retry_failed_world_generation(
        run_id,
        database=database,
        kick_worker=kick_worker,
        diagnostic_id=diagnostic_id,
    )
    return {
        **result,
        "continue_of_run_id": run_id,
    }
