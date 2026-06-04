from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / "docs" / "plans" / "rpg_phase8_33_browser_smoke_coverage.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase8_33_smoke_note_is_wildcard_wired_into_architecture_workflow():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "src/tests/rpg/test_ci_phase8_*_note.py" in workflow
    assert "docs/plans/rpg_phase8_*_completion_note.md" in workflow


def test_phase8_33_smoke_note_records_browser_smoke_contracts():
    smoke = SMOKE.read_text(encoding="utf-8")
    for expected in (
        "Phase 8.33 records provider-free browser smoke coverage",
        "source-backed smoke coverage slice",
        "not a new browser test harness installation",
        "Every registered panel must continue to satisfy these smoke conditions",
        "Escaped payload smoke expectations",
        "Runtime authority smoke expectations",
        "No registered panel may add provider/LLM calls.",
        "No registered panel may mutate gameplay truth.",
        "Phase 8.34 — UI runtime-authority boundary audit.",
        "Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff.",
    ):
        assert expected in smoke
