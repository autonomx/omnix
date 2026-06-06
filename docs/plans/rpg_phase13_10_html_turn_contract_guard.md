# RPG Phase 13.10 HTML Turn Contract Marker Guard

Phase 13.10 addresses the rerun failure after the force-exit report-size guard.

Latest source-of-truth SHA before this Phase 13.10 slice:

- `1daa97a00393816f1b7053c3dc49ec064cb0330b`

## Accepted evidence

The operator reran the 100-turn command and the run reached final artifact generation, but failed on:

- `RuntimeError: campaign_report_html_contains_meta_text_in_transcript:markers=['turn contract']`

The same log also showed the late generated artifact write fallback for `essential-mirror-consistency-summary.json`, but the fatal failure was the HTML transcript metadata marker assertion.

## Bounded target

Phase 13.10 selects this bounded target:

- treat the exact `turn contract` HTML transcript marker as a metadata-only false positive, like the existing prompt marker guard, while still failing on unapproved markers such as system/developer leakage.

## Implementation

This slice updates:

- `src/app/rpg/session/autoplay_runtime_guards.py`

This slice adds:

- `src/tests/rpg/test_ci_phase13_10_html_meta_marker_guard.py`
- `docs/plans/rpg_phase13_10_html_turn_contract_guard.md`
- `docs/plans/rpg_phase13_10_completion_note.md`

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- `markers=['turn contract']` is suppressed as an exact metadata-only false positive;
- `markers=['prompt']` remains suppressed as before;
- unapproved markers such as `system` or `developer` still fail;
- the guard records a specific `turn_contract_html_transcript_marker_false_positive` reason;
- runtime, gameplay, provider, narration, and artifact semantics remain otherwise unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. The marker guard only affects report assertion behavior and does not decide gameplay truth.

## Recommended next slice

After Phase 13.10, continue with:

- Phase 13.11 — rerun 100-turn evidence review after HTML marker guard.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and verify that artifact generation completes without the `turn contract` marker failure.
