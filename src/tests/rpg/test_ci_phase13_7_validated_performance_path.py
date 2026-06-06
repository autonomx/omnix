from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase13_7_validated_performance_path.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase13_7_plan_requires_evidence_before_broadening():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "latency-reduced matrix ZIP",
        "source checkout SHA",
        "latency-reduction evidence review payload",
        "proof that the Phase 13.4 runner was enabled",
        "provider-backed average latency improvement of at least 15%",
        "deterministic fast-path average at or below 1.0 second",
        "p95 turn time not regressed above the 6.36 second baseline",
        "max turn time not regressed above the 7.45 second baseline",
        "explicit promotion scope",
        "redaction review",
    ):
        assert expected in plan


def test_phase13_7_plan_blocks_no_evidence_broadening():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "No new latency-reduced interactive matrix evidence is attached",
        "classification: `phase13_7_no_latency_reduced_evidence`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `performance_path_broadening_blocked`",
        "selected broadening target: none",
        "documentation and deterministic source guards only",
        "default runner changes",
        "first-call routing changes",
        "speculative latency changes",
        "production readiness claims",
    ):
        assert expected in plan


def test_phase13_7_plan_preserves_authority_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Simulation/runtime remains authoritative",
        "decision labels are advisory evidence surfaces only",
        "do not decide gameplay truth",
        "does not add runtime behavior changes",
    ):
        assert expected in plan


def test_roadmap_advances_to_phase13_8_after_phase13_7():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 13.8 — production readiness evidence checkpoint or validated performance promotion**.",
        "Latest source-of-truth SHA before Phase 13.8: `17d7acb7fa7def1a8e57ecb85133ceb9e6c8f1a1`.",
        "#362 Phase 13.6 latency evidence backfill",
        "- [x] Phase 13.7 — broaden validated performance path or continue operator evidence backfill.",
        "- [ ] Phase 13.8 — production readiness evidence checkpoint or validated performance promotion.",
    ):
        assert expected in roadmap
