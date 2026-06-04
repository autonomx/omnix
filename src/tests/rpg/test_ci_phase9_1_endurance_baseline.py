from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "docs" / "plans" / "rpg_phase9_1_endurance_baseline.md"
HARNESS = ROOT / "src" / "tests" / "rpg" / "autoplay_llm_campaign.py"

FAILURE_CATEGORIES = (
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


def test_phase9_1_baseline_records_current_harness_entrypoint():
    baseline = BASELINE.read_text(encoding="utf-8")
    harness = HARNESS.read_text(encoding="utf-8")
    for expected in (
        "Phase 9 begins the 1000-turn endurance systems track.",
        "src/tests/rpg/autoplay_llm_campaign.py",
        "python src/tests/rpg/autoplay_llm_campaign.py",
        "run_autoplay_campaign(args)",
        "autoplay-summary.json",
        "autoplay-transcript.json",
        "autoplay-campaign-results.zip",
        "1000-turn endurance run readiness",
    ):
        assert expected in baseline
    for expected in (
        "def run_autoplay_campaign(args):",
        "autoplay-summary.json",
        "autoplay-transcript.json",
        "autoplay-campaign-results.zip",
        "_load_autoplay_campaign_runtime()",
    ):
        assert expected in harness


def test_phase9_1_baseline_records_failure_taxonomy():
    baseline = BASELINE.read_text(encoding="utf-8")
    for category in FAILURE_CATEGORIES:
        assert category in baseline
    for expected in (
        "The harness cannot load",
        "Runtime wrapper authority drifts",
        "A turn crashes",
        "Checkpoint validation fails",
        "Summary, transcript, or ZIP artifacts are missing",
        "Objective/progress checks flag false progress",
        "Blocking/human-equivalent turn time",
        "Provider/LLM behavior is required for deterministic runtime truth",
        "Long-run continuity breaks across combat, NPC memory, party, travel, time, weather, or quest/reward state",
        "live/manual execution evidence not captured in repo-side artifacts",
    ):
        assert expected in baseline


def test_phase9_1_baseline_separates_ci_and_operator_evidence():
    baseline = BASELINE.read_text(encoding="utf-8")
    for expected in (
        "CI-gated Phase 9 evidence should cover:",
        "harness entrypoint source contract",
        "compatibility runner artifact contract",
        "runtime wrapper manifest authority",
        "deterministic taxonomy documentation",
        "provider-boundary guardrails",
        "Operator/manual evidence may cover:",
        "live/provider 100-turn or 1000-turn campaigns",
        "wall-clock performance and final drain timings",
        "package/disk replay evidence",
        "production environment resource limits",
    ):
        assert expected in baseline


def test_phase9_1_runtime_wrapper_manifest_remains_authoritative():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()
    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"


def test_phase9_1_baseline_preserves_phase9_next_slice():
    baseline = BASELINE.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.1 does not require live/provider execution in CI.",
        "runtime authority/provider boundary preservation",
        "source guards that prevent losing the baseline contract",
        "Phase 9.2 — deterministic endurance artifact contract guard.",
    ):
        assert expected in baseline
