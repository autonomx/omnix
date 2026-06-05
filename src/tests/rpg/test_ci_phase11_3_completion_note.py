from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_3_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_3_package_install_run_evidence_runbook.md"


def test_phase11_3_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.3 package/install/run evidence capture runbook is complete.",
        "Implementation PR: #333",
        "89aef9f6602d003a60220a5bbaee26c47cfd37d4",
        "78bcba7fb8c6e9aef3966a7a661d55b157d70d62",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_3_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator runbook",
        "package_install_run_not_started",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_3_completion_note_matches_runbook_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "package_install_run_not_started",
        "source_checkout_gap",
        "package_artifact_gap",
        "dependency_install_transcript_gap",
        "launch_transcript_gap",
        "startup_health_gap",
        "runtime_smoke_gap",
        "shutdown_transcript_gap",
        "diagnostic_collection_gap",
        "package_install_run_ready_for_triage",
    ):
        assert expected in plan
    for expected in (
        "operator context",
        "source checkout",
        "package artifact inventory",
        "dependency install steps",
        "configuration snapshot",
        "runtime smoke command/result",
        "Phase 11.4 — first persistence and diagnostics evidence capture runbook",
    ):
        assert expected in note
