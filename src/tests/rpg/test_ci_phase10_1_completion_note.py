from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase10_1_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_1_production_readiness_baseline.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase10_1_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.1 production readiness baseline and packaging evidence plan is complete.",
        "Implementation PR: #315",
        "3ff7c0a29efe0b76aa0269b2b2d9382c46e30dab",
        "12efbe0baa16bed4c5336fdf76ff6422081a910f",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase10_1_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free production readiness baseline",
        "classifies the current state as `production_evidence_gap`",
        "does not claim release readiness",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase10_1_completion_note_matches_baseline_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "package_layout_evidence",
        "install_command_evidence",
        "run_command_evidence",
        "configuration_evidence",
        "save_load_persistence_evidence",
        "log_diagnostics_evidence",
        "player_safe_error_evidence",
        "production_evidence_gap",
        "release_candidate_ready",
    ):
        assert expected in plan
    for expected in (
        "package layout evidence",
        "install command evidence",
        "run command evidence",
        "configuration evidence",
        "save/load persistence evidence",
        "log diagnostics evidence",
        "player-safe error evidence",
        "production_evidence_gap",
        "release_candidate_ready",
    ):
        assert expected in note


def test_phase10_1_roadmap_advances_to_phase10_2():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 10 — production packaging, stability, and release readiness**.",
        "Current slice: **Phase 10.2 — install/run configuration evidence envelope**.",
        "Next recommended slice after Phase 10.2: **Phase 10.3 — persistence and diagnostics evidence envelope**.",
        "Phase 10.1 — production readiness baseline and packaging evidence plan.",
        "#315 Phase 10.1 production readiness baseline",
        "12efbe0baa16bed4c5336fdf76ff6422081a910f",
    ):
        assert expected in roadmap
