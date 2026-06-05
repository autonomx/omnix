# RPG Phase 11.5 Player-Safe Error and Redaction Evidence Runbook

Phase 11.5 defines the operator runbook for first player-safe error and redaction evidence capture.

Latest source-of-truth SHA before this Phase 11.5 slice:

- `146a3224c6b6d7a1c82dbb56232cf517d9f14a22`

## Scope

This slice is source/test/documentation only. It does not run a live/provider campaign, change runtime behavior, mutate gameplay state, build a package in CI, or claim external release readiness.

Phase 11.5 converts the Phase 11.2 evidence backfill plan into the third concrete operator runbook: player-facing safe error capture, internal diagnostic separation, support references, recovery instructions, redaction review, and shareable evidence bundle handling.

## Required operator runbook sections

The first player-safe error and redaction evidence capture should include:

1. `operator_context`
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
16. `redaction_review`
17. `evidence_bundle_manifest`
18. `player_safe_error_classification`

## Required artifact paths

The runbook should ask the operator to attach or record paths for:

- error scenario inventory;
- player-facing message transcript or screenshot notes;
- recovery action transcript or screenshot notes;
- support reference transcript or screenshot notes;
- internal diagnostic log files;
- diagnostic bundle archive;
- redaction review note;
- shareable evidence bundle archive;
- non-shareable private diagnostic bundle location if needed.

## Required metadata

The evidence capture should record:

- git SHA and branch;
- operator name or role;
- timestamp;
- operating system;
- shell;
- Python version;
- working directory;
- error scenario category;
- command or manual steps used to trigger the scenario;
- player-facing text observed;
- recovery action observed;
- support reference or correlation identifier observed;
- internal diagnostic artifact paths;
- whether secrets, tokens, provider keys, personal data, raw stack traces, and sensitive local paths were absent from player-facing output;
- whether secrets, tokens, provider keys, personal data, and sensitive local paths were redacted from shareable artifacts.

## Classifications

Use one or more of these classifications:

- `player_safe_error_capture_not_started`
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
- `player_safe_error_ready_for_triage`

## Classification rules

Use `player_safe_error_capture_not_started` when no player-safe error or redaction evidence bundle is attached.

Use scenario-specific `*_error_capture_gap` labels when the corresponding error category is missing, ambiguous, or not tied to exact reproduction steps.

Use `player_message_capture_gap` when the player-facing message transcript or screenshot notes are missing or unusable.

Use `recovery_action_capture_gap` when no reasonable recovery action is captured for the player.

Use `support_reference_capture_gap` when no support reference, log identifier, correlation identifier, or operator handoff path is captured.

Use `internal_diagnostic_capture_gap` when internal diagnostic logs or bundle paths are missing.

Use `player_facing_secret_leak_gap` when player-facing output exposes secrets, tokens, provider keys, personal data, raw stack traces, or sensitive local paths.

Use `shareable_artifact_redaction_gap` when shareable artifacts do not confirm redaction of secrets and sensitive local details.

Use `evidence_bundle_gap` when the evidence archive or manifest is missing or incomplete.

Use `player_safe_error_ready_for_triage` only when player-safe error and redaction evidence is complete enough to classify a concrete hardening target without speculation.

## No-evidence decision for this slice

Because this Phase 11.5 slice does not attach a concrete player-safe error or redaction evidence bundle, the current classification is:

- classification: `player_safe_error_capture_not_started`
- secondary classification: `operator_evidence_backfill_required`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Deterministic boundary

Phase 11.5 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- package building in CI;
- external release claims without evidence.

Simulation/runtime remains authoritative. Player-safe error and redaction evidence labels are evidence surfaces only and must not decide gameplay truth.

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

# Capture player-safe error scenario evidence
<error scenario command or manual steps> 2>&1 | tee operator-error-scenario-transcript.txt

# Capture internal diagnostics
<diagnostic collection command> 2>&1 | tee operator-error-diagnostics-transcript.txt

# Capture redaction review
<redaction review steps> 2>&1 | tee operator-redaction-review.txt
```

## Stop condition

Phase 11.5 is complete when the repository has CI-gated documentation/tests proving that player-safe error and redaction evidence capture has a runbook, missing evidence maps to explicit gaps, and hardening remains blocked until evidence identifies a narrow target.

## Recommended next slice

After Phase 11.5, continue with:

- Phase 11.6 — first live/provider 100-turn evidence capture runbook.
