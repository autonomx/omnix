from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_6_targeted_endurance_hardening.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"
PHASE9_5_NOTE = ROOT / "docs" / "plans" / "rpg_phase9_5_completion_note.md"

TAXONOMY = (
    "harness_entrypoint_failure",
    "runtime_authority_failure",
    "turn_execution_failure",
    "save_load_checkpoint_failure",
    "artifact_contract_failure",
    "progress_quality_failure",
    "performance_budget_failure",
    "provider_boundary_failure",
    "world_continuity_failure",
    "operator_evidence_gap",
)

EVIDENCE_SOURCES = (
    "autoplay-summary.json",
    "autoplay-transcript.json",
    "autoplay-campaign-results.zip",
    "save/load checkpoint",
    "package/disk replay",
    "operator evidence summary",
    "CI failure with source-backed logs",
    "production-like resource/timing note",
)


def test_phase9_6_plan_requires_concrete_evidence_before_hardening():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.6 records the deterministic intake contract",
        "prevent speculative hardening",
        "Runtime or harness fixes should be selected from concrete evidence",
        "If the evidence is missing, classify the next action as `operator_evidence_gap`",
        "Do not start runtime hardening until a concrete evidence source identifies the target failure mode",
        "Phase 9.7 — operator evidence intake contract.",
    ):
        assert expected in plan
    for source in EVIDENCE_SOURCES:
        assert source in plan
    for category in TAXONOMY:
        assert category in plan


def test_phase9_6_selection_rules_preserve_order_and_authority():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "target `artifact_contract_failure` before changing runtime behavior",
        "target `save_load_checkpoint_failure` before narrative or UI changes",
        "target `progress_quality_failure` before performance tuning",
        "target `performance_budget_failure` with the operator timing artifact attached",
        "target `world_continuity_failure` without moving truth into UI or provider code",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan


def test_phase9_6_boundary_is_provider_free_and_documentation_only():
    plan = PLAN.read_text(encoding="utf-8")
    forbidden = (
        "OpenAI API",
        "Anthropic API",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "LM Studio server",
    )
    for value in forbidden:
        assert value not in plan
    for expected in (
        "source/test/documentation only",
        "must not add:",
        "provider calls",
        "LLM calls",
        "network calls",
        "live 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
    ):
        assert expected in plan


def test_phase9_6_updates_main_production_readiness_plan_current_state():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for expected in (
        "Current phase focus: **Phase 9 — 1000-Turn Endurance Systems**.",
        "Current slice: **Phase 9.6 — targeted endurance hardening from concrete evidence**.",
        "Next recommended slice after Phase 9.6: **Phase 9.7 — operator evidence intake contract**.",
        "Phase 8 — UI/UX Production Pass: **Closed as provider-free UI/UX foundation**.",
        "Phase 9 — 1000-Turn Endurance Systems: **In progress; Phase 9.1 through Phase 9.5 complete; Phase 9.6 current**.",
        "Phase 9.1 through Phase 9.5 are complete",
        "Live/provider 1000-turn execution remains pending.",
        "Full package/disk replay evidence remains pending.",
        "Live/provider save/load checkpoint evidence remains pending.",
    ):
        assert expected in roadmap
    assert "Current phase focus: **Phase 8" not in roadmap
    assert "Phase 9 — 1000-Turn Endurance Systems: **Pending**" not in roadmap


def test_phase9_6_roadmap_aligns_with_phase9_5_completion_note():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    note = PHASE9_5_NOTE.read_text(encoding="utf-8")
    for expected in (
        "#304 Phase 9.5 performance evidence envelope",
        "#305 Phase 9.5 completion note",
        "08eda228111ac5482e16e06712ae89fe878cde47",
        "Phase 9.6 — targeted endurance hardening from concrete evidence",
    ):
        assert expected in roadmap
        assert expected in note or expected == "#304 Phase 9.5 performance evidence envelope"
    assert "Phase 9.6 — targeted endurance hardening from concrete evidence" in note
