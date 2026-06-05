# RPG Phase 11.4 Persistence and Diagnostics Evidence Runbook

Phase 11.4 defines the operator runbook for first persistence and diagnostics evidence capture.

Latest source-of-truth SHA before this Phase 11.4 slice:

- `b444fdbc83f65a7ce7d18234752c2132227b3494`

## Scope

This slice is source/test/documentation only. It does not run a live/provider campaign, change runtime behavior, mutate gameplay state, build a package in CI, or claim external release readiness.

Phase 11.4 converts the Phase 11.2 evidence backfill plan into the second concrete operator runbook: save/session/data path capture, save/load roundtrip evidence, replay/package artifacts, diagnostic logs, diagnostic bundles, redaction review, and failure reproduction notes.

## Required operator runbook sections

The first persistence and diagnostics evidence capture should include:

1. `operator_context`
2. `source_checkout`
3. `save_path_snapshot`
4. `session_path_snapshot`
5. `data_path_snapshot`
6. `report_path_snapshot`
7. `save_load_roundtrip_steps`
8. `save_load_roundtrip_result`
9. `replay_artifact_capture`
10. `package_disk_artifact_capture`
11. `diagnostic_log_capture`
12. `diagnostic_bundle_manifest`
13. `failure_reproduction_steps`
14. `redaction_review`
15. `operator_notes`
16. `persistence_diagnostics_classification`

## Required artifact paths

The runbook should ask the operator to attach or record paths for:

- save directory manifest;
- session directory manifest;
- data directory manifest;
- report directory manifest;
- save/load roundtrip transcript;
- saved state artifact;
- replay artifact;
- package/disk artifact;
- diagnostic log files;
- diagnostic bundle archive;
- failure reproduction note;
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
- save/session/data/report directory paths;
- command or manual steps used for save/load roundtrip;
- exit status or observed result for roundtrip, replay, and diagnostic collection;
- whether secrets, tokens, provider keys, personal data, and sensitive local paths were redacted.

## Classifications

Use one or more of these classifications:

- `persistence_diagnostics_capture_not_started`
- `save_path_capture_gap`
- `session_path_capture_gap`
- `data_path_capture_gap`
- `report_path_capture_gap`
- `save_load_roundtrip_capture_gap`
- `saved_state_artifact_gap`
- `replay_artifact_capture_gap`
- `package_disk_artifact_capture_gap`
- `diagnostic_log_capture_gap`
- `diagnostic_bundle_capture_gap`
- `failure_reproduction_gap`
- `redaction_review_gap`
- `persistence_diagnostics_ready_for_triage`

## Classification rules

Use `persistence_diagnostics_capture_not_started` when no persistence/diagnostics evidence bundle is attached.

Use path-specific `*_path_capture_gap` labels when the corresponding save, session, data, or report path is missing, ambiguous, or not tied to the exact checkout.

Use `save_load_roundtrip_capture_gap` when the save/load roundtrip transcript, command, manual steps, or observed result is missing or not reproducible.

Use `saved_state_artifact_gap`, `replay_artifact_capture_gap`, or `package_disk_artifact_capture_gap` when the corresponding artifact is missing, malformed, or not referenced from the evidence.

Use `diagnostic_log_capture_gap` or `diagnostic_bundle_capture_gap` when diagnostic logs, bundle archives, or bundle manifests are missing or unusable.

Use `failure_reproduction_gap` when reproduction steps are absent or not tied to source-backed artifacts.

Use `redaction_review_gap` when the evidence bundle does not confirm secrets and sensitive local details were redacted.

Use `persistence_diagnostics_ready_for_triage` only when persistence and diagnostics evidence is complete enough to classify a concrete hardening target without speculation.

## No-evidence decision for this slice

Because this Phase 11.4 slice does not attach a concrete persistence/diagnostics evidence bundle, the current classification is:

- classification: `persistence_diagnostics_capture_not_started`
- secondary classification: `operator_evidence_backfill_required`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Deterministic boundary

Phase 11.4 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- package building in CI;
- external release claims without evidence.

Simulation/runtime remains authoritative. Persistence and diagnostics evidence labels are evidence surfaces only and must not decide gameplay truth.

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

# Capture save/session/data/report paths
<path discovery command> 2>&1 | tee operator-paths-transcript.txt

# Capture save/load roundtrip evidence
<save-load command or manual steps> 2>&1 | tee operator-save-load-roundtrip-transcript.txt

# Capture replay/package artifacts
<artifact capture command> 2>&1 | tee operator-replay-artifact-transcript.txt

# Capture diagnostics
<diagnostic collection command> 2>&1 | tee operator-diagnostics-transcript.txt
```

## Stop condition

Phase 11.4 is complete when the repository has CI-gated documentation/tests proving that the first persistence and diagnostics evidence capture has a runbook, missing evidence maps to explicit gaps, and hardening remains blocked until evidence identifies a narrow target.

## Recommended next slice

After Phase 11.4, continue with:

- Phase 11.5 — first player-safe error and redaction evidence capture runbook.
