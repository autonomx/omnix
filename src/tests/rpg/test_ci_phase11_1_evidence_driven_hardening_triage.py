from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_1_evidence_driven_hardening_triage.md"


def test_phase11_1_triage_core_terms():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.1 starts evidence-driven production hardening",
        "source/test/documentation only",
        "does not build a release package",
        "phase10_1_production_readiness_baseline",
        "phase10_7_closeout_decision_gate",
        "ci_failure_logs",
        "operator_artifacts",
        "source_backed_diagnostics",
        "evidence source paths inspected",
        "proposed hardening target",
        "explicit non-targets",
        "Phase 11.2 — operator evidence backfill or narrow hardening from concrete failures",
    ):
        assert expected in plan


def test_phase11_1_missing_evidence_categories_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "package artifact and checksum evidence",
        "install/run transcript evidence",
        "persistence smoke evidence",
        "diagnostic bundle evidence",
        "player-safe error evidence",
        "operator release intake summary",
        "redaction review",
        "operator signoff",
        "live/provider 100-turn evidence",
        "live/provider 1000-turn evidence",
        "live/provider save/load checkpoint evidence",
        "progress-quality transcript review",
        "long-run continuity review",
        "timing, drain, and resource-limit evidence",
    ):
        assert expected in plan


def test_phase11_1_classifications_and_no_evidence_decision():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "hardening_evidence_gap",
        "operator_evidence_backfill_required",
        "ci_failure_hardening_target",
        "operator_artifact_hardening_target",
        "source_diagnostic_hardening_target",
        "runtime_hardening_ready",
        "packaging_hardening_ready",
        "diagnostics_hardening_ready",
        "player_safe_error_hardening_ready",
        "release_candidate_review_ready",
        "classification: `hardening_evidence_gap`",
        "secondary classification: `operator_evidence_backfill_required`",
        "documentation and deterministic source guards only",
    ):
        assert expected in plan


def test_phase11_1_boundary_is_provider_free_and_non_mutating():
    plan = PLAN.read_text(encoding="utf-8")
    for forbidden in (
        "OpenAI API",
        "Anthropic API",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        assert forbidden not in plan
    for expected in (
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "speculative hardening without concrete evidence",
        "external release claims without evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
