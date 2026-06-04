from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_2_completion_note.md"
PHASE9_3 = ROOT / "docs" / "plans" / "rpg_phase9_3_checkpoint_replay_taxonomy.md"
PHASE9_3_NOTE = ROOT / "docs" / "plans" / "rpg_phase9_3_completion_note.md"
PHASE9_4 = ROOT / "docs" / "plans" / "rpg_phase9_4_progress_quality_loop_taxonomy.md"
PHASE9_4_NOTE = ROOT / "docs" / "plans" / "rpg_phase9_4_completion_note.md"
PHASE9_5 = ROOT / "docs" / "plans" / "rpg_phase9_5_performance_evidence_envelope.md"
PHASE9_5_NOTE = ROOT / "docs" / "plans" / "rpg_phase9_5_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase9_2_completion_note_records_artifact_contract_guard():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.2 deterministic endurance artifact contract guard is complete.",
        "Implementation PR: #298",
        "36f29983f3ed0a3006365abd35d07bba19d6a03d",
        "a72952ca26a33648230bdbf6f3a6a04ec5e2701a",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "docs/plans/rpg_phase9_2_endurance_artifact_contract.md",
        "src/tests/rpg/test_ci_phase9_2_endurance_artifact_contract.py",
        "src/tests/rpg/test_ci_runtime_wrapper_manifest.py",
        "autoplay-summary.json",
        "autoplay-transcript.json",
        "autoplay-campaign-results.zip",
        "summary.json",
        "artifact_paths",
        "provider-free guard",
        "No live/provider 1000-turn campaign added to CI.",
        "Phase 9.3 — endurance checkpoint and replay taxonomy guard",
    ):
        assert expected in note


def test_phase9_2_completion_note_is_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for expected in (
        "src/tests/rpg/test_ci_phase9_2_endurance_artifact_contract.py",
        "src/tests/rpg/test_ci_phase9_2_completion_note.py",
        "docs/plans/rpg_phase9_2_endurance_artifact_contract.md",
        "docs/plans/rpg_phase9_2_completion_note.md",
    ):
        assert expected in workflow


def test_phase9_3_taxonomy_doc_is_covered_by_existing_phase9_architecture_gate():
    doc = PHASE9_3.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.3 Checkpoint and Replay Taxonomy Guard",
        "save_load_checkpoint_failure",
        "artifact_contract_failure",
        "operator_evidence_gap",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in doc


def test_phase9_3_completion_note_is_covered_by_existing_phase9_architecture_gate():
    note = PHASE9_3_NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.3 checkpoint and replay taxonomy guard is complete.",
        "Implementation PR: #300",
        "71d8ba3a0f2d0ee181fb0b525b7db3e9b7ce663b",
        "save_load_checkpoint_failure",
        "artifact_contract_failure",
        "operator_evidence_gap",
        "Phase 9.4 — endurance progress-quality loop taxonomy guard",
    ):
        assert expected in note


def test_phase9_4_progress_quality_doc_is_covered_by_existing_phase9_architecture_gate():
    doc = PHASE9_4.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.4 Progress-Quality Loop Taxonomy Guard",
        "progress_quality_failure",
        "turn_execution_failure",
        "operator_evidence_gap",
        "Simulation/runtime remains authoritative",
    ):
        assert expected in doc


def test_phase9_4_completion_note_is_covered_by_existing_phase9_architecture_gate():
    note = PHASE9_4_NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.4 progress-quality loop taxonomy guard is complete.",
        "Implementation PR: #302",
        "a50978c140a333983fef93cf49d8115ef94d43e7",
        "progress_quality_failure",
        "turn_execution_failure",
        "operator_evidence_gap",
        "Phase 9.5 — endurance performance/evidence envelope",
    ):
        assert expected in note


def test_phase9_5_performance_doc_is_covered_by_existing_phase9_architecture_gate():
    doc = PHASE9_5.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.5 Performance Evidence Envelope",
        "performance_budget_failure",
        "operator_evidence_gap",
        "progress_quality_failure",
        "Simulation/runtime remains authoritative",
        "Phase 9.6 — targeted endurance hardening from concrete evidence",
    ):
        assert expected in doc


def test_phase9_5_completion_note_is_covered_by_existing_phase9_architecture_gate():
    note = PHASE9_5_NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.5 performance evidence envelope is complete.",
        "Implementation PR: #304",
        "a6bb22007976dca1c0f3f92899cc05846588adf1",
        "performance_budget_failure",
        "operator_evidence_gap",
        "progress_quality_failure",
        "Phase 9.6 — targeted endurance hardening from concrete evidence",
    ):
        assert expected in note
