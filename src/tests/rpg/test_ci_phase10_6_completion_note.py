from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase10_6_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_6_operator_release_evidence_intake_checklist.md"


def test_phase10_6_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.6 operator release evidence intake checklist is complete.",
        "Implementation PR: #325",
        "f30434a12d580def789234753b3d0b7b23c560b8",
        "9f0a9dbe65c3da5f7335e742a9740386cb338d46",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase10_6_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator release evidence intake checklist",
        "classifies the current state as `release_intake_evidence_gap`",
        "does not claim release readiness",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase10_6_completion_note_matches_release_intake_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
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
        "release_intake_evidence_gap",
        "release_intake_ready",
    ):
        assert expected in plan
    for expected in (
        "release context",
        "source revision",
        "package artifacts",
        "install/run evidence",
        "configuration evidence",
        "persistence evidence",
        "diagnostic evidence",
        "player-safe error evidence",
        "endurance evidence",
        "platform environment",
        "known blockers",
        "redaction review",
        "operator signoff",
        "release_intake_evidence_gap",
        "release_intake_ready",
    ):
        assert expected in note
