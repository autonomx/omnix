"""Truthful, orthogonal review and validation state for World Forge candidates."""
from __future__ import annotations

from typing import Any, Mapping

_FAILED_VALIDATION_STATUSES = {"blocked", "failed", "needs_review", "rejected"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _issues(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(str(item) for item in value if str(item)))


def validation_evidence(report: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return stable validation evidence without conflating it with review decisions."""

    current = _mapping(report)
    previous = _mapping(current.get("previous_validation"))
    evidence = previous or current
    issues = _issues(current.get("outstanding_findings"))
    if not issues:
        issues = _issues(evidence.get("issues"))
    reason_codes = _strings(current.get("outstanding_reason_codes"))
    if not reason_codes:
        reason_codes = _strings(evidence.get("reason_codes"))

    explicit_status = str(current.get("validation_status") or "").strip()
    source_status = str(evidence.get("status") or "").strip()
    failed = bool(
        issues
        or reason_codes
        or evidence.get("blocking")
        or source_status in _FAILED_VALIDATION_STATUSES
    )
    validation_status = explicit_status or ("failed" if failed else "passed")
    if validation_status not in {"passed", "failed", "not_run"}:
        validation_status = "failed" if failed else "passed"

    return {
        "validation_status": validation_status,
        "outstanding_findings": issues,
        "outstanding_reason_codes": reason_codes,
        "validation_blocking": bool(evidence.get("blocking") or failed),
        "source_validation_status": source_status,
    }


def accepted_review_report(
    previous_validation: Mapping[str, Any] | None,
    *,
    accepted_at: str,
    accepted_by: str = "local-game-master",
    waiver_reason: str = "",
) -> dict[str, Any]:
    """Record acceptance while preserving failed validation as an active waiver."""

    previous = _mapping(previous_validation)
    evidence = validation_evidence(previous)
    findings = list(evidence["outstanding_findings"])
    reason_codes = list(evidence["outstanding_reason_codes"])
    failed = evidence["validation_status"] == "failed"
    reason = str(waiver_reason or "").strip()
    if failed and not reason:
        reason = "Accepted by the Game Master after review with unresolved validation findings."

    return {
        "schema_version": "rpg_world_generation_review_v2",
        "status": "accepted",
        "review_decision": "accepted",
        "validation_status": evidence["validation_status"],
        "waiver_status": "active" if failed else "none",
        "blocking": False,
        "validation_blocking": bool(evidence["validation_blocking"]),
        "error_type": str(previous.get("error_type") or ""),
        "reason_codes": reason_codes,
        "issues": findings,
        "outstanding_reason_codes": reason_codes,
        "outstanding_findings": findings,
        "summary": (
            "Candidate accepted by the Game Master with unresolved findings retained."
            if failed
            else "Candidate accepted by the Game Master after validation passed."
        ),
        "accepted_at": accepted_at,
        "accepted_by": accepted_by,
        "waiver": {
            "status": "active" if failed else "none",
            "reason": reason,
            "accepted_by": accepted_by,
            "accepted_at": accepted_at,
        },
        "previous_validation": previous,
    }


def review_state(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project independent review, validation and waiver state for API/UI consumers."""

    row = _mapping(result)
    validation = _mapping(row.get("validation"))
    evidence = validation_evidence(validation)
    review_decision = str(validation.get("review_decision") or "").strip()
    if not review_decision and str(row.get("status") or "") == "accepted":
        review_decision = "accepted"
    waiver_status = str(validation.get("waiver_status") or "").strip()
    if not waiver_status:
        waiver_status = (
            "active"
            if review_decision == "accepted" and evidence["validation_status"] == "failed"
            else "none"
        )
    return {
        "review_decision": review_decision or "pending",
        "validation_status": evidence["validation_status"],
        "waiver_status": waiver_status,
        "outstanding_finding_count": len(evidence["outstanding_findings"]),
        "outstanding_findings": evidence["outstanding_findings"],
        "outstanding_reason_codes": evidence["outstanding_reason_codes"],
    }


__all__ = ["accepted_review_report", "review_state", "validation_evidence"]
