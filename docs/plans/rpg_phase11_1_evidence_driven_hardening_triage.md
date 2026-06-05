# RPG Phase 11.1 Evidence-Driven Production Hardening Triage

Phase 11.1 starts evidence-driven production hardening.

Latest source-of-truth SHA before this Phase 11.1 slice:

- `83db1f8e5c6e9d11f926ae93e3c2a8be30f7a81c`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 11.1 reviews the Phase 10 evidence contracts and classifies which concrete operator evidence is still missing before any runtime, provider, packaging, UI, or gameplay hardening is selected.

## Evidence sources to inspect

A production hardening triage summary should inspect:

1. `phase10_1_production_readiness_baseline`
2. `phase10_2_install_run_configuration_evidence`
3. `phase10_3_persistence_diagnostics_evidence`
4. `phase10_4_player_safe_error_evidence`
5. `phase10_5_release_candidate_packaging_contract`
6. `phase10_6_operator_release_evidence_intake`
7. `phase10_7_closeout_decision_gate`
8. `ci_failure_logs`
9. `operator_artifacts`
10. `source_backed_diagnostics`

## Required triage fields

The hardening triage summary should record concrete values for:

- git SHA and branch;
- evidence source paths inspected;
- missing operator evidence categories;
- attached operator artifact paths if present;
- CI failure log references if present;
- source-backed diagnostics if present;
- proposed hardening target;
- reason the target is evidence-backed;
- explicit non-targets;
- triage classification;
- next recommended slice.

## Missing evidence categories

The current no-operator-evidence baseline should record these missing categories:

- package artifact and checksum evidence;
- install/run transcript evidence;
- configuration evidence;
- persistence smoke evidence;
- replay/package artifact evidence;
- diagnostic bundle evidence;
- player-safe error evidence;
- release candidate packaging evidence;
- operator release intake summary;
- redaction review;
- operator signoff;
- live/provider 100-turn evidence;
- live/provider 1000-turn evidence;
- live/provider save/load checkpoint evidence;
- progress-quality transcript review;
- long-run continuity review;
- timing, drain, and resource-limit evidence.

## Triage classifications

Use one of these classifications:

- `hardening_evidence_gap`
- `operator_evidence_backfill_required`
- `ci_failure_hardening_target`
- `operator_artifact_hardening_target`
- `source_diagnostic_hardening_target`
- `runtime_hardening_ready`
- `packaging_hardening_ready`
- `diagnostics_hardening_ready`
- `player_safe_error_hardening_ready`
- `release_candidate_review_ready`

## Classification rules

Use `hardening_evidence_gap` when no concrete operator artifacts, CI failure logs, or source-backed diagnostics identify a narrow hardening target.

Use `operator_evidence_backfill_required` when the correct next step is gathering missing package, install/run, persistence, diagnostics, player-safe error, endurance, or release intake evidence.

Use `ci_failure_hardening_target` only when a current CI failure log identifies a specific source-backed target.

Use `operator_artifact_hardening_target` only when an attached operator artifact identifies a specific source-backed target.

Use `source_diagnostic_hardening_target` only when repo-side diagnostics identify a specific hardening target without requiring speculation.

Use `runtime_hardening_ready`, `packaging_hardening_ready`, `diagnostics_hardening_ready`, or `player_safe_error_hardening_ready` only when a concrete evidence source identifies that category as the next bounded target.

Use `release_candidate_review_ready` only when Phase 10 evidence is attached and no blocking production-readiness gaps remain.

## No-evidence decision for this slice

Because this Phase 11.1 slice does not attach concrete operator artifacts, CI failure logs, or source-backed diagnostics that identify a narrow production hardening target, the current triage classification is:

- classification: `hardening_evidence_gap`
- secondary classification: `operator_evidence_backfill_required`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, UI authority changes, speculative hardening, and external release-readiness claims

## Deterministic boundary

Phase 11.1 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- external release claims without evidence.

Simulation/runtime remains authoritative. Hardening triage labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 11.1 is complete when the repository has CI-gated documentation/tests proving that hardening target selection requires concrete operator artifacts, CI failure logs, or source-backed diagnostics; absent evidence maps to `hardening_evidence_gap` and `operator_evidence_backfill_required`; and this slice does not change runtime behavior.

## Recommended next slice

After Phase 11.1, continue with:

- Phase 11.2 — operator evidence backfill or narrow hardening from concrete failures.
