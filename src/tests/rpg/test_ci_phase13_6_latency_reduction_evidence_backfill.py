from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase13_6_latency_reduction_evidence_backfill.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"


def test_phase13_6_plan_requires_operator_run_and_bundle():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "python src/tests/rpg/interactive_intent_matrix_latency_reduction.py --live-provider",
        "latency-reduced matrix ZIP",
        "interactive-intent-matrix-performance.json",
        "latency-reduction-evidence-review.json",
        "source checkout SHA",
        "provider/model configuration summary",
        "redaction review",
    ):
        assert expected in plan


def test_phase13_6_plan_blocks_speculative_implementation_without_evidence():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "No new latency-reduced interactive matrix ZIP is attached",
        "classification: `phase13_6_latency_reduction_evidence_missing`",
        "secondary classification: `operator_evidence_backfill_required`",
        "implementation state: `phase13_6_implementation_blocked`",
        "selected follow-up target: none",
        "documentation and deterministic source guards only",
        "runtime behavior changes",
        "provider behavior changes",
        "first-call routing changes",
        "speculative latency changes",
        "production readiness claims",
    ):
        assert expected in plan


def test_phase13_6_plan_preserves_runtime_authority_boundary():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Simulation/runtime remains authoritative",
        "decision labels are advisory evidence surfaces only",
        "do not decide gameplay truth",
        "does not add runtime behavior changes",
        "provider calls",
        "LLM calls",
        "live endurance execution in CI",
        "gameplay mutation",
        "UI authority changes",
    ):
        assert expected in plan


def test_roadmap_advances_to_phase13_7_after_phase13_6():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 13.7 — broaden validated performance path or continue operator evidence backfill**.",
        "Latest source-of-truth SHA before Phase 13.7: `e118f182d3fc2ad91b1f42a74035d3eec1564dcd`.",
        "#361 Phase 13.5 latency reduction evidence review",
        "#360 Phase 13.4 provider-backed intent latency reduction",
        "- [x] Phase 13.6 — apply latency-reduction follow-up from live matrix evidence.",
        "- [ ] Phase 13.7 — broaden validated performance path or continue operator evidence backfill.",
        "If no latency-reduced matrix evidence is attached, continue evidence backfill rather than implementing speculative changes.",
    ):
        assert expected in roadmap
