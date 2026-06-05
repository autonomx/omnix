# RPG Phase 11.8 Checkpoint and Replay Evidence Runbook

Phase 11.8 defines the operator runbook for first checkpoint/replay evidence capture.

Latest source-of-truth SHA before this Phase 11.8 slice:

- `641e3aac839413ba3fc54f44055acb3871483d25`

## Scope

This slice is source/test/documentation only. It does not run a live/provider campaign in CI, change runtime behavior, mutate gameplay state, build a package in CI, or claim external release readiness.

Phase 11.8 converts the Phase 11.2 evidence backfill plan into the checkpoint/replay operator runbook: checkpoint artifact capture, save/load roundtrip references, replay verification, package/disk replay references, determinism notes, failure classification, hardening handoff, redaction review, and evidence bundle classification.

## Required operator runbook sections

The first checkpoint/replay evidence capture should include:

1. `operator_context`
2. `source_checkout`
3. `checkpoint_capture_context`
4. `checkpoint_artifact_manifest`
5. `save_load_roundtrip_reference`
6. `replay_command`
7. `replay_result`
8. `package_disk_replay_reference`
9. `determinism_notes`
10. `artifact_integrity_notes`
11. `failure_classification`
12. `hardening_handoff`
13. `redaction_review`
14. `operator_notes`
15. `checkpoint_replay_classification`

## Required artifact paths

The runbook should ask the operator to attach or record paths for:

- checkpoint artifact directory;
- checkpoint artifact manifest;
- save/load roundtrip transcript or reference;
- replay command transcript;
- replay result artifact;
- package/disk replay reference;
- determinism notes;
- artifact integrity notes;
- failure classification note;
- hardening handoff note;
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
- checkpoint source run and turn range;
- checkpoint interval if captured;
- checkpoint artifact paths;
- replay command and arguments;
- replay exit status;
- replay comparison result;
- determinism status;
- package/disk replay reference if captured;
- whether secrets, tokens, provider keys, personal data, and sensitive local paths were redacted.

## Classifications

Use one or more of these classifications:

- `checkpoint_replay_capture_not_started`
- `checkpoint_context_gap`
- `checkpoint_artifact_manifest_gap`
- `save_load_roundtrip_reference_gap`
- `replay_command_gap`
- `replay_result_gap`
- `package_disk_replay_reference_gap`
- `determinism_notes_gap`
- `artifact_integrity_gap`
- `failure_classification_gap`
- `hardening_handoff_gap`
- `redaction_review_gap`
- `checkpoint_replay_ready_for_triage`

## Classification rules

Use `checkpoint_replay_capture_not_started` when no checkpoint/replay evidence bundle is attached.

Use `checkpoint_context_gap` when the checkpoint source run, turn range, or interval is missing or ambiguous.

Use `checkpoint_artifact_manifest_gap` when checkpoint artifact paths or manifest entries are missing, malformed, or not tied to the exact source checkout.

Use `save_load_roundtrip_reference_gap` when save/load roundtrip evidence is missing or not linked to concrete artifacts.

Use `replay_command_gap` or `replay_result_gap` when the replay command, arguments, exit status, comparison result, or replay artifact is missing or not reproducible.

Use `package_disk_replay_reference_gap` when package/disk replay evidence is missing or not tied to a package artifact.

Use `determinism_notes_gap` or `artifact_integrity_gap` when determinism status or artifact integrity notes are missing or ambiguous.

Use `failure_classification_gap` when replay/checkpoint failures are not mapped to the Phase 9/10/11 taxonomy.

Use `hardening_handoff_gap` when concrete failures exist but are not translated into a bounded next hardening target.

Use `redaction_review_gap` when the evidence bundle does not confirm secrets and sensitive local details were redacted.

Use `checkpoint_replay_ready_for_triage` only when checkpoint/replay evidence is complete enough to classify a concrete hardening target without speculation.

## No-evidence decision for this slice

Because this Phase 11.8 slice does not attach a concrete checkpoint/replay evidence bundle, the current classification is:

- classification: `checkpoint_replay_capture_not_started`
- secondary classification: `operator_evidence_backfill_required`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Deterministic boundary

Phase 11.8 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- package building in CI;
- external release claims without evidence.

Simulation/runtime remains authoritative. Checkpoint/replay evidence labels are evidence surfaces only and must not decide gameplay truth.

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

# Capture checkpoint artifact manifest
<checkpoint artifact discovery command> 2>&1 | tee operator-checkpoint-artifacts.txt

# Run replay verification
<replay verification command> 2>&1 | tee operator-replay-verification.txt

# Capture package/disk replay reference
<package disk replay command or manual notes> 2>&1 | tee operator-package-disk-replay.txt

# Capture review notes
<review steps> 2>&1 | tee operator-checkpoint-replay-review.txt
```

## Stop condition

Phase 11.8 is complete when the repository has CI-gated documentation/tests proving that first checkpoint/replay evidence capture has a runbook, missing evidence maps to explicit gaps, and hardening remains blocked until evidence identifies a narrow target.

## Recommended next slice

After Phase 11.8, continue with:

- Phase 11.9 — first hardening target selection from attached evidence.
