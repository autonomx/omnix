from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_3_completion_note.md"
TAXONOMY = ROOT / "docs" / "plans" / "rpg_phase9_3_checkpoint_replay_taxonomy.md"
PHASE9_2_GATE = ROOT / "src" / "tests" / "rpg" / "test_ci_phase9_2_completion_note.py"


def test_phase9_3_completion_note_records_checkpoint_replay_taxonomy_guard():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.3 checkpoint and replay taxonomy guard is complete.",
        "Implementation PR: #300",
        "de4b0e7158f3e9b935058781ee3e592cc35ec8e4",
        "71d8ba3a0f2d0ee181fb0b525b7db3e9b7ce663b",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "docs/plans/rpg_phase9_3_checkpoint_replay_taxonomy.md",
        "src/tests/rpg/test_ci_phase9_3_checkpoint_replay_taxonomy.py",
        "src/tests/rpg/test_ci_phase9_2_completion_note.py",
        "save_load_checkpoint_failure",
        "artifact_contract_failure",
        "operator_evidence_gap",
        "No live/provider 1000-turn campaign added to CI.",
        "Phase 9.4 — endurance progress-quality loop taxonomy guard",
    ):
        assert expected in note


def test_phase9_3_completion_note_aligns_with_taxonomy_doc_and_bridge_guard():
    note = NOTE.read_text(encoding="utf-8")
    taxonomy = TAXONOMY.read_text(encoding="utf-8")
    bridge = PHASE9_2_GATE.read_text(encoding="utf-8")

    for category in (
        "save_load_checkpoint_failure",
        "artifact_contract_failure",
        "operator_evidence_gap",
    ):
        assert category in note
        assert category in taxonomy
    assert "Phase 9.4 — endurance progress-quality loop taxonomy guard" in note
    assert "Phase 9.4 — endurance progress-quality loop taxonomy guard" in taxonomy
    assert "rpg_phase9_3_checkpoint_replay_taxonomy.md" in bridge
