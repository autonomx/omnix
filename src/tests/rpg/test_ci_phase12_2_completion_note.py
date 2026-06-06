from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase12_2_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase12_2_completion_note_records_pr_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 12.2 is complete as a package/install/run evidence-decision gate",
        "PR #349 — Phase 12.2 package evidence decision gate",
        "2ea2687b726540c5bea52e0ed43baa9d06901fb4",
        "5ec6b11e3b9e77dc68c18bbf0512f801407443fa",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase12_2_completion_note_preserves_blocked_state():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "classification: `phase12_2_package_evidence_not_started`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase12_2_implementation_blocked`",
        "selected package/install/run fix target: none",
        "Actual package/install/run evidence bundles are still missing",
        "No concrete package/install/run hardening fix has been implemented",
        "Production readiness is not claimable",
    ):
        assert expected in note


def test_phase12_2_completion_note_preserves_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "package implementation",
        "installer changes",
        "launch behavior changes",
        "configuration behavior changes",
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


def test_roadmap_advances_to_phase12_3_after_phase12_2():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 12 — concrete evidence-backed production hardening**.",
        "Current slice: **Phase 12.3 — persistence/diagnostics evidence capture or hardening**.",
        "Latest source-of-truth SHA before Phase 12.3: `2ea2687b726540c5bea52e0ed43baa9d06901fb4`.",
        "| #349 Phase 12.2 package evidence decision gate | `2ea2687b726540c5bea52e0ed43baa9d06901fb4` | Phase 12.2 | Complete | Added package/install/run evidence-decision gate proving implementation remains blocked without accepted package evidence. |",
        "- [x] Phase 12.2 — package/install/run evidence capture or hardening.",
        "- [ ] Phase 12.3 — persistence/diagnostics evidence capture or hardening.",
        "Phase 12.3 scope:",
        "Do not implement speculative persistence or diagnostics hardening without accepted persistence/diagnostics evidence.",
    ):
        assert expected in roadmap
