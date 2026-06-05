# RPG Phase 10.5 Release Candidate Packaging Contract

Phase 10.5 records the evidence contract for release-candidate packaging.

Latest source-of-truth SHA before this Phase 10.5 slice:

- `ba12cfc91d7fed7743634ed86c5baadc01833749`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 10.5 defines the evidence required before any packaged build can be called a release candidate.

## Required release-candidate packaging sections

A release-candidate packaging evidence summary should include:

1. `source_revision_evidence`
2. `package_manifest_evidence`
3. `artifact_inventory_evidence`
4. `dependency_lock_evidence`
5. `configuration_template_evidence`
6. `model_resource_manifest_evidence`
7. `data_directory_manifest_evidence`
8. `launch_script_evidence`
9. `install_run_transcript_evidence`
10. `persistence_smoke_evidence`
11. `diagnostic_bundle_evidence`
12. `player_safe_error_evidence`
13. `release_notes_evidence`
14. `known_blocker_evidence`
15. `rollback_recovery_evidence`
16. `release_candidate_classification`

## Required fields

The release-candidate packaging summary should record concrete values for:

- git SHA and branch;
- package name, version, and build identifier;
- package artifact paths and checksums;
- package manifest or file inventory;
- dependency lockfile status;
- configuration template paths and required variable documentation;
- model, resource, static, data, session, save, and report directory manifests;
- exact launch scripts or commands;
- install transcript and run transcript paths;
- persistence smoke artifact paths;
- diagnostic bundle artifact paths;
- player-safe error evidence paths;
- release notes path;
- known blockers and release exclusions;
- rollback, recovery, and uninstall instructions;
- selected release-candidate classification.

## Classifications

Use one or more of these classifications:

- `release_candidate_evidence_gap`
- `source_revision_gap`
- `package_manifest_gap`
- `artifact_inventory_gap`
- `dependency_lock_gap`
- `configuration_template_gap`
- `model_resource_manifest_gap`
- `data_directory_manifest_gap`
- `launch_script_gap`
- `install_run_transcript_gap`
- `persistence_smoke_gap`
- `diagnostic_bundle_gap`
- `player_safe_error_gap`
- `release_notes_gap`
- `known_blocker_gap`
- `rollback_recovery_gap`
- `release_candidate_ready`

## Classification rules

Use `release_candidate_evidence_gap` when no concrete release-candidate package or evidence bundle is attached.

Use `source_revision_gap` when the package cannot be tied to an exact git SHA and branch.

Use `package_manifest_gap` or `artifact_inventory_gap` when package contents are missing, ambiguous, or not inspectable.

Use `dependency_lock_gap` when dependency lockfile status is missing or inconsistent with the packaged artifact.

Use `configuration_template_gap` when config templates, required variables, or operator configuration instructions are missing.

Use `model_resource_manifest_gap` or `data_directory_manifest_gap` when model/resource/data/session/save/report directory expectations are missing or inconsistent.

Use `launch_script_gap` when launch scripts or commands are missing, ambiguous, or not reproducible.

Use `install_run_transcript_gap` when install/run transcripts are missing or do not match the packaged artifact.

Use `persistence_smoke_gap` when save/load or persistence smoke evidence is missing or failing.

Use `diagnostic_bundle_gap` when diagnostic bundle evidence is missing or unusable.

Use `player_safe_error_gap` when player-safe error evidence is missing for the release candidate.

Use `release_notes_gap`, `known_blocker_gap`, or `rollback_recovery_gap` when release notes, known blocker tracking, or recovery instructions are missing.

Use `release_candidate_ready` only when concrete evidence covers source revision, package manifest, artifact inventory, dependency lock status, configuration templates, model/resource/data manifests, launch scripts, install/run transcripts, persistence smoke, diagnostics, player-safe errors, release notes, blockers, and rollback/recovery without blocking gaps.

## No-evidence decision for this slice

Because this Phase 10.5 slice does not attach a built package, package manifest, install/run transcript, persistence smoke artifact, diagnostic bundle, player-safe error evidence, or release notes, the current classification is:

- classification: `release_candidate_evidence_gap`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims

## Deterministic boundary

Phase 10.5 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- external release claims without evidence.

Simulation/runtime remains authoritative. Release-candidate labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 10.5 is complete when the repository has CI-gated documentation/tests proving that release-candidate readiness requires concrete package evidence, absent evidence maps to `release_candidate_evidence_gap`, and this slice does not claim release readiness.

## Recommended next slice

After Phase 10.5, continue with:

- Phase 10.6 — operator release evidence intake checklist.
