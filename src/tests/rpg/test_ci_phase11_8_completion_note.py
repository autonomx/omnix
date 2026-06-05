from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_8_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase11_8_checkpoint_replay_evidence_runbook.md"


def test_phase11_8_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.8 checkpoint/replay evidence capture runbook is complete.",
        "Implementation PR: #343",
        "03eb68533c2f96fc7de7905c1778328052ca5205",
        "bb8d3e3a257be6b34bd174181b797d3006c3ca9b",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_8_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free operator runbook",
        "checkpoint_replay_capture_not_started",
        "operator_evidence_backfill_required",
        "does not select runtime, provider, packaging, UI, or gameplay hardening",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in note


def test_phase11_8_completion_note_matches_runbook_plan():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "checkpoint_replay_capture_not_started",
        "checkpoint_context_gap",
        "checkpoint_artifact_manifest_gap",
        "save_load_roundtrip_reference_gap",
        "replay_command_gap",
        "replay_result_gap",
        "package_disk_replay_reference_gap",
        "determinism_notes_gap",
        "artifact_integrity_gap",
        "checkpoint_replay_ready_for_triage",
    ):
        assert expected in plan
    for expected in (
        "checkpoint capture context",
        "checkpoint artifact manifest",
        "save/load roundtrip reference",
        "replay command",
        "replay result",
        "package/disk replay reference",
        "hardening handoff",
        "Phase 11.9 — first hardening target selection from attached evidence",
    ):
        assert expected in note
