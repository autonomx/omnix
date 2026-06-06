# RPG Phase 12.4 Player-Safe Error Redaction Evidence Decision

Phase 12.4 is the player-safe error/redaction evidence capture or hardening slice.

Latest source-of-truth SHA before this Phase 12.4 slice:

- `40306cda83207fd003b2a82b7f2e57efcf5b2bb3`

## Scope

This slice is source/test/documentation only because no accepted player-safe error/redaction evidence bundle is attached.

Phase 12.4 must not implement player-safe error handling, redaction, diagnostic separation, support-reference, recovery-action, runtime, provider, UI, or gameplay hardening unless accepted player-safe error/redaction evidence identifies a concrete bounded target.

This slice records the player-safe error/redaction evidence decision state, accepted evidence requirements, implementation-allowed conditions, implementation-blocked conditions, and the no-evidence baseline.

## Accepted player-safe error/redaction evidence requirements

Before Phase 12.4 may implement a player-safe error or redaction hardening fix, the evidence packet must include:

1. `accepted_player_safe_error_evidence_source_path`
2. `source_checkout`
3. `error_scenario_inventory`
4. `startup_error_capture`
5. `configuration_error_capture`
6. `provider_error_capture`
7. `save_load_error_capture`
8. `persistence_error_capture`
9. `network_error_capture`
10. `resource_error_capture`
11. `unknown_error_capture`
12. `player_message_capture`
13. `recovery_action_capture`
14. `support_reference_capture`
15. `internal_diagnostic_capture`
16. `evidence_bundle_manifest`
17. `failure_category`
18. `reproduction_command_or_steps`
19. `affected_component`
20. `player_or_operator_impact`
21. `deterministic_runtime_boundary_impact`
22. `proposed_bounded_fix_target`
23. `explicit_non_targets`
24. `acceptance_criteria`
25. `required_verification_checks`
26. `redaction_review`

## Decision classifications

Use one or more of these classifications:

- `phase12_4_player_safe_error_evidence_not_started`
- `operator_evidence_backfill_required`
- `player_safe_error_evidence_incomplete`
- `error_scenario_inventory_gap`
- `startup_error_capture_gap`
- `configuration_error_capture_gap`
- `provider_error_capture_gap`
- `save_load_error_capture_gap`
- `persistence_error_capture_gap`
- `network_error_capture_gap`
- `resource_error_capture_gap`
- `unknown_error_capture_gap`
- `player_message_capture_gap`
- `recovery_action_capture_gap`
- `support_reference_capture_gap`
- `internal_diagnostic_capture_gap`
- `player_facing_secret_leak_gap`
- `shareable_artifact_redaction_gap`
- `evidence_bundle_gap`
- `player_safe_error_target_ready`
- `phase12_4_implementation_allowed`
- `phase12_4_implementation_blocked`

## Decision rules

Use `phase12_4_player_safe_error_evidence_not_started` when no accepted player-safe error/redaction evidence packet is attached.

Use `operator_evidence_backfill_required` when the next action is still collecting error scenario, player message, recovery action, support reference, internal diagnostic, evidence bundle, or redaction evidence.

Use `player_safe_error_evidence_incomplete` when evidence is attached but missing any accepted player-safe error/redaction evidence requirement.

Use scenario-specific `*_error_capture_gap` classifications when startup, configuration, provider, save/load, persistence, network, resource, or unknown error capture is missing, ambiguous, not reproducible, or not tied to the exact source checkout.

Use `player_message_capture_gap` when the player-facing message transcript or screenshot notes are missing, unusable, or do not identify the observed player-visible message.

Use `recovery_action_capture_gap` when the evidence does not include a reasonable player recovery action or operator handoff path.

Use `support_reference_capture_gap` when no support reference, log identifier, correlation identifier, or diagnostic handoff path is captured.

Use `internal_diagnostic_capture_gap` when internal diagnostic logs, private diagnostic bundle paths, or operator-only diagnostic references are missing.

Use `player_facing_secret_leak_gap` when player-facing output exposes secrets, tokens, provider keys, personal data, raw stack traces, sensitive local paths, or private diagnostic details.

Use `shareable_artifact_redaction_gap` when shareable artifacts do not confirm redaction of secrets, tokens, provider keys, personal data, raw stack traces, sensitive local paths, or private diagnostic details.

Use `evidence_bundle_gap` when the evidence archive or manifest is missing, incomplete, not redacted, or not tied to the exact source checkout.

Use `player_safe_error_target_ready` only when player-safe error/redaction evidence identifies a bounded player-facing message, recovery action, support reference, internal diagnostic separation, redaction, evidence bundle, or private-detail exposure failure and supplies all accepted evidence requirements.

Use `phase12_4_implementation_allowed` only when `player_safe_error_target_ready` is present and all accepted player-safe error/redaction evidence requirements are complete.

Use `phase12_4_implementation_blocked` when evidence is missing, incomplete, not redacted, not reproducible, not source-backed, or does not identify a bounded player-safe error/redaction fix target.

## No-evidence decision for this slice

Because this Phase 12.4 slice does not attach an accepted player-safe error/redaction evidence packet, the current decision state is:

- classification: `phase12_4_player_safe_error_evidence_not_started`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `phase12_4_implementation_blocked`
- selected player-safe error/redaction fix target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: player-safe error implementation, redaction implementation, diagnostic separation changes, support-reference changes, recovery-action changes, runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Implementation allowed checklist

A Phase 12.4 player-safe error/redaction hardening PR may be opened only when all checklist items are true:

- accepted player-safe error evidence source path is present;
- source checkout is present;
- error scenario inventory is present;
- startup error capture is present;
- configuration error capture is present;
- provider error capture is present;
- save/load error capture is present;
- persistence error capture is present;
- network error capture is present;
- resource error capture is present;
- unknown error capture is present;
- player message capture is present;
- recovery action capture is present;
- support reference capture is present;
- internal diagnostic capture is present;
- evidence bundle manifest is present;
- failure category is present;
- reproduction command or steps are present;
- affected component is present;
- player or operator impact is present;
- deterministic/runtime boundary impact is present;
- proposed bounded fix target is present;
- explicit non-targets are present;
- acceptance criteria are present;
- required verification checks are present;
- redaction review is present;
- `player_safe_error_target_ready` is present;
- `phase12_4_implementation_allowed` is present.

If any checklist item is missing, Phase 12.4 remains blocked and the next action is player-safe error/redaction evidence backfill or target-selection clarification, not implementation.

## Deterministic boundary

Phase 12.4 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without accepted player-safe error/redaction evidence;
- package building in CI;
- player-safe error/redaction implementation without accepted evidence;
- external release claims without evidence.

Simulation/runtime remains authoritative. Phase 12.4 player-safe error/redaction decision labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 12.4 is complete when the repository has CI-gated documentation/tests proving that player-safe error/redaction implementation remains blocked without accepted evidence, accepted player-safe error/redaction evidence requirements are explicit, and any future player-safe error/redaction hardening implementation must be tied to a bounded source-backed target.

## Recommended next slice

After Phase 12.4, continue with:

- Phase 12.5 — live/provider endurance evidence capture or hardening.
