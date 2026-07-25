"""Fail-closed publication guard for single-pass World Forge runs."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Mapping

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .generation_publication import publish_world_generation as _publish_legacy

_NON_GENERATION_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}


class WorldGenerationRequiresReviewError(ValueError):
    def __init__(self, report: Mapping[str, Any]) -> None:
        self.report = dict(report)
        super().__init__(
            "world_generation_requires_review:"
            + json.dumps(self.report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )


def _reason_counts(results: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for result in results:
        for code in dict(result.get("validation") or {}).get("reason_codes") or ():
            counts[str(code)] += 1
    return dict(sorted(counts.items()))


def _generation_nodes(run: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    graph = dict(run.get("graph") or {})
    return tuple(
        dict(row)
        for row in graph.get("nodes") or ()
        if isinstance(row, Mapping)
        and str(row.get("category") or "lore") not in _NON_GENERATION_CATEGORIES
        and str(row.get("topic_id") or "")
    )


def _review_decisions(run: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    lineage = dict(run.get("lineage") or {})
    value = lineage.get("review_decisions")
    if not isinstance(value, Mapping):
        value = dict(run.get("plan") or {}).get("review_decisions")
    return {
        str(key): dict(row)
        for key, row in dict(value or {}).items()
        if isinstance(row, Mapping)
    }


def publication_review_report(
    run_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        run = work.world_generation.get(context, run_id)
        if run is None:
            work.rollback()
            raise KeyError(f"world_generation_run_not_found:{run_id}")
        results = work.world_generation.list_topic_results(context, run_id=run_id)
        topics = work.world_generation.list_topics(
            context,
            world_id=str(run["world_id"]),
            draft_revision=int(run["draft_revision"]),
        )
        work.rollback()

    targets = tuple(
        str(value)
        for value in dict(run.get("context") or {}).get("target_topic_ids") or ()
    )
    nodes = _generation_nodes(run)
    graph_topic_ids = tuple(str(node["topic_id"]) for node in nodes)
    graph_topic_set = set(graph_topic_ids)
    by_topic = {str(row.get("topic_id") or ""): row for row in results}
    authoring = {str(row.get("topic_id") or ""): row for row in topics}
    decisions = _review_decisions(run)

    missing = [topic_id for topic_id in targets if topic_id not in by_topic]
    replaced = {
        topic_id
        for topic_id, decision in decisions.items()
        if str(decision.get("decision") or "") == "replace"
    }
    kept = sorted(
        topic_id
        for topic_id, decision in decisions.items()
        if str(decision.get("decision") or "") == "keep"
    )
    pending_decisions = sorted(
        topic_id
        for topic_id in targets
        if "manual_retry_decision_required"
        in set(dict(by_topic.get(topic_id, {}).get("validation") or {}).get("reason_codes") or ())
        and topic_id not in decisions
    )
    flagged = [
        topic_id
        for topic_id in targets
        if str(by_topic.get(topic_id, {}).get("status") or "") == "needs_review"
        and topic_id not in replaced
    ]
    failed = [
        topic_id
        for topic_id in targets
        if str(by_topic.get(topic_id, {}).get("status") or "") == "failed"
    ]
    blocked = [
        topic_id
        for topic_id in targets
        if str(by_topic.get(topic_id, {}).get("status") or "") == "blocked"
    ]

    hash_mismatches: list[str] = []
    accepted_effective: list[str] = []
    for topic_id in targets:
        result = by_topic.get(topic_id)
        if result is None:
            continue
        decision = decisions.get(topic_id, {})
        if topic_id in replaced:
            expected_hash = str(decision.get("promoted_hash") or "")
        elif str(result.get("status") or "") == "accepted":
            expected_hash = str(result.get("candidate_hash") or "")
        else:
            continue
        topic = authoring.get(topic_id)
        if (
            not expected_hash
            or topic is None
            or str(topic.get("status") or "") != "ready"
            or str(topic.get("content_hash") or "") != expected_hash
        ):
            hash_mismatches.append(topic_id)
        else:
            accepted_effective.append(topic_id)

    missing_authoring = sorted(
        topic_id
        for topic_id in graph_topic_ids
        if topic_id not in authoring
        or str(authoring[topic_id].get("status") or "") != "ready"
    )
    dependency_mismatches: list[dict[str, str]] = []
    for node in nodes:
        topic_id = str(node["topic_id"])
        topic = authoring.get(topic_id)
        if topic is None or str(topic.get("status") or "") != "ready":
            continue
        if str(topic.get("source") or "") != "ai":
            continue
        stored_hashes = {
            str(key): str(value)
            for key, value in dict(topic.get("dependency_hashes") or {}).items()
        }
        for dependency_id in node.get("dependencies") or ():
            dependency_id = str(dependency_id)
            if dependency_id not in graph_topic_set:
                continue
            current = authoring.get(dependency_id)
            current_hash = str(current.get("content_hash") or "") if current else ""
            stored_hash = stored_hashes.get(dependency_id, "")
            if not current_hash or stored_hash != current_hash:
                dependency_mismatches.append(
                    {
                        "topic_id": topic_id,
                        "dependency_id": dependency_id,
                        "stored_hash": stored_hash,
                        "current_hash": current_hash,
                    }
                )

    blockers = (
        set(missing)
        | set(flagged)
        | set(failed)
        | set(blocked)
        | set(hash_mismatches)
        | set(kept)
        | set(pending_decisions)
        | set(missing_authoring)
        | {row["topic_id"] for row in dependency_mismatches}
    )
    return {
        "schema_version": "rpg_world_generation_publication_review_v2",
        "run_id": run_id,
        "world_id": str(run["world_id"]),
        "draft_revision": int(run["draft_revision"]),
        "publishable": not blockers and bool(targets) and bool(graph_topic_ids),
        "target_topic_ids": list(targets),
        "graph_topic_ids": list(graph_topic_ids),
        "accepted_topic_ids": sorted(accepted_effective),
        "missing_topic_ids": missing,
        "flagged_topic_ids": flagged,
        "failed_topic_ids": failed,
        "blocked_topic_ids": blocked,
        "pending_decision_topic_ids": pending_decisions,
        "kept_previous_topic_ids": kept,
        "hash_mismatch_topic_ids": sorted(hash_mismatches),
        "missing_authoring_topic_ids": missing_authoring,
        "dependency_hash_mismatches": dependency_mismatches,
        "reason_counts": _reason_counts(results),
    }


def publish_world_generation(
    run_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    report = publication_review_report(run_id, database=database)
    if not report["publishable"]:
        raise WorldGenerationRequiresReviewError(report)
    return _publish_legacy(run_id, database=database)


__all__ = [
    "WorldGenerationRequiresReviewError",
    "publication_review_report",
    "publish_world_generation",
]
