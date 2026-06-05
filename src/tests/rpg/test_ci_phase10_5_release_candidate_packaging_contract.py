from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_5_release_candidate_packaging_contract.md"


def test_phase10_5_release_candidate_contract_core_terms():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.5 records the evidence contract",
        "source/test/documentation only",
        "does not build a release package",
        "Phase 10.6 — operator release evidence intake checklist",
        "source_revision_evidence",
        "package_manifest_evidence",
        "artifact_inventory_evidence",
        "dependency_lock_evidence",
        "configuration_template_evidence",
        "model_resource_manifest_evidence",
        "data_directory_manifest_evidence",
        "launch_script_evidence",
        "install_run_transcript_evidence",
        "persistence_smoke_evidence",
        "diagnostic_bundle_evidence",
        "player_safe_error_evidence",
        "release_notes_evidence",
        "known_blocker_evidence",
        "rollback_recovery_evidence",
        "release_candidate_classification",
    ):
        assert expected in plan


def test_phase10_5_release_candidate_classifications():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "release_candidate_evidence_gap",
        "source_revision_gap",
        "package_manifest_gap",
        "artifact_inventory_gap",
        "dependency_lock_gap",
        "configuration_template_gap",
        "model_resource_manifest_gap",
        "data_directory_manifest_gap",
        "launch_script_gap",
        "install_run_transcript_gap",
        "persistence_smoke_gap",
        "diagnostic_bundle_gap",
        "player_safe_error_gap",
        "release_notes_gap",
        "known_blocker_gap",
        "rollback_recovery_gap",
        "release_candidate_ready",
    ):
        assert expected in plan


def test_phase10_5_no_evidence_and_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `release_candidate_evidence_gap`",
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
