"""Evidence partitioning and stricter release gates for Desktop Companion rollout."""
from __future__ import annotations

from dataclasses import dataclass

from .evaluation import (
    DesktopCompanionEvaluationRecord,
    DesktopCompanionReleaseGateReport,
    GateStatus,
    build_desktop_companion_release_gate,
)

_MINIMUM_PARTITION_RECORDS = 12


@dataclass(frozen=True, slots=True)
class DesktopCompanionEvidencePartition:
    exact_commit_sha: str
    observation_schema_version: int = 1
    attention_policy_version: int = 1
    vision_provider: str | None = None
    vision_model_hash: str | None = None
    remote_provider: bool | None = None


def select_desktop_companion_evidence(
    records: list[DesktopCompanionEvaluationRecord],
    partition: DesktopCompanionEvidencePartition,
) -> list[DesktopCompanionEvaluationRecord]:
    selected: list[DesktopCompanionEvaluationRecord] = []
    for record in records:
        if record.exact_commit_sha != partition.exact_commit_sha:
            continue
        if record.observation_schema_version != partition.observation_schema_version:
            continue
        if record.attention_policy_version != partition.attention_policy_version:
            continue
        if partition.vision_provider is not None and record.vision_provider != partition.vision_provider:
            continue
        if partition.vision_model_hash is not None and record.vision_model_hash != partition.vision_model_hash:
            continue
        if partition.remote_provider is not None and record.remote_provider != partition.remote_provider:
            continue
        selected.append(record)
    return selected


def build_partitioned_desktop_companion_release_gate(
    records: list[DesktopCompanionEvaluationRecord],
    partition: DesktopCompanionEvidencePartition,
) -> DesktopCompanionReleaseGateReport:
    selected = select_desktop_companion_evidence(records, partition)
    report = build_desktop_companion_release_gate(selected)
    insufficient = list(report.insufficient)
    legacy_minimum = next((item for item in insufficient if item.startswith("minimum_records:")), None)
    if legacy_minimum:
        insufficient.remove(legacy_minimum)
    if len(selected) < _MINIMUM_PARTITION_RECORDS:
        insufficient.append(f"minimum_partition_records:{len(selected)}/{_MINIMUM_PARTITION_RECORDS}")
    if not partition.exact_commit_sha or partition.exact_commit_sha == "unknown-local-build":
        insufficient.append("exact_build_identity_required")
    status: GateStatus = "fail" if report.failures else "insufficient" if insufficient else "pass"
    return report.model_copy(
        update={
            "status": status,
            "insufficient": tuple(dict.fromkeys(insufficient)),
        }
    )


__all__ = [
    "DesktopCompanionEvidencePartition",
    "build_partitioned_desktop_companion_release_gate",
    "select_desktop_companion_evidence",
]
