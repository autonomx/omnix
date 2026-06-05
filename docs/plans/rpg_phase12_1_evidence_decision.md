# RPG Phase 12.1 Evidence Decision

Phase 12.1 is the first concrete evidence-backed production hardening slice.

Latest source-of-truth SHA before this Phase 12.1 slice:

- `ac0290d848e8a73325b027b1258a681d394e3278`

## Scope

This slice is source/test/documentation only because no accepted operator evidence bundle, CI failure log, or source-backed diagnostic is attached.

Phase 12.1 must not implement runtime, provider, packaging, diagnostics, player-safe error, endurance, checkpoint/replay, UI, or gameplay hardening unless accepted evidence identifies a concrete bounded target.

This slice records the Phase 12.1 decision state, accepted evidence requirements, implementation-allowed conditions, implementation-blocked conditions, and the no-evidence baseline.

## Accepted evidence requirements

Before Phase 12.1 may implement a hardening fix, the evidence packet must include:

1. `accepted_evidence_source_path`
2. `evidence_category`
3. `failure_category`
4. `reproduction_command_or_steps`
5. `affected_component`
6. `severity`
7. `player_impact`
8. `deterministic_runtime_boundary_impact`
9. `proposed_bounded_fix_target`
10. `explicit_non_targets`
11. `acceptance_criteria`
12. `required_verification_checks`
13. `redaction_review`
14. `operator_or_source_diagnostic_reference`

## Evidence categories

Use one or more of these evidence categories:

- `package_install_run_evidence`
- `persistence_diagnostics_evidence`
- `player_safe_error_redaction_evidence`
- `live_provider_100_turn_evidence`
- `live_provider_1000_turn_evidence`
- `checkpoint_replay_evidence`
- `ci_failure_logs`
- `source_backed_diagnostics`

## Decision classifications

Use one or more of these classifications:

- `phase12_1_no_accepted_evidence`
- `operator_evidence_backfill_required`
- `accepted_evidence_incomplete`
- `accepted_evidence_ready_for_runtime_fix`
- `accepted_evidence_ready_for_packaging_fix`
- `accepted_evidence_ready_for_diagnostics_fix`
- `accepted_evidence_ready_for_player_safe_error_fix`
- `accepted_evidence_ready_for_endurance_fix`
- `accepted_evidence_ready_for_checkpoint_replay_fix`
- `phase12_1_implementation_allowed`
- `phase12_1_implementation_blocked`

## Decision rules

Use `phase12_1_no_accepted_evidence` when no accepted evidence packet is attached.

Use `operator_evidence_backfill_required` when the next action is still collecting package/install/run, persistence/diagnostics, player-safe error/redaction, endurance, checkpoint/replay, CI failure, or source-backed diagnostic evidence.

Use `accepted_evidence_incomplete` when evidence is attached but is missing a source path, failure category, reproduction command or steps, affected component, severity, player impact, deterministic/runtime boundary impact, proposed bounded fix target, explicit non-targets, acceptance criteria, required verification checks, redaction review, or operator/source diagnostic reference.

Use `accepted_evidence_ready_for_runtime_fix` only when evidence identifies a bounded runtime-authority defect and supplies all accepted evidence requirements.

Use `accepted_evidence_ready_for_packaging_fix` only when package/install/run evidence identifies a bounded packaging, launch, configuration, checksum, artifact, or install failure and supplies all accepted evidence requirements.

Use `accepted_evidence_ready_for_diagnostics_fix` only when persistence/diagnostics evidence identifies a bounded logging, diagnostic bundle, persistence, save/load, replay, or operator-observability failure and supplies all accepted evidence requirements.

Use `accepted_evidence_ready_for_player_safe_error_fix` only when player-safe error/redaction evidence identifies a bounded unsafe message, stack trace leak, secret leak, sensitive path leak, missing support reference, or recovery-message failure and supplies all accepted evidence requirements.

Use `accepted_evidence_ready_for_endurance_fix` only when live/provider 100-turn or 1000-turn evidence identifies a bounded long-run, progress-quality, continuity, final-drain, background-drain, timing, resource-limit, or artifact-capture failure and supplies all accepted evidence requirements.

Use `accepted_evidence_ready_for_checkpoint_replay_fix` only when checkpoint/replay evidence identifies a bounded checkpoint, save/load, replay, package/disk replay, determinism, or artifact-integrity failure and supplies all accepted evidence requirements.

Use `phase12_1_implementation_allowed` only when one ready-for-fix classification is present and all accepted evidence requirements are complete.

Use `phase12_1_implementation_blocked` when evidence is missing, incomplete, not source-backed, not reproducible, not redacted, or does not identify a bounded fix target.

## No-evidence decision for this slice

Because this Phase 12.1 slice does not attach an accepted evidence packet, the current decision state is:

- classification: `phase12_1_no_accepted_evidence`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `phase12_1_implementation_blocked`
- selected fix target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Implementation allowed checklist

A Phase 12.1 implementation PR may be opened only when all checklist items are true:

- accepted evidence source path is present;
- evidence category is present;
- failure category is present;
- reproduction command or steps are present;
- affected component is present;
- severity is present;
- player impact is present;
- deterministic/runtime boundary impact is present;
- proposed bounded fix target is present;
- explicit non-targets are present;
- acceptance criteria are present;
- required verification checks are present;
- redaction review is present;
- operator or source diagnostic reference is present;
- at least one ready-for-fix classification is present;
- `phase12_1_implementation_allowed` is present.

If any checklist item is missing, Phase 12.1 remains blocked and the next action is evidence backfill or target-selection clarification, not implementation.

## Deterministic boundary

Phase 12.1 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without accepted evidence;
- package building in CI;
- runtime implementation without accepted evidence;
- external release claims without evidence.

Simulation/runtime remains authoritative. Phase 12.1 decision labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 12.1 is complete when the repository has CI-gated documentation/tests proving that implementation remains blocked without accepted evidence, accepted evidence requirements are explicit, and any future concrete hardening implementation must be tied to a bounded source-backed target.

## Recommended next slice

After Phase 12.1, continue with:

- Phase 12.2 — package/install/run evidence capture or hardening.
