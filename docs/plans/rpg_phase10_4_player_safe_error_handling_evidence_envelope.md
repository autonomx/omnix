# RPG Phase 10.4 Player-Safe Error Handling Evidence Envelope

Phase 10.4 records the evidence envelope for player-safe error handling.

Latest source-of-truth SHA before this Phase 10.4 slice:

- `783571e95bc16d2a5f9bf87b947bc6bdb13520fe`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 10.4 defines the evidence required to prove that production-facing failures show safe player messages while preserving internal diagnostic detail for operators.

## Required player-safe error evidence sections

A player-safe error evidence summary should include:

1. `startup_error_evidence`
2. `configuration_error_evidence`
3. `provider_error_evidence`
4. `save_load_error_evidence`
5. `persistence_error_evidence`
6. `network_error_evidence`
7. `resource_error_evidence`
8. `unknown_error_evidence`
9. `safe_message_evidence`
10. `recovery_action_evidence`
11. `diagnostic_reference_evidence`
12. `internal_detail_separation_evidence`
13. `support_bundle_evidence`
14. `player_safe_error_classification`

## Required fields

The player-safe error evidence summary should record concrete values for:

- git SHA and branch;
- operating system and launch context;
- triggered error category;
- player-facing message text;
- recovery action text;
- support or diagnostic reference shown to the player;
- internal diagnostic location and artifact path;
- log correlation identifier if present;
- confirmation that provider keys, tokens, secrets, local absolute paths, and raw stack traces are not exposed to the player;
- confirmation that internal diagnostics remain available to operators;
- selected player-safe error classification.

## Classifications

Use one or more of these classifications:

- `player_safe_error_evidence_gap`
- `startup_error_message_gap`
- `configuration_error_message_gap`
- `provider_error_message_gap`
- `save_load_error_message_gap`
- `persistence_error_message_gap`
- `network_error_message_gap`
- `resource_error_message_gap`
- `unknown_error_message_gap`
- `recovery_action_gap`
- `diagnostic_reference_gap`
- `internal_detail_leak_gap`
- `support_bundle_gap`
- `player_safe_error_ready`

## Classification rules

Use `player_safe_error_evidence_gap` when no concrete player-safe error handling evidence is attached.

Use a category-specific `*_error_message_gap` when the corresponding failure category lacks a safe player-facing message.

Use `recovery_action_gap` when the player-facing message does not include a reasonable next action or recovery instruction.

Use `diagnostic_reference_gap` when the message gives no support reference, log identifier, artifact pointer, or operator diagnostic handoff path.

Use `internal_detail_leak_gap` when player-facing output exposes provider keys, tokens, secrets, raw stack traces, unredacted local absolute paths, or internal debug details beyond the intended diagnostic scope.

Use `support_bundle_gap` when support bundle or diagnostic artifact instructions are missing or unusable.

Use `player_safe_error_ready` only when concrete evidence covers startup, configuration, provider, save/load, persistence, network, resource, and unknown failures with safe messages, recovery actions, diagnostic references, internal-detail separation, and usable support bundle guidance without blocking gaps.

## No-evidence decision for this slice

Because this Phase 10.4 slice does not attach concrete startup, configuration, provider, save/load, persistence, network, resource, or unknown error evidence, the current classification is:

- classification: `player_safe_error_evidence_gap`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims

## Deterministic boundary

Phase 10.4 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- external release claims without evidence.

Simulation/runtime remains authoritative. Player-safe error labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 10.4 is complete when the repository has CI-gated documentation/tests proving that player-safe error readiness requires concrete evidence, absent evidence maps to `player_safe_error_evidence_gap`, and this slice does not claim release readiness.

## Recommended next slice

After Phase 10.4, continue with:

- Phase 10.5 — release candidate packaging contract.
