from __future__ import annotations

from pathlib import Path

from app.rpg.narrative_release_certification import (
    RELEASE_SCHEMA_VERSION,
    audit_phase_artifacts,
    certify_unified_narrative_release,
)
from app.rpg.response_generation.release_gate import (
    CampaignEvidenceRow,
    metrics_from_campaign_rows,
)


ROOT = Path(__file__).resolve().parents[4]
HEAD = "a" * 40


def _metrics(*, exact_head: bool = True):
    rows = tuple(
        CampaignEvidenceRow(
            turn_id=f"phase42:{index}",
            allowed_forward_outcome=True,
            normal_turn_latency_ms=100.0 + index,
        )
        for index in range(32)
    )
    return metrics_from_campaign_rows(
        rows,
        replay_hash_stable=True,
        persistent_proposal_peak=4,
        persistent_proposal_budget=64,
        exact_head_checks_passed=exact_head,
        p95_budget_ms=5000.0,
    )


def _runtime_checks() -> dict[str, bool]:
    return {
        "canonical_roundtrip_stable": True,
        "blocking_deferred_semantic_equivalence": True,
        "deferred_delivery_ordered_complete": True,
        "production_certification_passed": True,
        "retirement_record_persisted": True,
    }


def _retirement_snapshot() -> dict[str, object]:
    return {
        "record_count": 1,
        "canonical_publish_count": 1,
        "alternate_publish_count": 0,
        "rejected_alternate_count": 0,
        "violation_count": 0,
        "zero_alternate_publishers": True,
        "legacy_publisher_deletion_certified": True,
    }


def test_phase42_certifies_exact_head_and_all_milestone_artifacts() -> None:
    certificate = certify_unified_narrative_release(
        repository_root=ROOT,
        expected_head_sha=HEAD,
        observed_head_sha=HEAD,
        release_metrics=_metrics(),
        runtime_checks=_runtime_checks(),
        retirement_snapshot=_retirement_snapshot(),
    )

    assert certificate.passed is True, certificate.as_dict()
    payload = certificate.as_dict()
    assert payload["schema_version"] == RELEASE_SCHEMA_VERSION
    assert payload["checks"]["exact_head_sha_matches"] is True
    assert payload["checks"]["phase_25_through_41_artifacts_present"] is True
    assert payload["checks"]["zero_alternate_publishers"] is True
    assert payload["phase_artifacts"]["phase_count"] == 17
    assert payload["response_release_gate"]["passed"] is True
    assert payload["legacy_retirement_audit"]["passed"] is True


def test_phase42_fails_closed_on_head_drift() -> None:
    certificate = certify_unified_narrative_release(
        repository_root=ROOT,
        expected_head_sha=HEAD,
        observed_head_sha="b" * 40,
        release_metrics=_metrics(exact_head=False),
        runtime_checks=_runtime_checks(),
        retirement_snapshot=_retirement_snapshot(),
    )

    assert certificate.passed is False
    assert "exact_head_sha_matches" in certificate.violations
    assert "response_release_gate_passed" in certificate.violations
    assert "exact_head_checks_not_passed" in certificate.response_release_gate.issues


def test_phase42_fails_closed_on_missing_runtime_or_retirement_evidence() -> None:
    checks = _runtime_checks()
    checks["deferred_delivery_ordered_complete"] = False
    snapshot = _retirement_snapshot()
    snapshot["record_count"] = 0
    snapshot["legacy_publisher_deletion_certified"] = False

    certificate = certify_unified_narrative_release(
        repository_root=ROOT,
        expected_head_sha=HEAD,
        observed_head_sha=HEAD,
        release_metrics=_metrics(),
        runtime_checks=checks,
        retirement_snapshot=snapshot,
    )

    assert certificate.passed is False
    assert "deferred_delivery_ordered_complete" in certificate.violations
    assert "retirement_records_present" in certificate.violations
    assert "legacy_publisher_deletion_certified" in certificate.violations


def test_phase_artifact_audit_requires_contiguous_phase_25_through_41(tmp_path) -> None:
    audit = audit_phase_artifacts(tmp_path)
    assert audit.passed is False
    assert tuple(audit.phases) == tuple(range(25, 42))
    assert audit.missing_paths


def test_phase42_source_guards_cover_cli_workflow_and_exact_head_artifact() -> None:
    script = (
        ROOT / "scripts" / "certify_rpg_narrative_engine_release.py"
    ).read_text(encoding="utf-8")
    workflow = (
        ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"
    ).read_text(encoding="utf-8")
    certification = (
        ROOT / "src" / "app" / "rpg" / "narrative_release_certification.py"
    ).read_text(encoding="utf-8")

    assert "certify_unified_narrative_release" in script
    assert "--expected-head" in script
    assert "--observed-head" in script
    assert "Unified narrative exact-head release" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert "rpg-narrative-release-certificate.json" in workflow
    assert "phase_25_through_41_artifacts_present" in certification
    assert "provider_free_exact_head" in certification
