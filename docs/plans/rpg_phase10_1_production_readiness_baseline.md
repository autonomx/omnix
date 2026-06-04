# RPG Phase 10.1 Production Readiness Baseline and Packaging Evidence Plan

Phase 10.1 starts production packaging, stability, and release-readiness evidence.

Latest source-of-truth SHA before this Phase 10.1 slice:

- `154c8076a59d9fa82f40e76ba08310f0e52dee21`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 10.1 defines the evidence categories required before production packaging, install/run stability, persistence safety, logging, and player-safe error handling can be considered ready.

## Required evidence categories

A production readiness evidence summary should include:

1. `package_layout_evidence`
2. `install_command_evidence`
3. `run_command_evidence`
4. `configuration_evidence`
5. `model_resource_evidence`
6. `data_directory_evidence`
7. `save_load_persistence_evidence`
8. `log_diagnostics_evidence`
9. `player_safe_error_evidence`
10. `platform_environment_evidence`
11. `artifact_bundle_evidence`
12. `rollback_recovery_evidence`
13. `release_blocker_classification`

## Required fields

The production readiness summary should record concrete values for:

- git SHA and branch;
- operating system and shell;
- Python version and environment setup;
- package or launch artifact path;
- exact install command;
- exact run command;
- required environment variables and config files;
- model/resource directory expectations;
- data/session/save directory expectations;
- save/load persistence smoke evidence;
- log file paths and diagnostic artifact references;
- expected player-safe error surfaces;
- rollback or recovery instructions;
- known release blockers;
- selected release-readiness classification.

## Release-readiness classifications

Use one of these classifications:

- `production_evidence_gap`
- `packaging_contract_gap`
- `install_run_gap`
- `configuration_gap`
- `resource_layout_gap`
- `persistence_gap`
- `diagnostics_gap`
- `player_safe_error_gap`
- `platform_compatibility_gap`
- `release_candidate_ready`

## Classification rules

Use `production_evidence_gap` when no concrete install/run/package evidence is attached.

Use `packaging_contract_gap` when the package layout, launch artifact, or artifact bundle is missing or malformed.

Use `install_run_gap` when install or run commands are missing, fail, or cannot be reproduced from the evidence.

Use `configuration_gap` when required environment variables, provider settings, model paths, or config files are missing or ambiguous.

Use `resource_layout_gap` when model, resource, session, data, or static asset paths are missing or inconsistent.

Use `persistence_gap` when save/load, session persistence, or replay persistence evidence is missing or failing.

Use `diagnostics_gap` when logs, error reports, or diagnostic artifacts are missing or unusable.

Use `player_safe_error_gap` when errors expose raw internals without a safe player-facing message or recovery instruction.

Use `platform_compatibility_gap` when the evidence only works on one unrecorded environment or omits platform requirements.

Use `release_candidate_ready` only when concrete evidence covers packaging, install, run, config, resources, persistence, diagnostics, player-safe errors, and platform environment without blocking gaps.

## No-evidence decision for this slice

Because this Phase 10.1 slice does not attach a built package, install transcript, run transcript, persistence smoke artifact, or diagnostics bundle, the current release-readiness classification is:

- classification: `production_evidence_gap`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims

## Deterministic boundary

Phase 10.1 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- external release claims without evidence.

Simulation/runtime remains authoritative. Production readiness labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 10.1 is complete when the repository has CI-gated documentation/tests proving that production readiness requires concrete packaging/install/run evidence, absent evidence maps to `production_evidence_gap`, and this slice does not claim release readiness.

## Recommended next slice

After Phase 10.1, continue with:

- Phase 10.2 — install/run configuration evidence envelope.
