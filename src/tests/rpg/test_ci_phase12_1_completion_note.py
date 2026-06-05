from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase12_1_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase12_1_completion_note_records_pr_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.1 is complete as an evidence-decision gate",
        "PR #347 — Phase 12.1 evidence decision gate",
        "71c82ae6500f674f90ebe57b345f3ed78cb4f04d",
        "b41f0f28e467832a4f4053ca7828f1d1953ed0bb",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase12_1_completion_note_preserves_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_1_no_accepted_evidence`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_1_implementation_blocked`",
        "selected fix target: none",
        "Actual operator evidence bundles are still missing",
        "No concrete production hardening fix has been implemented",
        "Production readiness is not claimable",
    ):
        assert expected in note


def test_phase12_1_completion_note_preserves_boundary():
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
        "speculative hardening",
        "production readiness claims",
        "Simulation/runtime remains authoritative",
        "do not decide gameplay truth",
    ):
        assert expected in note


def test_roadmap_advances_to_phase12_2_after_phase12_1():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 12 — concrete evidence-backed production hardening**.",
        "Current slice: **Phase 12.2 — package/install/run evidence capture or hardening**.",
        "Latest source-of-truth SHA before Phase 12.2: `71c82ae6500f674f90ebe57b345f3ed78cb4f04d`.",
        "| #347 Phase 12.1 evidence decision gate | `71c82ae6500f674f90ebe57b345f3ed78cb4f04d` | Phase 12.1 | Complete | Added evidence-decision gate proving implementation remains blocked without accepted evidence. |",
        "- [x] Phase 12.1 — concrete hardening implementation from accepted evidence.",
        "- [ ] Phase 12.2 — package/install/run evidence capture or hardening.",
        "Phase 12.2 scope:",
        "Do not implement speculative packaging hardening without accepted package/install/run evidence.",
    ):
        assert expected in roadmap
