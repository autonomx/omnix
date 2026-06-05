from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_7_production_readiness_closeout_decision_gate.md"


def test_phase10_7_core_contract():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.7 records the closeout decision gate",
        "source/test/documentation only",
        "phase10_evidence_index",
        "package_evidence_status",
        "install_run_status",
        "persistence_status",
        "diagnostics_status",
        "player_safe_error_status",
        "release_candidate_status",
        "operator_intake_status",
        "closeout_decision",
        "Phase 11.1 — evidence-driven production hardening triage",
    ):
        assert expected in plan


def test_phase10_7_classifications_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "production_closeout_evidence_gap",
        "production_closeout_blocked",
        "production_closeout_deferred",
        "operator_evidence_required",
        "runtime_hardening_required",
        "packaging_hardening_required",
        "diagnostics_hardening_required",
        "release_candidate_review_ready",
        "production_release_ready",
        "classification: `production_closeout_evidence_gap`",
        "documentation and deterministic source guards only",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "must not decide gameplay truth",
    ):
        assert expected in plan
