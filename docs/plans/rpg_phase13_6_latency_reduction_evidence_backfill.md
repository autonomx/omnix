# RPG Phase 13.6 Latency Reduction Evidence Backfill

Phase 13.6 is the latency-reduction follow-up from live matrix evidence slice.

Latest source-of-truth SHA before this Phase 13.6 slice:

- `e118f182d3fc2ad91b1f42a74035d3eec1564dcd`

## Current evidence state

No new latency-reduced interactive matrix ZIP is attached in this slice.

Because no new live matrix evidence is attached, Phase 13.6 remains evidence-review/backfill and must not implement another latency change.

## Required operator run

Run the Phase 13.4 latency-reduced matrix runner:

```bash
python src/tests/rpg/interactive_intent_matrix_latency_reduction.py --live-provider
```

Optional bounded subset before a full matrix:

```bash
python src/tests/rpg/interactive_intent_matrix_latency_reduction.py --live-provider --scenario rumor_news_no_backed_state --scenario commerce_food_purchase --scenario party_companion_recruitment --scenario quest_no_backed_state --scenario npc_dialogue_persona
```

## Required evidence bundle contents

Attach a redacted evidence bundle containing:

- the latency-reduced matrix ZIP;
- `interactive-intent-matrix-performance.json` or equivalent matrix performance payload;
- `interactive-intent-matrix-performance-review.json` if generated;
- `latency-reduction-evidence-review.json` if generated;
- console transcript or run log;
- source checkout SHA;
- provider/model configuration summary;
- command used;
- start/end timestamps;
- failure notes if any scenario failed;
- redaction review.

## Acceptance criteria for Phase 13.6 implementation

A follow-up implementation is allowed only when new attached evidence shows one of these states:

1. Confirmed improvement:
   - Phase 13.4 runner is marked enabled;
   - provider-backed average latency improves by at least 15% from the 5.42 second baseline;
   - deterministic fast-path average remains at or below 1.0 second;
   - p95 and max turn time do not regress against the Phase 13.3 baseline.
2. Confirmed no improvement:
   - Phase 13.4 runner is marked enabled;
   - provider-backed average latency improves by less than 15% or regresses;
   - evidence identifies exactly one bounded follow-up target.
3. Confirmed failure:
   - the latency-reduced runner fails to complete;
   - evidence includes reproduction steps, affected component, impact, non-targets, acceptance criteria, and required checks.

## No-evidence decision for this slice

Because this Phase 13.6 slice does not attach new latency-reduced matrix evidence, the current decision state is:

- classification: `phase13_6_latency_reduction_evidence_missing`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `phase13_6_implementation_blocked`
- selected follow-up target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior changes, provider behavior changes, first-call routing changes, gameplay mutation, UI authority changes, package building in CI, live provider execution in CI, speculative latency changes, and production readiness claims

## Boundary confirmation

This slice does not add runtime behavior changes, provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Phase 13.6 decision labels are advisory evidence surfaces only and do not decide gameplay truth.

## Recommended next slice

Continue with:

- Phase 13.7 — broaden validated performance path or continue operator evidence backfill.

If no latency-reduced matrix evidence is attached, Phase 13.7 should continue evidence backfill instead of implementing speculative changes.
