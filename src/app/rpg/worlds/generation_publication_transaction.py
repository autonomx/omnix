"""Fail-closed transaction policy for certified World Forge publication."""
from __future__ import annotations

import json
from typing import Any, Mapping

_BLOCKING_PROGRESS_FIELDS = (
    "flagged_topic_ids",
    "failed_topic_ids",
    "blocked_topic_ids",
    "pending_decision_topic_ids",
    "kept_previous_topic_ids",
    "potentially_stale_topic_ids",
)
_CERTIFICATION_REPORT_FIELDS = (
    "strict_integrity",
    "profile_reference_integrity",
    "profile_dossier_policy",
)


class WorldGenerationCertificationError(ValueError):
    """Raised before durable writes when a release is not certifiable."""

    def __init__(self, report: Mapping[str, Any]) -> None:
        self.report = dict(report)
        super().__init__(
            "world_generation_certification_failed:"
            + json.dumps(self.report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )


def _values(progress: Mapping[str, Any], field: str) -> list[str]:
    return sorted(
        {
            str(value)
            for value in progress.get(field) or ()
            if str(value)
        }
    )


def publication_transaction_report(
    run: Mapping[str, Any],
    certification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe every condition that must hold before revision/release inserts."""

    progress = dict(run.get("progress") or {})
    blockers = {
        field: _values(progress, field)
        for field in _BLOCKING_PROGRESS_FIELDS
        if _values(progress, field)
    }
    reasons: list[str] = []
    if str(run.get("status") or "") != "review":
        reasons.append("run_not_in_review")
    if bool(progress.get("publication_blocked")):
        reasons.append("progress_publication_blocked")
    if blockers:
        reasons.append("unresolved_topic_blockers")

    certification_payload = dict(certification or {})
    report_failures: dict[str, Mapping[str, Any]] = {}
    if certification is not None:
        if not bool(certification_payload.get("launch_ready")):
            reasons.append("release_not_launch_ready")
        missing = [
            str(value)
            for value in certification_payload.get("missing_requirements") or ()
            if str(value)
        ]
        if missing:
            reasons.append("release_requirements_missing")
        consistency = certification_payload.get("consistency_report")
        if isinstance(consistency, Mapping) and not bool(consistency.get("passed")):
            report_failures["consistency_report"] = dict(consistency)
        for field in _CERTIFICATION_REPORT_FIELDS:
            value = certification_payload.get(field)
            if isinstance(value, Mapping) and not bool(value.get("passed")):
                report_failures[field] = dict(value)
        if report_failures:
            reasons.append("certification_report_failed")
    else:
        missing = []

    return {
        "schema_version": "rpg_world_publication_transaction_v1",
        "run_id": str(run.get("run_id") or ""),
        "world_id": str(run.get("world_id") or ""),
        "publishable": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "topic_blockers": blockers,
        "missing_requirements": missing,
        "failed_reports": report_failures,
        "launch_ready": (
            bool(certification_payload.get("launch_ready"))
            if certification is not None
            else None
        ),
    }


def require_publication_run_ready(run: Mapping[str, Any]) -> None:
    report = publication_transaction_report(run)
    if not report["publishable"]:
        raise WorldGenerationCertificationError(report)


def require_certified_publication(
    run: Mapping[str, Any],
    certification: Mapping[str, Any],
) -> None:
    report = publication_transaction_report(run, certification)
    if not report["publishable"]:
        raise WorldGenerationCertificationError(report)


__all__ = [
    "WorldGenerationCertificationError",
    "publication_transaction_report",
    "require_certified_publication",
    "require_publication_run_ready",
]
