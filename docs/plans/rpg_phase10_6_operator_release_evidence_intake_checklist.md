# RPG Phase 10.6 Operator Release Evidence Intake Checklist

Phase 10.6 records the operator-facing intake checklist for release evidence.

Latest source-of-truth SHA before this Phase 10.6 slice:

- `fd246f2da905beb5b471f8888383655a06497ac8`

## Scope

This slice is source/test/documentation only. It does not build a release package, run a live/provider campaign, change runtime behavior, or claim external release readiness.

Phase 10.6 defines how operators should attach, summarize, classify, and hand off release evidence before a release candidate can be considered reviewable.

## Required intake sections

An operator release evidence intake summary should include:

1. `release_context`
2. `source_revision`
3. `package_artifacts`
4. `install_run_evidence`
5. `configuration_evidence`
6. `persistence_evidence`
7. `diagnostic_evidence`
8. `player_safe_error_evidence`
9. `endurance_evidence`
10. `platform_environment`
11. `known_blockers`
12. `redaction_review`
13. `operator_signoff`
14. `release_intake_classification`

## Required fields

The release evidence intake summary should record concrete values for:

- git SHA and branch;
- package artifact paths and checksums;
- install and run transcript paths;
- configuration files, templates, and required environment variables;
- persistence smoke, save/load, and replay artifact paths;
- diagnostic logs and bundle paths;
- player-safe error evidence paths;
- endurance summary paths;
- platform, operating system, shell, and hardware notes;
- known blockers and release exclusions;
- redaction review status;
- operator name or role and signoff timestamp;
- selected release intake classification.

## Classifications

Use one or more of these classifications:

- `release_intake_evidence_gap`
- `source_revision_gap`
- `package_artifact_gap`
- `install_run_evidence_gap`
- `configuration_evidence_gap`
- `persistence_evidence_gap`
- `diagnostic_evidence_gap`
- `player_safe_error_evidence_gap`
- `endurance_evidence_gap`
- `platform_environment_gap`
- `known_blocker_gap`
- `redaction_review_gap`
- `operator_signoff_gap`
- `release_intake_ready`

## Classification rules

Use `release_intake_evidence_gap` when no concrete operator release evidence summary is attached.

Use `source_revision_gap` when the evidence is not tied to an exact git SHA and branch.

Use `package_artifact_gap` when package artifacts or checksums are missing.

Use `install_run_evidence_gap`, `configuration_evidence_gap`, `persistence_evidence_gap`, `diagnostic_evidence_gap`, `player_safe_error_evidence_gap`, or `endurance_evidence_gap` when the corresponding evidence is missing, failing, or not reproducible from the intake summary.

Use `platform_environment_gap` when OS, shell, hardware, or environment details are missing.

Use `known_blocker_gap` when blockers or release exclusions are missing or ambiguous.

Use `redaction_review_gap` when the intake does not confirm that secrets, tokens, provider keys, personal data, and sensitive local paths were redacted from shareable artifacts.

Use `operator_signoff_gap` when operator name or role and signoff timestamp are missing.

Use `release_intake_ready` only when concrete evidence covers source revision, package artifacts, install/run, configuration, persistence, diagnostics, player-safe errors, endurance, platform environment, blockers, redaction, and operator signoff without blocking gaps.

## No-evidence decision for this slice

Because this Phase 10.6 slice does not attach a concrete operator release evidence summary, package artifact, install/run transcript, persistence artifact, diagnostic bundle, player-safe error artifact, endurance summary, redaction review, or signoff, the current classification is:

- classification: `release_intake_evidence_gap`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, packaging claims, and external release-readiness claims

## Deterministic boundary

Phase 10.6 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- external release claims without evidence.

Simulation/runtime remains authoritative. Release intake labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 10.6 is complete when the repository has CI-gated documentation/tests proving that operator release intake requires concrete evidence, absent evidence maps to `release_intake_evidence_gap`, and this slice does not claim release readiness.

## Recommended next slice

After Phase 10.6, continue with:

- Phase 10.7 — production readiness closeout decision gate.
