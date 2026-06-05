# RPG Phase 10.3 Persistence and Diagnostics Evidence Envelope

Phase 10.3 records the evidence envelope for production persistence and diagnostics.

Latest source-of-truth SHA before this Phase 10.3 slice:

- `c1b0dd46b318bd28560e3bea2acdb436fabe0851`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 10.3 defines the evidence required to prove save/session/data persistence and diagnostics are safe enough for production packaging review.

## Required persistence evidence sections

A persistence evidence summary should include:

1. `save_path_evidence`
2. `session_path_evidence`
3. `data_path_evidence`
4. `save_load_roundtrip_evidence`
5. `replay_artifact_evidence`
6. `package_disk_artifact_evidence`
7. `artifact_bundle_members`
8. `migration_compatibility_evidence`
9. `backup_recovery_evidence`
10. `corruption_recovery_evidence`
11. `persistence_classification`

## Required diagnostics evidence sections

A diagnostics evidence summary should include:

1. `log_path_evidence`
2. `error_report_evidence`
3. `diagnostic_bundle_evidence`
4. `operator_collection_steps`
5. `failure_reproduction_steps`
6. `redaction_sensitive_data_evidence`
7. `player_safe_internal_separation`
8. `diagnostics_classification`

## Required fields

The persistence and diagnostics summary should record concrete values for:

- git SHA and branch;
- operating system and working directory;
- save, session, data, report, and replay directory paths;
- save/load roundtrip command or manual steps;
- replay/package artifact paths and bundle members;
- migration or schema compatibility notes;
- backup, rollback, and recovery instructions;
- corruption or missing-file recovery behavior;
- log file paths and retention expectations;
- error report paths and diagnostic bundle paths;
- operator diagnostic collection steps;
- failure reproduction steps;
- sensitive-data redaction expectations;
- separation between player-safe messages and internal diagnostics;
- selected persistence and diagnostics classifications.

## Classifications

Use one or more of these classifications:

- `persistence_diagnostics_evidence_gap`
- `save_path_gap`
- `session_path_gap`
- `data_path_gap`
- `save_load_roundtrip_gap`
- `replay_artifact_gap`
- `package_disk_artifact_gap`
- `artifact_bundle_gap`
- `migration_compatibility_gap`
- `backup_recovery_gap`
- `corruption_recovery_gap`
- `diagnostic_log_gap`
- `diagnostic_bundle_gap`
- `reproduction_steps_gap`
- `redaction_gap`
- `player_safe_internal_separation_gap`
- `persistence_diagnostics_ready`

## Classification rules

Use `persistence_diagnostics_evidence_gap` when no concrete persistence or diagnostic artifact evidence is attached.

Use `save_path_gap`, `session_path_gap`, or `data_path_gap` when the relevant storage path is missing, ambiguous, or inconsistent.

Use `save_load_roundtrip_gap` when save/load roundtrip evidence is missing, failing, or not reproducible from the recorded steps.

Use `replay_artifact_gap` or `package_disk_artifact_gap` when replay or package/disk artifacts are missing, malformed, or not referenced from the evidence.

Use `artifact_bundle_gap` when bundle members are missing, inconsistent, or not inspectable.

Use `migration_compatibility_gap` when schema, migration, or version compatibility expectations are missing or failing.

Use `backup_recovery_gap` or `corruption_recovery_gap` when recovery behavior is missing, unsafe, or not documented.

Use `diagnostic_log_gap` or `diagnostic_bundle_gap` when logs, error reports, or diagnostic bundles are missing or unusable.

Use `reproduction_steps_gap` when failures cannot be reproduced from the operator notes.

Use `redaction_gap` when diagnostic collection may expose secrets, tokens, provider keys, personal data, or unredacted local paths beyond the intended diagnostic scope.

Use `player_safe_internal_separation_gap` when internal stack traces or debug details leak into player-facing errors without a safe recovery message.

Use `persistence_diagnostics_ready` only when concrete evidence covers persistence paths, save/load roundtrip, replay/package artifacts, bundle members, migration compatibility, backup/recovery, corruption recovery, diagnostics, reproduction steps, redaction, and player-safe/internal separation without blocking gaps.

## No-evidence decision for this slice

Because this Phase 10.3 slice does not attach save/load roundtrip evidence, replay/package artifacts, diagnostic bundles, logs, reproduction steps, or redaction evidence, the current classification is:

- classification: `persistence_diagnostics_evidence_gap`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims

## Deterministic boundary

Phase 10.3 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- external release claims without evidence.

Simulation/runtime remains authoritative. Persistence and diagnostics labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 10.3 is complete when the repository has CI-gated documentation/tests proving that persistence and diagnostics readiness requires concrete artifacts, absent evidence maps to `persistence_diagnostics_evidence_gap`, and this slice does not claim release readiness.

## Recommended next slice

After Phase 10.3, continue with:

- Phase 10.4 — player-safe error handling evidence envelope.
