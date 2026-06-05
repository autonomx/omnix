from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_6_operator_release_evidence_intake_checklist.md"


def test_phase10_6_release_intake_core_terms():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.6 records the operator-facing intake checklist",
        "source/test/documentation only",
        "does not build a release package",
        "Phase 10.7 — production readiness closeout decision gate",
        "release_context",
        "source_revision",
        "package_artifacts",
        "install_run_evidence",
        "configuration_evidence",
        "persistence_evidence",
        "diagnostic_evidence",
        "player_safe_error_evidence",
        "endurance_evidence",
        "platform_environment",
        "known_blockers",
        "redaction_review",
        "operator_signoff",
        "release_intake_classification",
    ):
        assert expected in plan


def test_phase10_6_release_intake_classifications():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "release_intake_evidence_gap",
        "source_revision_gap",
        "package_artifact_gap",
        "install_run_evidence_gap",
        "configuration_evidence_gap",
        "persistence_evidence_gap",
        "diagnostic_evidence_gap",
        "player_safe_error_evidence_gap",
        "endurance_evidence_gap",
        "platform_environment_gap",
        "known_blocker_gap",
        "redaction_review_gap",
        "operator_signoff_gap",
        "release_intake_ready",
    ):
        assert expected in plan


def test_phase10_6_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `release_intake_evidence_gap`",
        "allowed changes: documentation and deterministic source guards only",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "external release claims without evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
