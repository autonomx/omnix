# RPG Phase 13.7 Validated Performance Path Gate

Phase 13.7 is the broaden validated performance path or continue operator evidence backfill slice.

Latest source-of-truth SHA before this Phase 13.7 slice:

- `17d7acb7fa7def1a8e57ecb85133ceb9e6c8f1a1`

## Current evidence state

No new latency-reduced interactive matrix evidence is attached in this slice.

Because no new live matrix evidence is attached, Phase 13.7 must continue evidence backfill and must not broaden the Phase 13.4 opt-in performance path.

## Validated broadening requirements

A validated performance path may be broadened only when attached evidence includes:

1. latency-reduced matrix ZIP;
2. source checkout SHA;
3. command used;
4. provider/model configuration summary;
5. matrix performance payload;
6. latency-reduction evidence review payload;
7. proof that the Phase 13.4 runner was enabled;
8. provider-backed average latency improvement of at least 15% from the 5.42 second baseline;
9. deterministic fast-path average at or below 1.0 second;
10. p95 turn time not regressed above the 6.36 second baseline;
11. max turn time not regressed above the 7.45 second baseline;
12. scenario pass/fail summary;
13. boundary review confirming runtime authority and deferred narration boundaries remain intact;
14. explicit promotion scope;
15. explicit non-targets;
16. required verification checks;
17. redaction review.

## Decision classifications

Use one or more of these classifications:

- `phase13_7_no_latency_reduced_evidence`
- `operator_evidence_backfill_required`
- `validated_performance_path_not_ready`
- `validated_performance_path_ready`
- `performance_path_broadening_allowed`
- `performance_path_broadening_blocked`

## Decision rules

Use `phase13_7_no_latency_reduced_evidence` when no latency-reduced matrix evidence is attached.

Use `operator_evidence_backfill_required` when the next action remains running or attaching the latency-reduced matrix bundle.

Use `validated_performance_path_not_ready` when evidence is missing, incomplete, not redacted, not source-backed, fails improvement thresholds, regresses deterministic fast paths, or does not preserve runtime/deferred narration boundaries.

Use `validated_performance_path_ready` only when all validated broadening requirements are complete.

Use `performance_path_broadening_allowed` only when `validated_performance_path_ready` is present and the proposed promotion scope is bounded.

Use `performance_path_broadening_blocked` when broadening would be speculative or lacks accepted evidence.

## No-evidence decision for this slice

Because this Phase 13.7 slice does not attach new latency-reduced matrix evidence, the current decision state is:

- classification: `phase13_7_no_latency_reduced_evidence`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `performance_path_broadening_blocked`
- selected broadening target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: default runner changes, runtime behavior changes, provider behavior changes, first-call routing changes, gameplay mutation, UI authority changes, package building in CI, live provider execution in CI, speculative latency changes, and production readiness claims

## Operator command

Run the opt-in latency-reduced matrix before attempting to broaden the performance path:

```bash
python src/tests/rpg/interactive_intent_matrix_latency_reduction.py --live-provider
```

Then attach the resulting evidence bundle for review.

## Boundary confirmation

This slice does not add runtime behavior changes, provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Phase 13.7 decision labels are advisory evidence surfaces only and do not decide gameplay truth.

## Recommended next slice

Continue with:

- Phase 13.8 — production readiness evidence checkpoint or validated performance promotion.

If no latency-reduced matrix evidence is attached, Phase 13.8 should continue operator evidence backfill rather than implementing speculative changes.
