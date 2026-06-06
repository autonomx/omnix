from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase13_2_performance_hardening.md"
NOTE = ROOT / "docs" / "plans" / "rpg_phase13_2_completion_note.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase13_2_plan_records_accepted_performance_evidence():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "autoplay-2-n113-smoke.zip",
        "average wall time was approximately 18 seconds per turn",
        "player-agent action selection took roughly 4 to 6 seconds per turn",
        "runtime turn execution took roughly 11 to 13 seconds per turn",
        "emit structured autoplay performance summary artifacts",
        "advisory-only and do not decide simulation truth",
    ):
        assert expected in plan


def test_phase13_2_plan_guards_boundary_and_acceptance():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "deterministic tests prove slow 5-turn smoke-shaped rows produce warning classifications",
        "performance JSON and HTML are appended to the autoplay ZIP under `performance/`",
        "runtime, provider, gameplay, UI authority, live provider calls, and package building are unchanged",
        "Simulation/runtime remains authoritative",
        "Performance labels are advisory evidence surfaces only",
        "Phase 13.3 — production readiness evidence review after first hardening target",
    ):
        assert expected in plan


def test_phase13_2_completion_note_records_first_hardening_implementation():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 13.2 is complete as the first accepted evidence-backed hardening implementation",
        "autoplay-2-n113-smoke.zip",
        "writes advisory performance JSON/HTML artifacts",
        "appends matching artifacts to the results ZIP under `performance/`",
        "This slice adds measurement and report hardening, not a runtime latency reduction",
        "Production readiness is not claimable",
    ):
        assert expected in note


def test_roadmap_advances_to_phase13_3_after_phase13_2():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 13.3 — production readiness evidence review after first hardening target**.",
        "- [x] Phase 13.2 — first accepted hardening target implementation after evidence attachment.",
        "- [ ] Phase 13.3 — production readiness evidence review after first hardening target.",
        "Phase 13.3 scope:",
        "Review the next 5-turn smoke with structured performance artifacts.",
    ):
        assert expected in roadmap
