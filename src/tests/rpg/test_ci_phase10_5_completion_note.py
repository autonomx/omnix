from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase10_5_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_5_release_candidate_packaging_contract.md"


def test_phase10_5_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.5 release-candidate packaging contract is complete.",
        "Implementation PR: #323",
        "95ec3151ca1e8251a93eab764038a87eb8249080",
        "801b075ad69b3d97a7e6cce7fac746c3bdfeec63",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase10_5_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free release-candidate packaging contract",
        "classifies the current state as `release_candidate_evidence_gap`",
        "does not claim release readiness",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase10_5_completion_note_matches_release_candidate_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
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
        "release_candidate_evidence_gap",
        "release_candidate_ready",
    ):
        assert expected in plan
    for expected in (
        "source revision",
        "package manifest",
        "artifact inventory",
        "dependency lock",
        "configuration templates",
        "model/resource manifests",
        "data directory manifests",
        "launch scripts",
        "install/run transcripts",
        "persistence smoke",
        "diagnostic bundles",
        "player-safe errors",
        "release_candidate_evidence_gap",
        "release_candidate_ready",
    ):
        assert expected in note
