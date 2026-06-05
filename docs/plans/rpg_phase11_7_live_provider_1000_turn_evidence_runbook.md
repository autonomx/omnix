# RPG Phase 11.7 Live Provider 1000-Turn Evidence Runbook

Phase 11.7 defines the operator runbook for first live/provider 1000-turn evidence capture.

Latest source-of-truth SHA before this Phase 11.7 slice:

- `6424b60897ac0a90520e090f23a6868ff1932a73`

## Scope

This slice is source/test/documentation only. It does not run a live/provider campaign in CI, change runtime behavior, mutate gameplay state, build a package in CI, or claim external release readiness.

Phase 11.7 converts the Phase 11.2 evidence backfill plan into the first live/provider 1000-turn operator runbook: provider/model/config capture, command capture, artifact capture, timing capture, final drain behavior, background job behavior, checkpoint/replay evidence, progress-quality review, continuity review, redaction review, and hardening handoff classification.

## Required operator runbook sections

The first live/provider 1000-turn evidence capture should include:

1. `operator_context`
2. `source_checkout`
3. `provider_configuration`
4. `model_configuration`
5. `run_command`
6. `runtime_configuration_snapshot`
7. `artifact_bundle_manifest`
8. `autoplay_summary_capture`
9. `autoplay_transcript_capture`
10. `autoplay_zip_capture`
11. `checkpoint_artifact_capture`
12. `replay_artifact_capture`
13. `timing_metrics_capture`
14. `final_drain_capture`
15. `background_job_capture`
16. `progress_quality_review`
17. `continuity_review`
18. `failure_classification`
19. `hardening_handoff`
20. `redaction_review`
21. `operator_notes`
22. `live_provider_1000_turn_classification`

## Required artifact paths

The runbook should ask the operator to attach or record paths for:

- operator command transcript;
- provider/model/config snapshot;
- `autoplay-summary.json`;
- `autoplay-transcript.json`;
- `autoplay-campaign-results.zip`;
- checkpoint artifact paths;
- replay artifact paths;
- timing metrics summary;
- final drain notes;
- background job notes;
- progress-quality review note;
- continuity review note;
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
- provider name;
- model name;
- provider endpoint or local service description with secrets redacted;
- runtime configuration relevant to the campaign;
- exact run command;
- requested turn count;
- turns executed;
- run exit status;
- wall-clock time;
- blocking or human-equivalent turn timing if captured;
- final drain duration and result;
- background job count and drain behavior;
- checkpoint interval and artifact paths if captured;
- replay verification result if captured;
- whether secrets, tokens, provider keys, personal data, and sensitive local paths were redacted.

## Classifications

Use one or more of these classifications:

- `live_provider_1000_turn_not_started`
- `provider_configuration_gap`
- `model_configuration_gap`
- `run_command_gap`
- `runtime_configuration_gap`
- `artifact_bundle_gap`
- `autoplay_summary_gap`
- `autoplay_transcript_gap`
- `autoplay_zip_gap`
- `checkpoint_artifact_gap`
- `replay_artifact_gap`
- `timing_metrics_gap`
- `final_drain_gap`
- `background_job_gap`
- `progress_quality_review_gap`
- `continuity_review_gap`
- `failure_classification_gap`
- `hardening_handoff_gap`
- `redaction_review_gap`
- `live_provider_1000_turn_ready_for_triage`

## Classification rules

Use `live_provider_1000_turn_not_started` when no live/provider 1000-turn evidence bundle is attached.

Use `provider_configuration_gap`, `model_configuration_gap`, `run_command_gap`, or `runtime_configuration_gap` when the provider/model/command/runtime context is missing, ambiguous, or not reproducible.

Use `artifact_bundle_gap`, `autoplay_summary_gap`, `autoplay_transcript_gap`, or `autoplay_zip_gap` when required campaign artifacts are missing, malformed, or not referenced from the evidence.

Use `checkpoint_artifact_gap` or `replay_artifact_gap` when checkpoint/replay evidence is missing, malformed, or not tied to exact artifacts.

Use `timing_metrics_gap`, `final_drain_gap`, or `background_job_gap` when timing, final drain, or background job behavior is missing, failing, or not reviewable.

Use `progress_quality_review_gap` or `continuity_review_gap` when transcript review is missing or not tied to concrete transcript artifacts.

Use `failure_classification_gap` when failures are not mapped to the Phase 9/10/11 taxonomy.

Use `hardening_handoff_gap` when concrete failures exist but are not translated into a bounded next hardening target.

Use `redaction_review_gap` when the evidence bundle does not confirm secrets and sensitive local details were redacted.

Use `live_provider_1000_turn_ready_for_triage` only when live/provider 1000-turn evidence is complete enough to classify a concrete hardening target without speculation.

## No-evidence decision for this slice

Because this Phase 11.7 slice does not attach a concrete live/provider 1000-turn evidence bundle, the current classification is:

- classification: `live_provider_1000_turn_not_started`
- secondary classification: `operator_evidence_backfill_required`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Deterministic boundary

Phase 11.7 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- speculative hardening without concrete evidence;
- package building in CI;
- external release claims without evidence.

Simulation/runtime remains authoritative. Live/provider 1000-turn evidence labels are evidence surfaces only and must not decide gameplay truth.

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

# Capture provider/model/runtime configuration with secrets redacted
<configuration capture command or manual notes> 2>&1 | tee operator-live-1000-config.txt

# Run the live/provider 1000-turn campaign
<live provider 1000-turn command> 2>&1 | tee operator-live-1000-run-transcript.txt

# Capture artifact manifest
<artifact discovery command> 2>&1 | tee operator-live-1000-artifacts.txt

# Capture checkpoint/replay evidence
<checkpoint replay verification command or manual notes> 2>&1 | tee operator-live-1000-checkpoint-replay.txt

# Capture review notes
<review steps> 2>&1 | tee operator-live-1000-review.txt
```

## Stop condition

Phase 11.7 is complete when the repository has CI-gated documentation/tests proving that first live/provider 1000-turn evidence capture has a runbook, missing evidence maps to explicit gaps, and hardening remains blocked until evidence identifies a narrow target.

## Recommended next slice

After Phase 11.7, continue with:

- Phase 11.8 — first checkpoint/replay evidence capture runbook.
