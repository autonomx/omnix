# RPG Phase 11.2 Operator Evidence Backfill Plan

Phase 11.2 defines the operator evidence backfill plan for production hardening.

Latest source-of-truth SHA before this Phase 11.2 slice:

- `bdcd7a4e12c9f38c0d8c2a5d041620f4d3fabaa2`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 11.2 converts the Phase 11.1 `operator_evidence_backfill_required` triage result into an ordered evidence collection plan. It does not select runtime, provider, packaging, UI, or gameplay hardening unless a concrete artifact, CI failure log, or source-backed diagnostic identifies a narrow target.

## Evidence backfill order

Operator evidence should be gathered in this order:

1. `package_artifact_inventory`
2. `install_run_transcript`
3. `configuration_snapshot`
4. `persistence_smoke_artifacts`
5. `diagnostic_bundle_artifacts`
6. `player_safe_error_artifacts`
7. `release_candidate_artifacts`
8. `redaction_review`
9. `operator_signoff`
10. `live_provider_100_turn_evidence`
11. `live_provider_1000_turn_evidence`
12. `live_provider_save_load_checkpoint_evidence`
13. `progress_quality_transcript_review`
14. `long_run_continuity_review`
15. `timing_drain_resource_evidence`

## Required backfill fields

Each evidence backfill item should record:

- evidence category;
- operator command or collection steps;
- expected artifact paths;
- required metadata fields;
- redaction requirements;
- acceptance criteria;
- gap classification if missing;
- next action when evidence is missing;
- next action when evidence identifies a concrete failure.

## Gap classifications

Use one or more of these classifications:

- `operator_backfill_not_started`
- `package_artifact_backfill_gap`
- `install_run_backfill_gap`
- `configuration_backfill_gap`
- `persistence_backfill_gap`
- `diagnostic_backfill_gap`
- `player_safe_error_backfill_gap`
- `release_candidate_backfill_gap`
- `redaction_review_backfill_gap`
- `operator_signoff_backfill_gap`
- `live_100_turn_backfill_gap`
- `live_1000_turn_backfill_gap`
- `checkpoint_backfill_gap`
- `progress_quality_review_gap`
- `continuity_review_gap`
- `timing_resource_backfill_gap`
- `concrete_hardening_target_found`
- `operator_backfill_ready_for_triage`

## Classification rules

Use `operator_backfill_not_started` when no operator evidence bundle or backfill summary has been attached.

Use category-specific `*_backfill_gap` labels when that evidence category is missing, incomplete, non-reproducible, or not tied to exact artifact paths.

Use `progress_quality_review_gap` or `continuity_review_gap` when transcript review is missing or not tied to concrete transcript artifacts.

Use `concrete_hardening_target_found` only when attached evidence identifies a specific bounded target with source-backed reproduction details.

Use `operator_backfill_ready_for_triage` only when the evidence set is complete enough to choose a hardening target without speculation.

## No-evidence decision for this slice

Because this Phase 11.2 slice does not attach concrete operator evidence, the current classification is:

- classification: `operator_backfill_not_started`
- secondary classification: `operator_evidence_backfill_required`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, UI authority changes, speculative hardening, and external release-readiness claims

## Deterministic boundary

Phase 11.2 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- external release claims without evidence.

Simulation/runtime remains authoritative. Evidence backfill labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 11.2 is complete when the repository has CI-gated documentation/tests proving that operator evidence backfill has an ordered collection plan, missing evidence maps to explicit backfill gaps, and hardening remains blocked until concrete artifacts identify a narrow target.

## Recommended next slice

After Phase 11.2, continue with:

- Phase 11.3 — operator runbook for first package/install/run evidence capture.
