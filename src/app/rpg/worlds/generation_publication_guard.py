"""Fail-closed publication guard for single-pass World Forge runs."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Mapping

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .generation_publication import publish_world_generation as _publish_legacy


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
    by_topic = {str(row.get("topic_id") or ""): row for row in results}
    authoring = {str(row.get("topic_id") or ""): row for row in topics}
    missing = [topic_id for topic_id in targets if topic_id not in by_topic]
    flagged = [
        topic_id for topic_id in targets
        if str(by_topic.get(topic_id, {}).get("status") or "") == "needs_review"
    ]
    failed = [
        topic_id for topic_id in targets
        if str(by_topic.get(topic_id, {}).get("status") or "") == "failed"
    ]
    blocked = [
        topic_id for topic_id in targets
        if str(by_topic.get(topic_id, {}).get("status") or "") == "blocked"
    ]
    hash_mismatches = []
    for topic_id in targets:
        result = by_topic.get(topic_id)
        if result is None or str(result.get("status") or "") != "accepted":
            continue
        topic = authoring.get(topic_id)
        if (
            topic is None
            or str(topic.get("status") or "") != "ready"
            or str(topic.get("content_hash") or "")
            != str(result.get("candidate_hash") or "")
        ):
            hash_mismatches.append(topic_id)
    blockers = set(missing) | set(flagged) | set(failed) | set(blocked) | set(hash_mismatches)
    return {
        "schema_version": "rpg_world_generation_publication_review_v1",
        "run_id": run_id,
        "world_id": str(run["world_id"]),
        "draft_revision": int(run["draft_revision"]),
        "publishable": not blockers and bool(targets),
        "target_topic_ids": list(targets),
        "accepted_topic_ids": [
            topic_id for topic_id in targets
            if str(by_topic.get(topic_id, {}).get("status") or "") == "accepted"
        ],
        "missing_topic_ids": missing,
        "flagged_topic_ids": flagged,
        "failed_topic_ids": failed,
        "blocked_topic_ids": blocked,
        "hash_mismatch_topic_ids": hash_mismatches,
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
