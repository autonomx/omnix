from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "docs" / "plans" / "rpg_phase10_2_install_run_configuration_evidence_envelope.md"

SECTIONS = (
    "operator_environment",
    "repository_checkout",
    "dependency_install",
    "configuration_files",
    "environment_variables",
    "model_resource_paths",
    "data_session_paths",
    "launch_command",
    "startup_health_check",
    "runtime_smoke_result",
    "shutdown_result",
    "diagnostic_log_paths",
    "failure_recovery_notes",
    "install_run_classification",
)

CLASSIFICATIONS = (
    "install_run_evidence_gap",
    "checkout_gap",
    "dependency_install_gap",
    "configuration_file_gap",
    "environment_variable_gap",
    "provider_config_gap",
    "resource_path_gap",
    "data_path_gap",
    "startup_health_gap",
    "runtime_smoke_gap",
    "shutdown_gap",
    "diagnostic_log_gap",
    "install_run_ready",
)


def test_phase10_2_records_scope_and_required_sections():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "Phase 10.2 records the evidence envelope",
        "source/test/documentation only",
        "does not build a release package",
        "does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness",
        "Phase 10.3 — persistence and diagnostics evidence envelope",
    ):
        assert expected in plan
    for section in SECTIONS:
        assert section in plan


def test_phase10_2_required_fields_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "git SHA and branch",
        "operating system, shell, CPU/GPU notes, and working directory",
        "Python version, virtual environment, and dependency install command",
        "package manager and lockfile status",
        "exact configuration files read by the application",
        "required and optional environment variables",
        "provider endpoint configuration without secrets",
        "model, resource, static, data, session, and save directory paths",
        "exact launch command",
        "startup URL or health-check command",
        "expected ports and services",
        "first successful runtime action or smoke command",
        "shutdown command and shutdown result",
        "log file and diagnostic artifact paths",
        "failure recovery or rollback notes",
    ):
        assert expected in plan


def test_phase10_2_classifications_are_guarded():
    plan = PLAN.read_text(encoding="utf-8")
    for classification in CLASSIFICATIONS:
        assert classification in plan
    for expected in (
        "Use `install_run_evidence_gap` when no concrete install/run transcript or operator evidence is attached.",
        "Use `dependency_install_gap` when dependency installation is missing, failing, non-reproducible, or not tied to a recorded command.",
        "Use `provider_config_gap` when provider endpoint settings are missing, ambiguous, secret-leaking, or not separated from runtime truth.",
        "Use `install_run_ready` only when concrete evidence covers checkout, dependency install, configuration files, environment variables, provider settings, resource paths, data paths, startup health, runtime smoke, shutdown, and diagnostics without blocking gaps.",
    ):
        assert expected in plan


def test_phase10_2_no_evidence_maps_to_install_run_gap():
    plan = PLAN.read_text(encoding="utf-8")
    for expected in (
        "classification: `install_run_evidence_gap`",
        "allowed changes: documentation and deterministic source guards only",
        "disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims",
        "does not attach an install transcript",
        "run transcript",
        "startup health artifact",
        "runtime smoke artifact",
        "shutdown artifact",
        "diagnostic log bundle",
    ):
        assert expected in plan


def test_phase10_2_boundary_is_provider_free_and_non_mutating():
    plan = PLAN.read_text(encoding="utf-8")
    forbidden = (
        "OpenAI API",
        "Anthropic API",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
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
