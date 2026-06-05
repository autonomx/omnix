# RPG Phase 11.3 Package Install Run Evidence Runbook

Phase 11.3 defines the operator runbook for first package/install/run evidence capture.

Latest source-of-truth SHA before this Phase 11.3 slice:

- `475ee40de83017911a17ed12382b7a9ed7512abb`

## Scope

This slice is source/test/documentation only. It does not build a release package in CI, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 11.3 converts the Phase 11.2 evidence backfill plan into the first concrete operator runbook: package artifact inventory, install transcript, run transcript, configuration snapshot, startup health, shutdown behavior, and diagnostic handoff.

## Required operator runbook sections

The first package/install/run evidence capture should include:

1. `operator_context`
2. `source_checkout`
3. `package_artifact_inventory`
4. `dependency_install_steps`
5. `configuration_snapshot`
6. `environment_variable_snapshot`
7. `resource_path_snapshot`
8. `data_path_snapshot`
9. `launch_command`
10. `startup_health_check`
11. `runtime_smoke_command`
12. `runtime_smoke_result`
13. `shutdown_steps`
14. `diagnostic_collection_steps`
15. `redaction_review`
16. `evidence_bundle_manifest`
17. `operator_notes`
18. `package_install_run_classification`

## Required artifact paths

The runbook should ask the operator to attach or record paths for:

- package artifact or checkout path;
- dependency install transcript;
- launch transcript;
- startup health transcript;
- runtime smoke transcript;
- shutdown transcript;
- configuration file copies or templates;
- environment variable snapshot with secrets redacted;
- resource/model path manifest;
- data/session/save/report path manifest;
- diagnostic logs;
- evidence bundle archive;
- redaction review note.

## Required metadata

The evidence capture should record:

- git SHA and branch;
- operator name or role;
- timestamp;
- operating system;
- shell;
- Python version;
- working directory;
- relevant hardware notes;
- package/checksum details if a package artifact exists;
- command used for install;
- command used for launch;
- command used for runtime smoke;
- exit status for install, launch, smoke, and shutdown;
- whether secrets, tokens, provider keys, personal data, and sensitive local paths were redacted.

## Classifications

Use one or more of these classifications:

- `package_install_run_not_started`
- `source_checkout_gap`
- `package_artifact_gap`
- `dependency_install_transcript_gap`
- `configuration_snapshot_gap`
- `environment_snapshot_gap`
- `resource_path_snapshot_gap`
- `data_path_snapshot_gap`
- `launch_transcript_gap`
- `startup_health_gap`
- `runtime_smoke_gap`
- `shutdown_transcript_gap`
- `diagnostic_collection_gap`
- `redaction_review_gap`
- `evidence_bundle_gap`
- `package_install_run_ready_for_triage`

## Classification rules

Use `package_install_run_not_started` when no package/install/run evidence bundle is attached.

Use `source_checkout_gap` when the evidence is not tied to a concrete checkout path, branch, and git SHA.

Use `package_artifact_gap` when an intended package artifact is missing, ambiguous, or lacks checksum details.

Use `dependency_install_transcript_gap`, `launch_transcript_gap`, `startup_health_gap`, `runtime_smoke_gap`, or `shutdown_transcript_gap` when the corresponding transcript or exit status is missing, failing, or not reproducible.

Use `configuration_snapshot_gap`, `environment_snapshot_gap`, `resource_path_snapshot_gap`, or `data_path_snapshot_gap` when the corresponding configuration, environment, resource/model, or data/session/save/report details are missing or ambiguous.

Use `diagnostic_collection_gap` when diagnostic logs or collection steps are missing.

Use `redaction_review_gap` when the evidence bundle does not confirm secrets and sensitive local details were redacted.

Use `evidence_bundle_gap` when the evidence archive or manifest is missing or incomplete.

Use `package_install_run_ready_for_triage` only when package/install/run evidence is complete enough to classify a concrete hardening target without speculation.

## No-evidence decision for this slice

Because this Phase 11.3 slice does not attach a concrete operator evidence bundle, the current classification is:

- classification: `package_install_run_not_started`
- secondary classification: `operator_evidence_backfill_required`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Deterministic boundary

Phase 11.3 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- package building in CI;
- external release claims without evidence.

Simulation/runtime remains authoritative. Package/install/run evidence labels are evidence surfaces only and must not decide gameplay truth.

## Operator command template

Record the exact commands used by the operator. Do not invent successful commands in repo documentation.

Suggested placeholders:

```text
# Capture checkout and revision
pwd
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD

# Capture environment
python --version

# Capture install transcript
<install command> 2>&1 | tee operator-install-transcript.txt

# Capture launch transcript
<launch command> 2>&1 | tee operator-launch-transcript.txt

# Capture runtime smoke transcript
<smoke command> 2>&1 | tee operator-runtime-smoke-transcript.txt

# Capture shutdown transcript
<shutdown steps> 2>&1 | tee operator-shutdown-transcript.txt
```

## Stop condition

Phase 11.3 is complete when the repository has CI-gated documentation/tests proving that the first package/install/run evidence capture has a runbook, missing evidence maps to explicit gaps, and hardening remains blocked until evidence identifies a narrow target.

## Recommended next slice

After Phase 11.3, continue with:

- Phase 11.4 — first persistence and diagnostics evidence capture runbook.
