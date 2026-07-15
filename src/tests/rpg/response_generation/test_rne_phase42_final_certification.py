from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rpg.narrative_engine.release_certification import (
    FinalNarrativeReleaseBlocked,
    FinalNarrativeReleaseEvidence,
    certify_final_narrative_release,
    require_final_narrative_release,
)


ROOT = Path(__file__).resolve().parents[4]
HEAD = "a" * 40
WORKFLOWS = {
    "RPG Phase 0 architecture compliance": "success",
    "PostgreSQL persistence gates": "success",
    "Live Chat hardening gates": "success",
    "RPG deterministic PR gates": "success",
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


def _evidence(**overrides: object) -> FinalNarrativeReleaseEvidence:
    payload = {
        "expected_head_sha": HEAD,
        "observed_head_sha": HEAD,
        "workflow_conclusions": WORKFLOWS,
        "retirement_snapshot": _retirement_snapshot(),
        "provider_free_ci": True,
        "live_provider_execution_claimed": False,
        "metadata": {"phase_range": "25-42"},
        **overrides,
    }
    return FinalNarrativeReleaseEvidence.from_mapping(payload)


def test_phase42_certifies_exact_head_workflows_retirement_and_delivery() -> None:
    certification = require_final_narrative_release(ROOT, _evidence())

    assert certification.passed is True, certification.as_dict()
    checks = certification.checks
    assert checks["exact_head_matches"] is True
    assert checks["required_workflows_success"] is True
    assert checks["publisher_ownership_audit_passed"] is True
    assert checks["legacy_deletion_audit_passed"] is True
    assert checks["required_migrations_present"] is True
    assert checks["required_phase_tests_present"] is True
    assert checks["deferred_delivery_resume_certified"] is True
    assert checks["retirement_zero_alternate_publishers"] is True
    assert checks["retirement_deletion_certified"] is True
    assert certification.diagnostics["missing_phase_tests"] == []
    assert certification.diagnostics["missing_migrations"] == []


def test_phase42_certificate_json_is_stable_and_roundtrippable() -> None:
    certification = certify_final_narrative_release(ROOT, _evidence())
    encoded = certification.canonical_json()

    assert encoded == certification.canonical_json()
    assert json.loads(encoded) == certification.as_dict()
    assert ": " not in encoded
    assert ", " not in encoded
    assert "\n" not in encoded


def test_phase42_fails_closed_on_exact_head_drift() -> None:
    evidence = _evidence(observed_head_sha="b" * 40)
    certification = certify_final_narrative_release(ROOT, evidence)

    assert certification.passed is False
    assert "exact_head_matches" in certification.violations
    with pytest.raises(FinalNarrativeReleaseBlocked, match="exact_head_matches"):
        require_final_narrative_release(ROOT, evidence)


def test_phase42_fails_closed_on_missing_or_failed_workflow_evidence() -> None:
    incomplete = dict(WORKFLOWS)
    incomplete.pop("PostgreSQL persistence gates")
    missing = certify_final_narrative_release(
        ROOT,
        _evidence(workflow_conclusions=incomplete),
    )
    assert "required_workflows_present" in missing.violations
    assert "required_workflows_success" in missing.violations

    failed = dict(WORKFLOWS)
    failed["RPG deterministic PR gates"] = "failure"
    rejected = certify_final_narrative_release(
        ROOT,
        _evidence(workflow_conclusions=failed),
    )
    assert "required_workflows_success" in rejected.violations


def test_phase42_fails_closed_on_fabricated_provider_or_retirement_evidence() -> None:
    snapshot = _retirement_snapshot()
    snapshot["alternate_publish_count"] = 1
    snapshot["zero_alternate_publishers"] = False
    snapshot["violation_count"] = 1
    snapshot["legacy_publisher_deletion_certified"] = False
    certification = certify_final_narrative_release(
        ROOT,
        _evidence(
            retirement_snapshot=snapshot,
            live_provider_execution_claimed=True,
        ),
    )

    assert certification.passed is False
    assert "live_provider_execution_not_fabricated" in certification.violations
    assert "retirement_zero_alternate_publishers" in certification.violations
    assert "retirement_deletion_certified" in certification.violations


def test_phase42_source_guard_keeps_final_certification_inside_engine_boundary() -> None:
    source = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "narrative_engine"
        / "release_certification.py"
    ).read_text(encoding="utf-8")

    assert "FinalNarrativeReleaseEvidence" in source
    assert "expected_head_sha" in source
    assert "required_workflows_success" in source
    assert "audit_legacy_publisher_retirement" in source
    assert "_deferred_delivery_certified" in source
    assert "live_provider_execution_claimed" in source
    assert "from app.rpg.response_generation" not in source
    assert "import app.rpg.response_generation" not in source


def test_phase42_completion_record_requires_external_exact_head_evidence() -> None:
    completion = (
        ROOT / "docs" / "RPG_NARRATIVE_ENGINE_MILESTONES_G_L_COMPLETION.md"
    ).read_text(encoding="utf-8")

    assert "exact-head workflow evidence is intentionally external" in completion
    assert "release evidence is certified against the exact pull-request head" not in completion
