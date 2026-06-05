from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase10_3_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_3_persistence_diagnostics_evidence_envelope.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase10_3_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.3 persistence and diagnostics evidence envelope is complete.",
        "Implementation PR: #319",
        "1f689b6ba84dbaa208c113508d3b673f84c02383",
        "7549f3a08874c24140c34bfd6fff350d093ddb1c",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase10_3_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free persistence and diagnostics evidence envelope",
        "classifies the current state as `persistence_diagnostics_evidence_gap`",
        "does not claim release readiness",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase10_3_completion_note_matches_persistence_diagnostics_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "save_path_evidence",
        "session_path_evidence",
        "data_path_evidence",
        "save_load_roundtrip_evidence",
        "replay_artifact_evidence",
        "package_disk_artifact_evidence",
        "diagnostic_bundle_evidence",
        "operator_collection_steps",
        "redaction_sensitive_data_evidence",
        "player_safe_internal_separation",
        "persistence_diagnostics_evidence_gap",
        "persistence_diagnostics_ready",
    ):
        assert expected in plan
    for expected in (
        "save path evidence",
        "session path evidence",
        "data path evidence",
        "save/load roundtrip evidence",
        "replay artifact evidence",
        "package/disk artifact evidence",
        "diagnostic bundle evidence",
        "operator collection steps",
        "redaction/sensitive-data evidence",
        "player-safe/internal diagnostic separation",
        "persistence_diagnostics_evidence_gap",
    ):
        assert expected in note


def test_phase10_3_roadmap_advances_to_phase10_4():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 10 — production packaging, stability, and release readiness**.",
        "Current slice: **Phase 10.4 — player-safe error handling evidence envelope**.",
        "Next recommended slice after Phase 10.4: **Phase 10.5 — release candidate packaging contract**.",
        "Phase 10.3 — persistence and diagnostics evidence envelope.",
        "#319 Phase 10.3 persistence diagnostics evidence envelope",
        "7549f3a08874c24140c34bfd6fff350d093ddb1c",
    ):
        assert expected in roadmap
