from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase9_7_operator_evidence_intake_contract.md"

REQUIRED_SECTIONS = (
    "run_metadata",
    "provider_model_config",
    "command_used",
    "artifact_bundle_paths",
    "autoplay_summary",
    "autoplay_transcript",
    "autoplay_campaign_results_zip",
    "timing_metrics",
    "final_drain_behavior",
    "background_job_behavior",
    "save_load_checkpoint_evidence",
    "package_disk_replay_evidence",
    "progress_quality_review",
    "continuity_review",
    "taxonomy_classification",
)

REQUIRED_ARTIFACTS = (
    "autoplay-summary.json",
    "autoplay-transcript.json",
    "autoplay-campaign-results.zip",
)

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

MISSING_EVIDENCE_RULES = (
    "missing live/provider run evidence should classify as `operator_evidence_gap`",
    "missing timing evidence should classify as `operator_evidence_gap`",
    "missing save/load checkpoint or replay evidence should classify as `operator_evidence_gap`",
    "missing transcript review should classify as `operator_evidence_gap`",
    "missing artifact bundle references should classify as `operator_evidence_gap`",
    "missing provider/model/config metadata should classify as `operator_evidence_gap`",
)


def test_phase9_7_operator_evidence_contract_records_scope_and_stop_condition():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 9.7 records the deterministic intake contract",
        "source/test/documentation only",
        "does not run a live/provider 100-turn or 1000-turn campaign in CI",
        "CI source guards can prove that the intake contract exists",
        "they do not prove live 1000-turn performance",
        "Phase 9.8 — long-run continuity evidence envelope",
    ):
        assert expected in plan


def test_phase9_7_required_operator_evidence_sections_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in plan
    for artifact in REQUIRED_ARTIFACTS:
        assert artifact in plan
    for expected in (
        "run date and operator",
        "git SHA and branch",
        "requested turn count and executed turn count",
        "exact command used",
        "blocking or human-equivalent turn timing",
        "autoplay wall-clock timing",
        "final drain duration and timeout status",
        "background job count and drain behavior",
        "save/load checkpoint artifact reference",
        "package/disk replay artifact reference",
    ):
        assert expected in plan


def test_phase9_7_missing_evidence_maps_to_operator_evidence_gap():
    plan = PLAN.read_text(encoding="utf-8")
    for rule in MISSING_EVIDENCE_RULES:
        assert rule in plan
    for expected in (
        "Do not treat absent evidence as a passing result",
        "Do not infer timing, replay, checkpoint, or transcript quality from CI source guards",
        "If the run completes but evidence is incomplete",
        "classify the gap explicitly as `operator_evidence_gap`",
    ):
        assert expected in plan


def test_phase9_7_taxonomy_and_runtime_authority_are_preserved():
    plan = PLAN.read_text(encoding="utf-8")
    for category in TAXONOMY:
        assert category in plan
    for expected in (
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
        "Operator evidence summaries, labels, and transcript reviews are evidence surfaces only",
    ):
        assert expected in plan


def test_phase9_7_boundary_is_provider_free_and_non_mutating():
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
        "provider calls",
        "LLM calls",
        "network calls",
        "live 100-turn or 1000-turn CI execution",
        "gameplay mutation",
        "UI authority changes",
        "command execution paths outside existing runtime validation",
    ):
        assert expected in plan
