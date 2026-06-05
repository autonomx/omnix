# RPG Phase 10.2 Install/Run Configuration Evidence Envelope

Phase 10.2 records the evidence envelope for reproducible install/run configuration.

Latest source-of-truth SHA before this Phase 10.2 slice:

- `c158b80e77768f819c8405dc14976eeaf42c2169`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 10.2 defines the evidence required to reproduce install and run behavior across operator environments before any release-readiness claim.

## Required install/run evidence sections

A production install/run evidence summary should include:

1. `operator_environment`
2. `repository_checkout`
3. `dependency_install`
4. `configuration_files`
5. `environment_variables`
6. `model_resource_paths`
7. `data_session_paths`
8. `launch_command`
9. `startup_health_check`
10. `runtime_smoke_result`
11. `shutdown_result`
12. `diagnostic_log_paths`
13. `failure_recovery_notes`
14. `install_run_classification`

## Required fields

The install/run evidence summary should record concrete values for:

- git SHA and branch;
- operating system, shell, CPU/GPU notes, and working directory;
- Python version, virtual environment, and dependency install command;
- package manager and lockfile status;
- exact configuration files read by the application;
- required and optional environment variables;
- provider endpoint configuration without secrets;
- model, resource, static, data, session, and save directory paths;
- exact launch command;
- startup URL or health-check command;
- expected ports and services;
- first successful runtime action or smoke command;
- shutdown command and shutdown result;
- log file and diagnostic artifact paths;
- failure recovery or rollback notes;
- selected install/run classification.

## Install/run classifications

Use one of these classifications:

- `install_run_evidence_gap`
- `checkout_gap`
- `dependency_install_gap`
- `configuration_file_gap`
- `environment_variable_gap`
- `provider_config_gap`
- `resource_path_gap`
- `data_path_gap`
- `startup_health_gap`
- `runtime_smoke_gap`
- `shutdown_gap`
- `diagnostic_log_gap`
- `install_run_ready`

## Classification rules

Use `install_run_evidence_gap` when no concrete install/run transcript or operator evidence is attached.

Use `checkout_gap` when the git SHA, branch, checkout path, or repository state is missing or inconsistent.

Use `dependency_install_gap` when dependency installation is missing, failing, non-reproducible, or not tied to a recorded command.

Use `configuration_file_gap` when required configuration files are missing, ambiguous, or not recorded.

Use `environment_variable_gap` when required environment variables are missing or ambiguous.

Use `provider_config_gap` when provider endpoint settings are missing, ambiguous, secret-leaking, or not separated from runtime truth.

Use `resource_path_gap` when model, resource, or static asset paths are missing or inconsistent.

Use `data_path_gap` when data, session, save, or report paths are missing or inconsistent.

Use `startup_health_gap` when startup output, URL, port, or health-check evidence is missing or failing.

Use `runtime_smoke_gap` when no first action, smoke command, or equivalent runtime evidence is attached.

Use `shutdown_gap` when shutdown behavior is missing, hanging, or not recorded.

Use `diagnostic_log_gap` when logs or diagnostic artifact paths are missing or unusable.

Use `install_run_ready` only when concrete evidence covers checkout, dependency install, configuration files, environment variables, provider settings, resource paths, data paths, startup health, runtime smoke, shutdown, and diagnostics without blocking gaps.

## No-evidence decision for this slice

Because this Phase 10.2 slice does not attach an install transcript, run transcript, startup health artifact, runtime smoke artifact, shutdown artifact, or diagnostic log bundle, the current install/run classification is:

- classification: `install_run_evidence_gap`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims

## Deterministic boundary

Phase 10.2 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- external release claims without evidence.

Simulation/runtime remains authoritative. Install/run labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 10.2 is complete when the repository has CI-gated documentation/tests proving that install/run readiness requires concrete operator transcripts, absent evidence maps to `install_run_evidence_gap`, and this slice does not claim release readiness.

## Recommended next slice

After Phase 10.2, continue with:

- Phase 10.3 — persistence and diagnostics evidence envelope.
