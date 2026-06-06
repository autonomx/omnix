# RPG Phase 12.2 Package Install Run Evidence Decision

Phase 12.2 is the package/install/run evidence capture or hardening slice.

Latest source-of-truth SHA before this Phase 12.2 slice:

- `c3a18b28d612eeaf5d0b8229f7cd693ebe22cc1e`

## Scope

This slice is source/test/documentation only because no accepted package/install/run evidence bundle is attached.

Phase 12.2 must not implement package, installer, launcher, configuration, runtime, provider, UI, or gameplay hardening unless accepted package/install/run evidence identifies a concrete bounded target.

This slice records the package/install/run evidence decision state, accepted package evidence requirements, implementation-allowed conditions, implementation-blocked conditions, and the no-evidence baseline.

## Accepted package/install/run evidence requirements

Before Phase 12.2 may implement a package/install/run hardening fix, the evidence packet must include:

1. `accepted_package_evidence_source_path`
2. `source_checkout`
3. `package_artifact_inventory`
4. `package_checksum_or_checkout_reference`
5. `dependency_install_transcript`
6. `configuration_snapshot`
7. `environment_variable_snapshot`
8. `resource_path_snapshot`
9. `data_path_snapshot`
10. `launch_command_transcript`
11. `startup_health_check`
12. `runtime_smoke_transcript`
13. `shutdown_transcript`
14. `diagnostic_collection_reference`
15. `failure_category`
16. `reproduction_command_or_steps`
17. `affected_component`
18. `operator_impact`
19. `deterministic_runtime_boundary_impact`
20. `proposed_bounded_fix_target`
21. `explicit_non_targets`
22. `acceptance_criteria`
23. `required_verification_checks`
24. `redaction_review`

## Decision classifications

Use one or more of these classifications:

- `phase12_2_package_evidence_not_started`
- `operator_evidence_backfill_required`
- `package_evidence_incomplete`
- `package_artifact_gap`
- `install_transcript_gap`
- `configuration_snapshot_gap`
- `environment_snapshot_gap`
- `resource_path_snapshot_gap`
- `data_path_snapshot_gap`
- `launch_transcript_gap`
- `startup_health_gap`
- `runtime_smoke_gap`
- `shutdown_transcript_gap`
- `diagnostic_collection_gap`
- `redaction_review_gap`
- `package_install_run_target_ready`
- `phase12_2_implementation_allowed`
- `phase12_2_implementation_blocked`

## Decision rules

Use `phase12_2_package_evidence_not_started` when no accepted package/install/run evidence packet is attached.

Use `operator_evidence_backfill_required` when the next action is still collecting package artifact, install, launch, configuration, smoke, shutdown, diagnostic, or redaction evidence.

Use `package_evidence_incomplete` when evidence is attached but missing any accepted package/install/run evidence requirement.

Use category-specific `*_gap` classifications when the matching artifact, transcript, snapshot, diagnostic reference, or redaction review is missing, non-reproducible, or not tied to the exact source checkout.

Use `package_install_run_target_ready` only when package/install/run evidence identifies a bounded packaging, install, launch, configuration, startup health, runtime smoke, shutdown, diagnostic, checksum, or artifact-integrity failure and supplies all accepted evidence requirements.

Use `phase12_2_implementation_allowed` only when `package_install_run_target_ready` is present and all accepted package/install/run evidence requirements are complete.

Use `phase12_2_implementation_blocked` when evidence is missing, incomplete, not redacted, not reproducible, not source-backed, or does not identify a bounded package/install/run fix target.

## No-evidence decision for this slice

Because this Phase 12.2 slice does not attach an accepted package/install/run evidence packet, the current decision state is:

- classification: `phase12_2_package_evidence_not_started`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `phase12_2_implementation_blocked`
- selected package/install/run fix target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: package implementation, installer changes, launch behavior changes, configuration behavior changes, runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Implementation allowed checklist

A Phase 12.2 package/install/run hardening PR may be opened only when all checklist items are true:

- accepted package evidence source path is present;
- source checkout is present;
- package artifact inventory is present;
- package checksum or checkout reference is present;
- dependency install transcript is present;
- configuration snapshot is present;
- environment variable snapshot is present and redacted;
- resource path snapshot is present;
- data path snapshot is present;
- launch command transcript is present;
- startup health check is present;
- runtime smoke transcript is present;
- shutdown transcript is present;
- diagnostic collection reference is present;
- failure category is present;
- reproduction command or steps are present;
- affected component is present;
- operator impact is present;
- deterministic/runtime boundary impact is present;
- proposed bounded fix target is present;
- explicit non-targets are present;
- acceptance criteria are present;
- required verification checks are present;
- redaction review is present;
- `package_install_run_target_ready` is present;
- `phase12_2_implementation_allowed` is present.

If any checklist item is missing, Phase 12.2 remains blocked and the next action is package/install/run evidence backfill or target-selection clarification, not implementation.

## Deterministic boundary

Phase 12.2 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without accepted package/install/run evidence;
- package building in CI;
- package/install/run implementation without accepted evidence;
- external release claims without evidence.

Simulation/runtime remains authoritative. Phase 12.2 package/install/run decision labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 12.2 is complete when the repository has CI-gated documentation/tests proving that package/install/run implementation remains blocked without accepted package evidence, accepted package evidence requirements are explicit, and any future package/install/run hardening implementation must be tied to a bounded source-backed target.

## Recommended next slice

After Phase 12.2, continue with:

- Phase 12.3 — persistence/diagnostics evidence capture or hardening.
