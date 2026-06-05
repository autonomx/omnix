# RPG Phase 11.9 Hardening Target Selection

Phase 11.9 defines how the first concrete production hardening target is selected from attached evidence.

Latest source-of-truth SHA before this Phase 11.9 slice:

- `1400cf8b3a31daf2d4469afaeaf893d5a20c9cdf`

## Scope

This slice is source/test/documentation only. It does not run a live/provider campaign in CI, change runtime behavior, mutate gameplay state, build a package in CI, select speculative runtime hardening, or claim external release readiness.

Phase 11.9 converts the Phase 11.1 triage and Phase 11.2 backfill plan into a target-selection gate: attached evidence must identify a bounded failure before Phase 12 implementation begins. Without attached evidence, no runtime, provider, packaging, diagnostics, player-safe error, endurance, checkpoint/replay, UI, or gameplay hardening target is selected.

## Required evidence inputs

The first hardening target selection packet should inspect these evidence inputs when attached:

1. `package_install_run_evidence`
2. `persistence_diagnostics_evidence`
3. `player_safe_error_redaction_evidence`
4. `live_provider_100_turn_evidence`
5. `live_provider_1000_turn_evidence`
6. `checkpoint_replay_evidence`
7. `ci_failure_logs`
8. `source_backed_diagnostics`

## Required hardening target selection fields

A hardening target selection record should include concrete values for:

- evidence source path;
- failure category;
- reproduction command or steps;
- affected component;
- severity;
- player impact;
- deterministic/runtime boundary impact;
- proposed bounded fix target;
- explicit non-targets;
- acceptance criteria;
- required verification checks.

## Selection classifications

Use one or more of these classifications:

- `hardening_target_selection_not_started`
- `operator_evidence_backfill_required`
- `no_concrete_failure_evidence`
- `runtime_hardening_target_selected`
- `packaging_hardening_target_selected`
- `diagnostics_hardening_target_selected`
- `player_safe_error_hardening_target_selected`
- `endurance_hardening_target_selected`
- `checkpoint_replay_hardening_target_selected`
- `target_selection_ready_for_phase12`

## Classification rules

Use `hardening_target_selection_not_started` when no hardening target selection packet or evidence bundle is attached.

Use `operator_evidence_backfill_required` when package/install/run, persistence/diagnostics, player-safe error/redaction, endurance, checkpoint/replay, CI failure, or source-backed diagnostic evidence is still missing or insufficient.

Use `no_concrete_failure_evidence` when attached evidence exists but does not identify a reproducible bounded failure with source-backed target details.

Use `runtime_hardening_target_selected` only when evidence identifies a bounded runtime-authority failure, reproduction steps, affected runtime component, and verification checks.

Use `packaging_hardening_target_selected` only when package/install/run evidence identifies a bounded packaging, launch, configuration, or artifact-integrity failure.

Use `diagnostics_hardening_target_selected` only when persistence/diagnostics evidence identifies a bounded logging, diagnostic bundle, save/load, replay, or operator-observability failure.

Use `player_safe_error_hardening_target_selected` only when player-safe error/redaction evidence identifies a bounded unsafe message, leak, missing recovery path, or support-reference failure.

Use `endurance_hardening_target_selected` only when live/provider 100-turn or 1000-turn evidence identifies a bounded long-run, progress-quality, continuity, final-drain, background-drain, timing, or resource-limit failure.

Use `checkpoint_replay_hardening_target_selected` only when checkpoint/replay evidence identifies a bounded save/load, replay, checkpoint artifact, package/disk replay, determinism, or artifact-integrity failure.

Use `target_selection_ready_for_phase12` only when a selected target has an evidence source path, failure category, reproduction command or steps, affected component, severity, player impact, deterministic/runtime boundary impact, bounded fix target, explicit non-targets, acceptance criteria, and required verification checks.

## No-evidence decision for this slice

Because this Phase 11.9 slice does not attach a concrete operator evidence bundle, CI failure log, or source-backed diagnostic that identifies a bounded failure, the current selection state is:

- classification: `hardening_target_selection_not_started`
- secondary classification: `operator_evidence_backfill_required`
- selected target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, Phase 12 implementation, and external release-readiness claims

## Phase 12 entry gate

Phase 12 implementation must not begin unless an attached evidence bundle identifies a concrete bounded hardening target and the target-selection record includes:

- an evidence source path;
- a failure category;
- reproduction command or steps;
- an affected component;
- severity and player impact;
- deterministic/runtime boundary impact;
- a proposed bounded fix target;
- explicit non-targets;
- acceptance criteria;
- required verification checks.

If any required field is missing, the next action remains evidence backfill or target-selection clarification, not implementation.

## Deterministic boundary

Phase 11.9 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- package building in CI;
- Phase 12 implementation without target-selection evidence;
- external release claims without evidence.

Simulation/runtime remains authoritative. Hardening target labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 11.9 is complete when the repository has CI-gated documentation/tests proving that first hardening target selection requires attached evidence, missing evidence maps to `hardening_target_selection_not_started` and `operator_evidence_backfill_required`, and Phase 12 implementation remains blocked until a bounded target is selected from source-backed evidence.

## Recommended next slice

After Phase 11.9, continue with:

- Phase 12.1 — concrete hardening implementation from accepted evidence.
