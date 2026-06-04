from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_34_completion_note.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_34_completion_note_records_runtime_authority_audit():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.34 UI runtime-authority boundary audit is complete.",
        "Implementation PR: #292",
        "96a7cca00316ce302d614f0910f8a5115b117772",
        "b33a338894e36de64b5ca966b54069d659fc6ec5",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
        "read-only panels do not submit commands or mutate runtime state",
        "survival inspector remains the only registered command-intent panel",
        "shared panel chrome/layout remain provider-free and presentation-only",
        "runtime_part27 and runtime_part23",
        "Phase 8.35 final closeout note and Phase 9 handoff",
        "not a full visual/gameplay UI overhaul",
    ):
        assert expected in note


def test_phase8_34_completion_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow
