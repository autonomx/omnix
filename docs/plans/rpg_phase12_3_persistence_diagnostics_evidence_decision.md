# RPG Phase 12.3 Persistence Diagnostics Evidence Decision

Phase 12.3 is the persistence/diagnostics evidence capture or hardening slice.

Latest source-of-truth SHA before this Phase 12.3 slice:

- `468ac1b76a0c266c63a3af45dcc9e7e644ebdd32`

## Scope

This slice is source/test/documentation only because no accepted persistence/diagnostics evidence bundle is attached.

Phase 12.3 must not implement persistence, diagnostics, save/load, replay, artifact, runtime, provider, UI, or gameplay hardening unless accepted persistence/diagnostics evidence identifies a concrete bounded target.

This slice records the persistence/diagnostics evidence decision state, accepted persistence/diagnostics evidence requirements, implementation-allowed conditions, implementation-blocked conditions, and the no-evidence baseline.

## Accepted persistence/diagnostics evidence requirements

Before Phase 12.3 may implement a persistence or diagnostics hardening fix, the evidence packet must include:

1. `accepted_persistence_diagnostics_evidence_source_path`
2. `source_checkout`
3. `save_path_snapshot`
4. `session_path_snapshot`
5. `data_path_snapshot`
6. `report_path_snapshot`
7. `save_load_roundtrip_steps`
8. `save_load_roundtrip_result`
9. `saved_state_artifact_reference`
10. `replay_artifact_capture`
11. `package_disk_artifact_capture`
12. `diagnostic_log_capture`
13. `diagnostic_bundle_manifest`
14. `failure_reproduction_steps`
15. `failure_category`
16. `affected_component`
17. `player_or_operator_impact`
18. `deterministic_runtime_boundary_impact`
19. `proposed_bounded_fix_target`
20. `explicit_non_targets`
21. `acceptance_criteria`
22. `required_verification_checks`
23. `redaction_review`

## Decision classifications

Use one or more of these classifications:

- `phase12_3_persistence_diagnostics_evidence_not_started`
- `operator_evidence_backfill_required`
- `persistence_diagnostics_evidence_incomplete`
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
- `persistence_diagnostics_target_ready`
- `phase12_3_implementation_allowed`
- `phase12_3_implementation_blocked`

## Decision rules

Use `phase12_3_persistence_diagnostics_evidence_not_started` when no accepted persistence/diagnostics evidence packet is attached.

Use `operator_evidence_backfill_required` when the next action is still collecting save path, session path, data path, report path, save/load roundtrip, replay artifact, package/disk artifact, diagnostic log, diagnostic bundle, failure reproduction, or redaction evidence.

Use `persistence_diagnostics_evidence_incomplete` when evidence is attached but missing any accepted persistence/diagnostics evidence requirement.

Use path-specific `*_path_capture_gap` classifications when save, session, data, or report path evidence is missing, ambiguous, not reproducible, or not tied to the exact source checkout.

Use artifact-specific `*_artifact_gap` or `*_artifact_capture_gap` classifications when saved state, replay, or package/disk artifacts are missing, malformed, not referenced, or not tied to the exact source checkout.

Use `save_load_roundtrip_capture_gap` when the roundtrip transcript, command, manual steps, exit status, observed result, or artifact reference is missing or not reproducible.

Use `diagnostic_log_capture_gap` or `diagnostic_bundle_capture_gap` when diagnostic logs, diagnostic bundle archives, or bundle manifests are missing, incomplete, unusable, or not reproducible.

Use `failure_reproduction_gap` when reproduction steps are absent, ambiguous, or not tied to source-backed artifacts.

Use `redaction_review_gap` when the evidence bundle does not confirm secrets, provider keys, personal data, and sensitive local paths were redacted.

Use `persistence_diagnostics_target_ready` only when persistence/diagnostics evidence identifies a bounded save path, session path, data path, report path, save/load, replay, package/disk artifact, diagnostic log, diagnostic bundle, reproduction, redaction, or artifact-integrity failure and supplies all accepted evidence requirements.

Use `phase12_3_implementation_allowed` only when `persistence_diagnostics_target_ready` is present and all accepted persistence/diagnostics evidence requirements are complete.

Use `phase12_3_implementation_blocked` when evidence is missing, incomplete, not redacted, not reproducible, not source-backed, or does not identify a bounded persistence/diagnostics fix target.

## No-evidence decision for this slice

Because this Phase 12.3 slice does not attach an accepted persistence/diagnostics evidence packet, the current decision state is:

- classification: `phase12_3_persistence_diagnostics_evidence_not_started`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `phase12_3_implementation_blocked`
- selected persistence/diagnostics fix target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: persistence implementation, diagnostics implementation, save/load behavior changes, replay behavior changes, artifact behavior changes, runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Implementation allowed checklist

A Phase 12.3 persistence/diagnostics hardening PR may be opened only when all checklist items are true:

- accepted persistence/diagnostics evidence source path is present;
- source checkout is present;
- save path snapshot is present;
- session path snapshot is present;
- data path snapshot is present;
- report path snapshot is present;
- save/load roundtrip steps are present;
- save/load roundtrip result is present;
- saved state artifact reference is present;
- replay artifact capture is present;
- package/disk artifact capture is present;
- diagnostic log capture is present;
- diagnostic bundle manifest is present;
- failure reproduction steps are present;
- failure category is present;
- affected component is present;
- player or operator impact is present;
- deterministic/runtime boundary impact is present;
- proposed bounded fix target is present;
- explicit non-targets are present;
- acceptance criteria are present;
- required verification checks are present;
- redaction review is present;
- `persistence_diagnostics_target_ready` is present;
- `phase12_3_implementation_allowed` is present.

If any checklist item is missing, Phase 12.3 remains blocked and the next action is persistence/diagnostics evidence backfill or target-selection clarification, not implementation.

## Deterministic boundary

Phase 12.3 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without accepted persistence/diagnostics evidence;
- package building in CI;
- persistence/diagnostics implementation without accepted evidence;
- external release claims without evidence.

Simulation/runtime remains authoritative. Phase 12.3 persistence/diagnostics decision labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 12.3 is complete when the repository has CI-gated documentation/tests proving that persistence/diagnostics implementation remains blocked without accepted persistence/diagnostics evidence, accepted persistence/diagnostics evidence requirements are explicit, and any future persistence/diagnostics hardening implementation must be tied to a bounded source-backed target.

## Recommended next slice

After Phase 12.3, continue with:

- Phase 12.4 — player-safe error/redaction evidence capture or hardening.
