from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_9_hardening_target_selection.md"


def test_phase11_9_selection_core_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.9 defines how the first concrete production hardening target is selected",
        "source/test/documentation only",
        "package_install_run_evidence",
        "persistence_diagnostics_evidence",
        "player_safe_error_redaction_evidence",
        "live_provider_100_turn_evidence",
        "live_provider_1000_turn_evidence",
        "checkpoint_replay_evidence",
        "ci_failure_logs",
        "source_backed_diagnostics",
        "Phase 12.1 — concrete hardening implementation from accepted evidence",
    ):
        assert expected in plan


def test_phase11_9_required_target_fields_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "evidence source path",
        "failure category",
        "reproduction command or steps",
        "affected component",
        "severity",
        "player impact",
        "deterministic/runtime boundary impact",
        "proposed bounded fix target",
        "explicit non-targets",
        "acceptance criteria",
        "required verification checks",
    ):
        assert expected in plan


def test_phase11_9_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "hardening_target_selection_not_started",
        "operator_evidence_backfill_required",
        "no_concrete_failure_evidence",
        "runtime_hardening_target_selected",
        "packaging_hardening_target_selected",
        "diagnostics_hardening_target_selected",
        "player_safe_error_hardening_target_selected",
        "endurance_hardening_target_selected",
        "checkpoint_replay_hardening_target_selected",
        "target_selection_ready_for_phase12",
    ):
        assert expected in plan


def test_phase11_9_no_evidence_and_phase12_gate():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `hardening_target_selection_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "selected target: none",
        "documentation and deterministic source guards only",
        "Phase 12 implementation must not begin unless an attached evidence bundle identifies a concrete bounded hardening target",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "package building in CI",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
