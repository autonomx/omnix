# RPG Phase 13.4 Provider-Backed Intent Latency Reduction

Phase 13.4 implements a bounded latency-reduction path from the accepted interactive matrix performance evidence.

Latest source-of-truth SHA before this Phase 13.4 slice:

- `426c9a9ca762df7e64cf5d57f2caab6124fa1711`

## Accepted evidence

Accepted evidence source:

- `interactive-intent-matrix(36).zip`
- Phase 13.3 structured matrix performance review

The evidence showed deterministic fast paths around 0.10 seconds per turn, while provider-backed paths averaged about 5.42 seconds per turn and runtime-apply time dominated measured latency.

## Bounded target

Phase 13.4 selects this bounded target:

- reduce interactive matrix latency for accepted provider-backed intent paths by avoiding the first-call advisory provider round trip for known-safe, bounded matrix categories.

The target categories are:

- `rumor_news_no_backed_state`
- `commerce_food_purchase`
- `party_companion_recruitment`
- `quest_no_backed_state`
- `npc_dialogue_persona`

## Implementation

This slice adds:

- `src/app/rpg/session/provider_backed_intent_fast_path.py`
- `src/tests/rpg/interactive_intent_matrix_latency_reduction.py`
- `src/tests/rpg/test_ci_phase13_4_provider_backed_intent_fast_path.py`

The latency-reduced matrix runner patches first-call advisory functions only for the duration of the run. For accepted bounded inputs, it supplies a deterministic grounded advisory. Canonical runtime still resolves state, and deferred narration/runtime authority boundaries remain unchanged.

## Operator command

Use this runner for the next matrix smoke:

```bash
python src/tests/rpg/interactive_intent_matrix_latency_reduction.py --live-provider
```

Optional scenario subset:

```bash
python src/tests/rpg/interactive_intent_matrix_latency_reduction.py --live-provider --scenario rumor_news_no_backed_state --scenario commerce_food_purchase
```

## Acceptance criteria

The implementation is accepted when:

- deterministic tests prove the fast path is opt-in;
- accepted slow matrix categories produce grounded fast advisories;
- unbounded inputs do not match the fast path;
- the patch restores original first-call advisory functions after use;
- canonical runtime remains authoritative;
- provider calls are avoided only for accepted bounded matrix inputs;
- normal app/runtime behavior is unchanged unless the opt-in matrix runner is used.

## Deterministic boundary

This slice does not add new provider calls, LLM calls, network calls, live 100-turn or 1000-turn CI execution, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. The fast path supplies advisory intent only; runtime decides state and deferred narration cannot mutate state.

## Remaining risks

- The next live matrix run must confirm actual latency reduction.
- This implementation is opt-in for the latency-reduced matrix runner; the default matrix runner remains unchanged.
- Live/provider 1000-turn execution remains pending.
- Production readiness is not claimable.

## Recommended next slice

After Phase 13.4, continue with:

- Phase 13.5 — production readiness evidence review after latency reduction.
