"""Quality audit compatible with machine-only structured fact records.

Typed structured facts are complete when their canonical object is present. Narrative
facts still require authored ``content``. This adapter removes only the obsolete
``content``-missing issue for machine facts and preserves every other quality check.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from .canon_audit import CanonAuditReport
from .world_forge_generation import GeneratedTopic
from .world_forge_quality import apply_world_forge_quality_audit as _apply

_STRUCTURED_SOURCES = {
    "profile_structured_fact_compiler_v1",
    "profile_structured_fact_compiler_v2",
}


def _complete_machine_fact_ids(
    topics: Iterable[GeneratedTopic],
) -> set[str]:
    result: set[str] = set()
    for topic in topics:
        for value in topic.facts:
            if not isinstance(value, Mapping):
                continue
            row = dict(value)
            machine = (
                str(row.get("authorship_class") or "") == "machine_structured"
                or str(row.get("source") or "") in _STRUCTURED_SOURCES
            )
            if not machine or row.get("object") in (None, ""):
                continue
            fact_id = str(row.get("id") or row.get("fact_id") or "")
            if fact_id:
                result.add(fact_id)
    return result


def apply_world_forge_quality_audit(
    topics: Iterable[GeneratedTopic],
    report: CanonAuditReport,
) -> CanonAuditReport:
    topic_list = tuple(topics)
    audited = _apply(topic_list, report)
    complete_machine_facts = _complete_machine_fact_ids(topic_list)
    removed = tuple(
        issue
        for issue in audited.issues
        if issue.code == "incomplete_generated_fact"
        and issue.item_id in complete_machine_facts
    )
    if not removed:
        return audited
    removed_ids = {(issue.code, issue.item_id, issue.message) for issue in removed}
    issues = tuple(
        issue
        for issue in audited.issues
        if (issue.code, issue.item_id, issue.message) not in removed_ids
    )
    checks = dict(audited.checks)
    checks["quality_errors"] = max(
        0,
        int(checks.get("quality_errors") or 0)
        - sum(1 for issue in removed if issue.severity == "error"),
    )
    checks["machine_structured_facts_without_prose"] = len(removed)
    return CanonAuditReport(
        passed=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        patches=audited.patches,
        checks=checks,
    )


__all__ = ["apply_world_forge_quality_audit"]
