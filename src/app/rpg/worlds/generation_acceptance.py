"""Promote retained World Forge candidates without relabelling their authorship."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.rpg_repository import canonical_json
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic

from .generation_authorship_runtime import generation_artifact
from .generation_authorship_signing import (
    attach_signed_human_authorship,
    require_signed_authorship,
)
from .generation_coordinator import (
    _graph_from_payload,
    _settings_from_payload,
    reconcile_world_generation,
)
from .generation_jobs import (
    canonical_generation_directives,
    canonical_hash,
    topic_generation_fingerprint,
)
from .lifecycle_service import require_world_writable

_ACCEPTED_DECISIONS = {"accept", "replace"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _accepted_candidate(
    candidate: Mapping[str, Any],
    *,
    original_candidate: Mapping[str, Any],
    run_id: str,
    topic_id: str,
    accepted_at: str,
    original_candidate_hash: str,
    edited: bool,
) -> tuple[dict[str, Any], str]:
    payload = dict(candidate)
    if str(payload.get("topic_id") or "") != topic_id:
        raise ValueError(
            f"world_generation_accept_topic_mismatch:{payload.get('topic_id')}:{topic_id}"
        )
    GeneratedTopic.from_dict(payload)

    artifact = generation_artifact(original_candidate)
    if edited:
        event_id = f"humanedit:{run_id}:{topic_id}:{accepted_at}"
        payload = attach_signed_human_authorship(
            payload,
            event_id=event_id,
            prior_candidate=original_candidate,
            edited_llm=bool(artifact),
        )
        source = "manual"
    else:
        require_signed_authorship(payload)
        source = "ai"

    provenance = _mapping(payload.get("provenance"))
    provenance.pop("generation_review", None)
    authoring = _mapping(provenance.get("authoring"))
    authoring.update(
        {
            "approved_at": accepted_at,
            "approved_by": "local-game-master",
            "edit_state": (
                "review_candidate_human_edited" if edited else "review_candidate_accepted"
            ),
            "authorship_preserved": True,
        }
    )
    provenance.update(
        {
            "authoring": authoring,
            "generation_status": "accepted",
            "generation_result_status": "accepted",
            "review_acceptance": {
                "run_id": run_id,
                "accepted_at": accepted_at,
                "original_candidate_hash": original_candidate_hash,
                "edited_before_acceptance": edited,
                "source_after_acceptance": source,
            },
        }
    )
    payload["provenance"] = provenance
    require_signed_authorship(payload)
    return payload, source


def _promotion_inputs(
    run: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    topic_id: str,
    candidate: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    graph = _graph_from_payload(_mapping(run.get("graph")))
    node = graph.node_map().get(topic_id)
    if node is None:
        raise ValueError(f"world_generation_accept_unknown_topic:{topic_id}")
    run_context = _mapping(run.get("context"))
    generation_context = _mapping(run_context.get("generation_context"))
    directives = canonical_generation_directives(
        _mapping(_mapping(run_context.get("topic_directives")).get(topic_id))
    )
    settings = _settings_from_payload(_mapping(run.get("settings")))
    dependency_hashes = {
        str(key): str(value)
        for key, value in _mapping(result.get("dependency_hashes")).items()
    }
    dependency_trust = _mapping(result.get("dependency_trust"))
    fingerprint, input_hash, directive_hash = topic_generation_fingerprint(
        node,
        normalized_topic_input={
            "generation_context": generation_context,
            "target_count": node.target_count,
            "visibility": node.visibility,
            "dependency_trust": dependency_trust,
        },
        dependency_hashes=dependency_hashes,
        directives=directives,
        entity_manifest_hash=str(run_context.get("entity_manifest_hash") or ""),
        settings=settings,
    )
    provenance = _mapping(candidate.get("provenance"))
    provenance.update(
        {
            "generation_fingerprint": fingerprint,
            "directive_hash": directive_hash,
            "run_id": str(run.get("run_id") or ""),
            "generation_result_status": "accepted",
        }
    )
    candidate["provenance"] = provenance
    return directives, dependency_hashes, input_hash, directive_hash, fingerprint


def _mark_result_accepted(
    work: Any,
    context: Any,
    *,
    run_id: str,
    topic_id: str,
    candidate: Mapping[str, Any],
    candidate_hash: str,
    previous_validation: Mapping[str, Any],
    accepted_at: str,
) -> None:
    validation = {
        "schema_version": "rpg_world_generation_review_v1",
        "status": "accepted",
        "blocking": False,
        "error_type": "",
        "reason_codes": [],
        "issues": [],
        "summary": "Candidate accepted by the Game Master with authorship preserved.",
        "accepted_at": accepted_at,
        "previous_validation": dict(previous_validation),
    }
    cursor = work.connection.execute(
        "UPDATE omnix_rpg_world_generation_topic_results "
        "SET status = 'accepted', candidate_jsonb = %s::jsonb, candidate_hash = %s, "
        "validation_jsonb = %s::jsonb, updated_at = CURRENT_TIMESTAMP "
        "WHERE workspace_id = %s AND run_id = %s AND topic_id = %s",
        (
            canonical_json(dict(candidate)),
            candidate_hash,
            canonical_json(validation),
            context.workspace_id,
            run_id,
            topic_id,
        ),
    )
    if int(getattr(cursor, "rowcount", 0) or 0) != 1:
        raise KeyError(f"world_generation_topic_result_not_found:{run_id}:{topic_id}")


def _promote(
    work: Any,
    context: Any,
    *,
    run: Mapping[str, Any],
    result: Mapping[str, Any],
    topic_id: str,
    candidate_override: Mapping[str, Any] | None,
    expected_candidate_hash: str,
    accepted_at: str,
) -> dict[str, Any]:
    if str(result.get("status") or "") != "needs_review":
        raise ValueError(f"world_generation_candidate_not_reviewable:{topic_id}")
    original_candidate = result.get("candidate")
    if not isinstance(original_candidate, Mapping):
        raise ValueError(f"world_generation_review_candidate_missing:{topic_id}")
    original_hash = str(result.get("candidate_hash") or "")
    if expected_candidate_hash and expected_candidate_hash != original_hash:
        raise ValueError(
            "world_generation_candidate_hash_conflict:"
            f"expected={expected_candidate_hash}:current={original_hash}"
        )
    source_candidate = candidate_override if candidate_override is not None else original_candidate
    edited = candidate_override is not None and dict(source_candidate) != dict(original_candidate)
    candidate, source = _accepted_candidate(
        source_candidate,
        original_candidate=original_candidate,
        run_id=str(run["run_id"]),
        topic_id=topic_id,
        accepted_at=accepted_at,
        original_candidate_hash=original_hash,
        edited=edited,
    )
    directives, dependency_hashes, input_hash, _directive_hash, _fingerprint = (
        _promotion_inputs(run, result, topic_id=topic_id, candidate=candidate)
    )
    promoted_hash = canonical_hash(candidate)
    work.world_scenarios.put_topic(
        context,
        world_id=str(run["world_id"]),
        topic_id=topic_id,
        draft_revision=int(run["draft_revision"]),
        source=source,
        status="ready",
        content=candidate,
        directives=directives,
        dependency_hashes=dependency_hashes,
        input_hash=input_hash,
        content_hash=promoted_hash,
        provenance=_mapping(candidate.get("provenance")),
    )
    _mark_result_accepted(
        work,
        context,
        run_id=str(run["run_id"]),
        topic_id=topic_id,
        candidate=candidate,
        candidate_hash=promoted_hash,
        previous_validation=_mapping(result.get("validation")),
        accepted_at=accepted_at,
    )
    return {
        "decision": "accept",
        "candidate_hash": original_hash,
        "promoted_hash": promoted_hash,
        "decided_at": accepted_at,
        "edited": edited,
        "source": source,
    }


def accept_world_generation_candidates(
    run_id: str,
    *,
    topic_ids: Sequence[str] = (),
    candidate_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    expected_candidate_hashes: Mapping[str, str] | None = None,
    database: Any | None = None,
) -> dict[str, Any]:
    """Accept selected retained candidates, preserving or explicitly changing origin."""

    context = bootstrap_local_tenant(database)
    overrides = dict(candidate_overrides or {})
    expected_hashes = dict(expected_candidate_hashes or {})
    accepted_at = datetime.now(timezone.utc).isoformat()
    with unit_of_work(database) as work:
        run = work.world_generation.get(context, run_id)
        if run is None:
            work.rollback()
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        if str(run.get("status") or "") not in {"review", "failed"}:
            work.rollback()
            raise ValueError("world_generation_accept_requires_completed_review")
        world = require_world_writable(work, context, str(run["world_id"]))
        if int(world["draft_revision"]) != int(run["draft_revision"]):
            work.rollback()
            raise ValueError(
                "world_generation_accept_revision_conflict:"
                f"run={run['draft_revision']}:current={world['draft_revision']}"
            )
        rows = work.world_generation.list_topic_results(context, run_id=run_id)
        by_topic = {str(row.get("topic_id") or ""): row for row in rows}
        requested = tuple(dict.fromkeys(str(value) for value in topic_ids if str(value)))
        selected = requested or tuple(
            topic_id
            for topic_id, row in by_topic.items()
            if str(row.get("status") or "") == "needs_review"
            and isinstance(row.get("candidate"), Mapping)
        )
        if not selected:
            work.rollback()
            raise ValueError("world_generation_accept_scope_empty")
        unknown = sorted(set(selected) - set(by_topic))
        if unknown:
            work.rollback()
            raise KeyError("world_generation_topic_result_not_found:" + ",".join(unknown))
        plan = _mapping(run.get("plan"))
        decisions = {
            str(key): dict(value)
            for key, value in _mapping(plan.get("review_decisions")).items()
            if isinstance(value, Mapping)
        }
        already_decided = sorted(
            topic_id
            for topic_id in selected
            if str(_mapping(decisions.get(topic_id)).get("decision") or "")
            in _ACCEPTED_DECISIONS | {"keep"}
        )
        if already_decided:
            work.rollback()
            raise ValueError(
                "world_generation_candidate_already_decided:" + ",".join(already_decided)
            )
        graph = _graph_from_payload(_mapping(run.get("graph")))
        selected_set = set(selected)
        ordered = [
            node.topic_id
            for node in graph.topological_order()
            if node.topic_id in selected_set
        ]
        decision_rows: dict[str, dict[str, Any]] = {}
        for topic_id in ordered:
            decision_rows[topic_id] = _promote(
                work,
                context,
                run=run,
                result=by_topic[topic_id],
                topic_id=topic_id,
                candidate_override=overrides.get(topic_id),
                expected_candidate_hash=str(expected_hashes.get(topic_id) or ""),
                accepted_at=accepted_at,
            )
        decisions.update(decision_rows)
        plan["review_decisions"] = decisions
        work.world_generation.update(context, run_id=run_id, plan=plan)
        work.commit()
    reconciled = reconcile_world_generation(run_id, database=database)
    return {
        "ok": True,
        "run_id": run_id,
        "accepted_topic_ids": ordered,
        "decisions": decision_rows,
        "run": reconciled,
    }


def accept_world_generation_candidate(
    run_id: str,
    topic_id: str,
    *,
    candidate: Mapping[str, Any] | None = None,
    expected_candidate_hash: str = "",
    database: Any | None = None,
) -> dict[str, Any]:
    return accept_world_generation_candidates(
        run_id,
        topic_ids=(topic_id,),
        candidate_overrides={topic_id: candidate} if candidate is not None else {},
        expected_candidate_hashes={topic_id: expected_candidate_hash},
        database=database,
    )


__all__ = [
    "accept_world_generation_candidate",
    "accept_world_generation_candidates",
]
