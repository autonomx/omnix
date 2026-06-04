from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOTE = ROOT / "docs" / "plans" / "rpg_phase9_8_completion_note.md"
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_8_long_run_continuity_evidence_envelope.md"
ROADMAP = ROOT / "docs" / "plans" / "rpg_production_readiness_plan.md"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-phase0-architecture-compliance.yml"


def test_phase9_8_completion_note_records_implementation_and_checks():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.8 long-run continuity evidence envelope is complete.",
        "Implementation PR: #310",
        "95bffcf9e827f9deec73bc3f8723fef08bc9280f",
        "7b4c1a944ecd1e522681c155efe0df0acc689e1f",
        "RPG Phase 0 architecture compliance",
        "RPG deterministic PR gates",
    ):
        assert expected in note


def test_phase9_8_completion_note_records_scope_and_boundary():
    note = NOTE.read_text(encoding="utf-8")
    for expected in (
        "deterministic, provider-free evidence envelope",
        "without requiring a live/provider 100-turn or 1000-turn campaign in CI",
        "did not add provider calls",
        "did not add provider calls, LLM calls, network calls",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "operator_evidence_gap",
    ):
        assert expected in note


def test_phase9_8_completion_note_matches_continuity_envelope():
    note = NOTE.read_text(encoding="utf-8")
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "combat_continuity",
        "npc_memory_continuity",
        "party_continuity",
        "travel_continuity",
        "time_continuity",
        "weather_continuity",
        "quest_continuity",
        "reward_continuity",
        "economy_inventory_continuity",
        "save_load_continuity",
        "replay_continuity",
        "world_continuity_failure",
        "save_load_checkpoint_failure",
        "progress_quality_failure",
        "operator_evidence_gap",
    ):
        assert expected in plan
    for expected in (
        "combat continuity",
        "NPC memory continuity",
        "party continuity",
        "travel continuity",
        "time continuity",
        "weather continuity",
        "quest continuity",
        "reward continuity",
        "economy and inventory continuity",
        "save/load continuity",
        "replay continuity",
        "progress-quality continuity",
        "provider-boundary continuity",
        "runtime-authority continuity",
    ):
        assert expected in note


def test_phase9_8_roadmap_and_architecture_workflow_are_aligned():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for expected in (
        "Current slice: **Phase 9.8 — long-run continuity evidence envelope**.",
        "Next recommended slice after Phase 9.8: **Phase 9.9 — targeted endurance hardening from concrete evidence**.",
        "Phase 9.1 through Phase 9.7 are complete",
        "Phase 9.8 scope:",
        "docs/plans/rpg_phase9_8_long_run_continuity_evidence_envelope.md",
        "src/tests/rpg/test_ci_phase9_8_long_run_continuity_evidence_envelope.py",
    ):
        assert expected in roadmap
    for expected in (
        "src/tests/rpg/test_ci_phase9_8_long_run_continuity_evidence_envelope.py",
        "docs/plans/rpg_phase9_8_long_run_continuity_evidence_envelope.md",
    ):
        assert expected in workflow
