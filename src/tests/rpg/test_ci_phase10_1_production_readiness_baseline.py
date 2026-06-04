from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_1_production_readiness_baseline.md"

EVIDENCE_CATEGORIES = (
    "package_layout_evidence",
    "install_command_evidence",
    "run_command_evidence",
    "configuration_evidence",
    "model_resource_evidence",
    "data_directory_evidence",
    "save_load_persistence_evidence",
    "log_diagnostics_evidence",
    "player_safe_error_evidence",
    "platform_environment_evidence",
    "artifact_bundle_evidence",
    "rollback_recovery_evidence",
    "release_blocker_classification",
)

CLASSIFICATIONS = (
    "production_evidence_gap",
    "packaging_contract_gap",
    "install_run_gap",
    "configuration_gap",
    "resource_layout_gap",
    "persistence_gap",
    "diagnostics_gap",
    "player_safe_error_gap",
    "platform_compatibility_gap",
    "release_candidate_ready",
)

RULES = (
    "Use `production_evidence_gap` when no concrete install/run/package evidence is attached.",
    "Use `packaging_contract_gap` when the package layout, launch artifact, or artifact bundle is missing or malformed.",
    "Use `install_run_gap` when install or run commands are missing, fail, or cannot be reproduced from the evidence.",
    "Use `configuration_gap` when required environment variables, provider settings, model paths, or config files are missing or ambiguous.",
    "Use `resource_layout_gap` when model, resource, session, data, or static asset paths are missing or inconsistent.",
    "Use `persistence_gap` when save/load, session persistence, or replay persistence evidence is missing or failing.",
    "Use `diagnostics_gap` when logs, error reports, or diagnostic artifacts are missing or unusable.",
    "Use `player_safe_error_gap` when errors expose raw internals without a safe player-facing message or recovery instruction.",
    "Use `platform_compatibility_gap` when the evidence only works on one unrecorded environment or omits platform requirements.",
    "Use `release_candidate_ready` only when concrete evidence covers packaging, install, run, config, resources, persistence, diagnostics, player-safe errors, and platform environment without blocking gaps.",
)


def test_phase10_1_records_scope_and_no_release_claim():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.1 starts production packaging",
        "source/test/documentation only",
        "does not build a release package",
        "does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness",
        "production packaging, install/run stability, persistence safety, logging, and player-safe error handling",
        "Phase 10.2 — install/run configuration evidence envelope",
    ):
        assert expected in plan


def test_phase10_1_required_evidence_categories_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for category in EVIDENCE_CATEGORIES:
        assert category in plan
    for expected in (
        "git SHA and branch",
        "operating system and shell",
        "Python version and environment setup",
        "package or launch artifact path",
        "exact install command",
        "exact run command",
        "required environment variables and config files",
        "model/resource directory expectations",
        "data/session/save directory expectations",
        "save/load persistence smoke evidence",
        "log file paths and diagnostic artifact references",
        "expected player-safe error surfaces",
        "rollback or recovery instructions",
        "known release blockers",
    ):
        assert expected in plan


def test_phase10_1_classifications_and_rules_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for classification in CLASSIFICATIONS:
        assert classification in plan
    for rule in RULES:
        assert rule in plan


def test_phase10_1_no_evidence_maps_to_production_evidence_gap():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `production_evidence_gap`",
        "allowed changes: documentation and deterministic source guards only",
        "disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims",
        "does not attach a built package",
        "install transcript",
        "run transcript",
        "persistence smoke artifact",
        "diagnostics bundle",
    ):
        assert expected in plan


def test_phase10_1_boundary_is_provider_free_and_non_mutating():
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
        "external release claims without evidence",
        "Simulation/runtime remains authoritative",
        "must not decide gameplay truth",
    ):
        assert expected in plan
