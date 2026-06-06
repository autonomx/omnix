from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase12_3_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase12_3_completion_note_records_pr_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.3 is complete as a persistence/diagnostics evidence-decision gate",
        "PR #351 — Phase 12.3 persistence diagnostics evidence decision gate",
        "3ccde744e6b84a6f0f2d28596b5e167280870778",
        "e53cc70546e2019151bb2ff1ab1192925b09e662",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase12_3_completion_note_preserves_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_3_persistence_diagnostics_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_3_implementation_blocked`",
        "selected persistence/diagnostics fix target: none",
        "Actual persistence/diagnostics evidence bundles are still missing",
        "No concrete persistence or diagnostics hardening fix has been implemented",
        "Production readiness is not claimable",
    ):
        assert expected in note


def test_phase12_3_completion_note_preserves_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "persistence implementation",
        "diagnostics implementation",
        "save/load behavior changes",
        "replay behavior changes",
        "artifact behavior changes",
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


def test_roadmap_advances_to_phase12_4_after_phase12_3():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 12 — concrete evidence-backed production hardening**.",
        "Current slice: **Phase 12.4 — player-safe error/redaction evidence capture or hardening**.",
        "Latest source-of-truth SHA before Phase 12.4: `3ccde744e6b84a6f0f2d28596b5e167280870778`.",
        "| #351 Phase 12.3 persistence diagnostics evidence decision gate | `3ccde744e6b84a6f0f2d28596b5e167280870778` | Phase 12.3 | Complete | Added persistence/diagnostics evidence-decision gate proving implementation remains blocked without accepted persistence/diagnostics evidence. |",
        "- [x] Phase 12.3 — persistence/diagnostics evidence capture or hardening.",
        "- [ ] Phase 12.4 — player-safe error/redaction evidence capture or hardening.",
        "Phase 12.4 scope:",
        "Do not implement speculative player-safe error or redaction hardening without accepted player-safe error/redaction evidence.",
    ):
        assert expected in roadmap
