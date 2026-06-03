from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase8_5_completion_note.md"


def test_ci_phase8_5_completion_note_records_pr_and_guardrails():
    note = NOTE.read_text(encoding="utf-8")

    assert "Phase 8.5" in note
    assert "Implementation PR: #234" in note
    assert "1a56b5821ffb35d3055624dd8095ed02dcca2de7" in note
    assert "eb57dceabb5ef141f77e004f623195fe48f0ef99" in note
    assert "RPG Phase 0 architecture compliance" in note
    assert "RPG deterministic PR gates" in note
    assert "Runtime/simulation remains authoritative" in note
    assert "No provider/LLM calls are introduced" in note
