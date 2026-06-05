from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase10_2_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_2_install_run_configuration_evidence_envelope.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase10_2_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.2 install/run configuration evidence envelope is complete.",
        "Implementation PR: #317",
        "d4e48414d85e61be0df90f389c3356caa0e553b4",
        "1957d9da2cc505ba04247b92dabef0c614238759",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase10_2_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free install/run configuration evidence envelope",
        "classifies the current state as `install_run_evidence_gap`",
        "does not claim release readiness",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase10_2_completion_note_matches_install_run_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "operator_environment",
        "repository_checkout",
        "dependency_install",
        "configuration_files",
        "environment_variables",
        "model_resource_paths",
        "data_session_paths",
        "startup_health_check",
        "runtime_smoke_result",
        "shutdown_result",
        "diagnostic_log_paths",
        "install_run_evidence_gap",
        "install_run_ready",
    ):
        assert expected in plan
    for expected in (
        "operator environment",
        "repository checkout",
        "dependency install",
        "configuration files",
        "environment variables",
        "model/resource paths",
        "data/session paths",
        "startup health check",
        "runtime smoke result",
        "shutdown result",
        "diagnostic log paths",
        "install_run_evidence_gap",
        "install_run_ready",
    ):
        assert expected in note


def test_phase10_2_roadmap_advances_to_phase10_3():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 10 — production packaging, stability, and release readiness**.",
        "Current slice: **Phase 10.3 — persistence and diagnostics evidence envelope**.",
        "Next recommended slice after Phase 10.3: **Phase 10.4 — player-safe error handling evidence envelope**.",
        "Phase 10.2 — install/run configuration evidence envelope.",
        "#317 Phase 10.2 install/run evidence envelope",
        "1957d9da2cc505ba04247b92dabef0c614238759",
    ):
        assert expected in roadmap
