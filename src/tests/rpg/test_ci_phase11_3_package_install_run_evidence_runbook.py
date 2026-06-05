from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_3_package_install_run_evidence_runbook.md"


def test_phase11_3_runbook_core_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.3 defines the operator runbook",
        "source/test/documentation only",
        "operator_context",
        "source_checkout",
        "package_artifact_inventory",
        "dependency_install_steps",
        "configuration_snapshot",
        "environment_variable_snapshot",
        "resource_path_snapshot",
        "data_path_snapshot",
        "launch_command",
        "startup_health_check",
        "runtime_smoke_command",
        "runtime_smoke_result",
        "shutdown_steps",
        "diagnostic_collection_steps",
        "redaction_review",
        "evidence_bundle_manifest",
        "package_install_run_classification",
        "Phase 11.4 — first persistence and diagnostics evidence capture runbook",
    ):
        assert expected in plan


def test_phase11_3_artifacts_and_metadata_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "dependency install transcript",
        "launch transcript",
        "startup health transcript",
        "runtime smoke transcript",
        "shutdown transcript",
        "environment variable snapshot with secrets redacted",
        "resource/model path manifest",
        "data/session/save/report path manifest",
        "git SHA and branch",
        "operator name or role",
        "Python version",
        "exit status for install, launch, smoke, and shutdown",
        "secrets, tokens, provider keys, personal data, and sensitive local paths were redacted",
    ):
        assert expected in plan


def test_phase11_3_gap_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "package_install_run_not_started",
        "source_checkout_gap",
        "package_artifact_gap",
        "dependency_install_transcript_gap",
        "configuration_snapshot_gap",
        "environment_snapshot_gap",
        "resource_path_snapshot_gap",
        "data_path_snapshot_gap",
        "launch_transcript_gap",
        "startup_health_gap",
        "runtime_smoke_gap",
        "shutdown_transcript_gap",
        "diagnostic_collection_gap",
        "redaction_review_gap",
        "evidence_bundle_gap",
        "package_install_run_ready_for_triage",
    ):
        assert expected in plan


def test_phase11_3_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `package_install_run_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "documentation and deterministic source guards only",
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
