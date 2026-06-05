from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase11_9_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase11_9_completion_note_records_pr_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 11.9 is complete as a deterministic hardening target selection gate",
        "PR #345 — Phase 11.9 hardening target selection gate",
        "764eccb922229c6b0045f77e63bc219f62948fee",
        "32955e874239f6cb82dc9f811471c611da15ed05",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase11_9_completion_note_preserves_no_evidence_baseline():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `hardening_target_selection_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "selected target: none",
        "Phase 12 implementation must not begin unless attached evidence identifies a concrete bounded hardening target",
        "evidence source path",
        "failure category",
        "reproduction command or steps",
        "affected component",
        "deterministic/runtime boundary impact",
        "required verification checks",
    ):
        assert expected in note


def test_phase11_9_completion_note_preserves_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "runtime behavior",
        "gameplay mutation",
        "provider calls",
        "LLM calls",
        "network calls",
        "live endurance execution in CI",
        "package building in CI",
        "UI authority changes",
        "production readiness claims",
        "Simulation/runtime remains authoritative",
        "do not decide gameplay truth",
    ):
        assert expected in note


def test_roadmap_advances_to_phase12_1_after_phase11_9():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 12 — concrete evidence-backed production hardening**.",
        "Current slice: **Phase 12.1 — concrete hardening implementation from accepted evidence**.",
        "Latest source-of-truth SHA before Phase 12.1: `764eccb922229c6b0045f77e63bc219f62948fee`.",
        "| #345 Phase 11.9 hardening target selection gate | `764eccb922229c6b0045f77e63bc219f62948fee` | Phase 11.9 | Complete | Added evidence-backed hardening target selection gate and deterministic guard. |",
        "- [x] Phase 11.9 — first hardening target selection from attached evidence.",
        "- [ ] Phase 12.1 — concrete hardening implementation from accepted evidence.",
        "Phase 12.1 scope:",
        "Do not implement speculative hardening without accepted evidence.",
    ):
        assert expected in roadmap
