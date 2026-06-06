# RPG Phase 13.1 Operator Evidence Backfill Reopen

Phase 13.1 reopens operator evidence backfill unless accepted evidence is attached.

Latest source-of-truth SHA before this Phase 13.1 slice:

- `fa0cee3ae42ab26be49eb00d3d17d3c7d13ed604`

## Scope

This slice is source/test/documentation only because no accepted evidence bundle is attached.

Phase 13.1 must not implement runtime, provider, package, diagnostics, player-safe error, endurance, checkpoint/replay, UI, or gameplay hardening unless accepted evidence identifies exactly one concrete bounded target.

This slice records that Phase 12 is complete as an evidence intake framework, Phase 13 implementation remains blocked, and operator evidence backfill is reopened.

## Evidence categories to backfill

Backfill remains required for:

1. `package_install_run_evidence`
2. `persistence_diagnostics_evidence`
3. `player_safe_error_redaction_evidence`
4. `live_provider_100_turn_evidence`
5. `live_provider_1000_turn_evidence`
6. `checkpoint_replay_evidence`
7. `ci_failure_logs`
8. `source_backed_diagnostics`

## Accepted evidence requirements

A Phase 13 implementation target may be selected only when the evidence packet includes:

1. `accepted_evidence_source_path`
2. `accepted_evidence_category`
3. `failure_category`
4. `reproduction_command_or_steps`
5. `affected_component`
6. `severity`
7. `player_or_operator_impact`
8. `deterministic_runtime_boundary_impact`
9. `proposed_bounded_fix_target`
10. `explicit_non_targets`
11. `acceptance_criteria`
12. `required_verification_checks`
13. `redaction_review`
14. `phase13_recommended_implementation_slice`

## Decision classifications

Use one or more of these classifications:

- `phase13_1_no_accepted_evidence`
- `operator_evidence_backfill_reopened`
- `accepted_evidence_incomplete`
- `accepted_evidence_selects_single_target`
- `phase13_implementation_allowed`
- `phase13_implementation_blocked`

## Decision rules

Use `phase13_1_no_accepted_evidence` when no accepted evidence packet is attached.

Use `operator_evidence_backfill_reopened` when evidence collection is the next action.

Use `accepted_evidence_incomplete` when evidence is attached but missing any accepted evidence requirement.

Use `accepted_evidence_selects_single_target` only when one bounded implementation target is selected from a source-backed, reproducible, redacted evidence packet.

Use `phase13_implementation_allowed` only when `accepted_evidence_selects_single_target` is present and all accepted evidence requirements are complete.

Use `phase13_implementation_blocked` when evidence is missing, incomplete, not redacted, not reproducible, not source-backed, or selects zero or multiple targets.

## No-evidence decision for this slice

Because this Phase 13.1 slice does not attach an accepted evidence packet, the current decision state is:

- classification: `phase13_1_no_accepted_evidence`
- secondary classification: `operator_evidence_backfill_reopened`
- implementation state: `phase13_implementation_blocked`
- selected implementation target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime implementation, provider implementation, package implementation, diagnostics implementation, player-safe error implementation, endurance implementation, checkpoint/replay implementation, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Operator testing packet

The next direct-testing packet should capture:

- package checkout, install, launch, startup, smoke, and shutdown transcripts;
- configuration, environment, resource path, and data path snapshots;
- save/load roundtrip and checkpoint/replay artifacts;
- diagnostic logs and diagnostic bundle manifests;
- player-safe error and redaction review evidence;
- 100-turn and 1000-turn live/provider endurance artifacts;
- failure classifications and hardening handoff notes;
- redacted shareable evidence bundle paths.

## Deterministic boundary

Phase 13.1 must not add provider calls, LLM calls, network calls, live 100-turn or 1000-turn CI execution, gameplay mutation, UI authority changes, speculative hardening, package building in CI, implementation without accepted evidence, or external release claims without evidence.

Simulation/runtime remains authoritative. Phase 13.1 decision labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 13.1 is complete when the repository has CI-gated documentation/tests proving that operator evidence backfill is reopened, Phase 13 implementation remains blocked without accepted evidence, and any future implementation must be tied to one bounded source-backed target.

## Recommended next slice

After Phase 13.1, continue with:

- Phase 13.2 — first accepted hardening target implementation after evidence attachment.

If no accepted evidence is attached, continue operator evidence backfill instead of implementing speculative hardening.
