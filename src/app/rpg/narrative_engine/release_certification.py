"""Final provider-free release certification for Narrative Engine milestones G-L."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.rpg.response_generation.release_gate import (
    ReleaseGateResult,
    ResponseReleaseMetrics,
    evaluate_response_release_gate,
)

from .legacy_retirement import (
    LegacyPublisherRetirementAudit,
    audit_legacy_publisher_retirement,
)


RELEASE_SCHEMA_VERSION = "rne_milestones_g_l_release_v1"
REQUIRED_PHASE_ARTIFACTS: Mapping[int, tuple[str, ...]] = {
    25: (
        "src/tests/rpg/response_generation/test_rne_phase25_canonical_semantics.py",
    ),
    26: (
        "src/tests/rpg/response_generation/test_rne_phase26_knowledge_grants.py",
    ),
    27: (
        "src/tests/rpg/response_generation/test_rne_phase27_semantic_claims.py",
    ),
    28: (
        "src/tests/rpg/response_generation/test_rne_phase28_production_writer.py",
    ),
    29: (
        "src/tests/rpg/response_generation/test_rne_phase29_direct_dialogue_replacement.py",
    ),
    30: (
        "src/tests/rpg/response_generation/test_rne_phase30_single_orchestration.py",
    ),
    31: (
        "src/tests/rpg/response_generation/test_rne_phase31_postgres_repository.py",
    ),
    32: (
        "src/tests/rpg/response_generation/test_rne_phase32_turn_idempotency.py",
    ),
    33: (
        "src/tests/rpg/response_generation/test_rne_phase33_atomic_turn_persistence.py",
    ),
    34: (
        "src/tests/rpg/response_generation/test_rne_phase34_runtime_repository_authority.py",
    ),
    35: (
        "src/tests/rpg/response_generation/test_rne_phase35_durable_submission_replay.py",
    ),
    36: (
        "src/tests/rpg/response_generation/test_rne_phase36_production_world_forge.py",
    ),
    37: (
        "src/tests/rpg/response_generation/test_rne_phase37_world_forge_commit_gate.py",
    ),
    38: (
        "src/tests/rpg/response_generation/test_rne_phase38_world_forge_dossier_quality.py",
    ),
    39: (
        "src/tests/rpg/response_generation/test_rne_phase39_async_campaign_genesis.py",
    ),
    40: (
        "src/tests/rpg/response_generation/test_rne_phase40_deferred_delivery.py",
        "src/app/persistence/migrations/0022_rpg_narrative_delivery.sql",
    ),
    41: (
        "src/tests/rpg/response_generation/test_rne_phase41_legacy_retirement.py",
        "src/app/persistence/migrations/0023_rpg_narrative_retirement.sql",
    ),
}


@dataclass(frozen=True)
class PhaseArtifactAudit:
    passed: bool
    phases: Mapping[int, bool]
    missing_paths: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "phase_count": len(self.phases),
            "phases": {str(key): value for key, value in self.phases.items()},
            "missing_paths": list(self.missing_paths),
        }


@dataclass(frozen=True)
class NarrativeReleaseCertification:
    passed: bool
    expected_head_sha: str
    observed_head_sha: str
    checks: Mapping[str, bool]
    violations: tuple[str, ...]
    phase_artifacts: PhaseArtifactAudit
    response_release_gate: ReleaseGateResult
    legacy_retirement_audit: LegacyPublisherRetirementAudit
    retirement_snapshot: Mapping[str, Any]
    diagnostics: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RELEASE_SCHEMA_VERSION,
            "passed": self.passed,
            "expected_head_sha": self.expected_head_sha,
            "observed_head_sha": self.observed_head_sha,
            "checks": dict(self.checks),
            "violations": list(self.violations),
            "phase_artifacts": self.phase_artifacts.as_dict(),
            "response_release_gate": {
                "passed": self.response_release_gate.passed,
                "issues": list(self.response_release_gate.issues),
                "metrics": dict(self.response_release_gate.metrics),
            },
            "legacy_retirement_audit": self.legacy_retirement_audit.as_dict(),
            "retirement_snapshot": dict(self.retirement_snapshot),
            "diagnostics": dict(self.diagnostics),
        }


def audit_phase_artifacts(repository_root: Path) -> PhaseArtifactAudit:
    root = repository_root.resolve()
    phases: dict[int, bool] = {}
    missing: list[str] = []
    for phase, paths in REQUIRED_PHASE_ARTIFACTS.items():
        absent = [path for path in paths if not (root / path).is_file()]
        phases[phase] = not absent
        missing.extend(absent)
    return PhaseArtifactAudit(
        passed=not missing and tuple(phases) == tuple(range(25, 42)),
        phases=phases,
        missing_paths=tuple(missing),
    )


def certify_unified_narrative_release(
    *,
    repository_root: Path,
    expected_head_sha: str,
    observed_head_sha: str,
    release_metrics: ResponseReleaseMetrics,
    runtime_checks: Mapping[str, bool],
    retirement_snapshot: Mapping[str, Any],
    required_runtime_checks: Sequence[str] = (
        "canonical_roundtrip_stable",
        "blocking_deferred_semantic_equivalence",
        "deferred_delivery_ordered_complete",
        "production_certification_passed",
        "retirement_record_persisted",
    ),
) -> NarrativeReleaseCertification:
    expected = str(expected_head_sha or "").strip().lower()
    observed = str(observed_head_sha or "").strip().lower()
    phase_audit = audit_phase_artifacts(repository_root)
    legacy_audit = audit_legacy_publisher_retirement(repository_root)
    release_gate = evaluate_response_release_gate(release_metrics)
    required_runtime = {
        name: runtime_checks.get(name) is True for name in required_runtime_checks
    }
    retirement = dict(retirement_snapshot)
    checks = {
        "expected_head_sha_valid": _valid_sha(expected),
        "observed_head_sha_valid": _valid_sha(observed),
        "exact_head_sha_matches": bool(expected) and expected == observed,
        "phase_25_through_41_artifacts_present": phase_audit.passed,
        "response_release_gate_passed": release_gate.passed,
        "legacy_publisher_deletion_audit_passed": legacy_audit.passed,
        "retirement_records_present": int(retirement.get("record_count") or 0) > 0,
        "zero_alternate_publishers": (
            retirement.get("zero_alternate_publishers") is True
            and int(retirement.get("alternate_publish_count") or 0) == 0
        ),
        "legacy_publisher_deletion_certified": (
            retirement.get("legacy_publisher_deletion_certified") is True
        ),
        **required_runtime,
    }
    violations = tuple(name for name, passed in checks.items() if not passed)
    return NarrativeReleaseCertification(
        passed=not violations,
        expected_head_sha=expected,
        observed_head_sha=observed,
        checks=checks,
        violations=violations,
        phase_artifacts=phase_audit,
        response_release_gate=release_gate,
        legacy_retirement_audit=legacy_audit,
        retirement_snapshot=retirement,
        diagnostics={
            "runtime_checks": dict(runtime_checks),
            "required_runtime_checks": list(required_runtime_checks),
            "required_phase_range": [25, 41],
            "provider_policy": "provider_free_exact_head",
        },
    )


def _valid_sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
