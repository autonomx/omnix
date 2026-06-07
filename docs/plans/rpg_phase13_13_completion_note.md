# RPG Phase 13.13 Completion Note

Phase 13.13 is complete as an output-directory hook and guarded-copy follow-up.

## Accepted evidence

Accepted evidence source:

- pasted operator output from the latest 100-turn run

The evidence confirmed the run was on Phase 13.12, report-size summary existed, performance summary was missing from the per-run directory, and turn errors still reported `RecursionError` from turn 59 through turn 100.

## What changed

Phase 13.13 added:

- `src/tests/rpg/autoplay/deepcopy_recursion_guard.py`
- `src/tests/rpg/test_ci_phase13_13_output_dir_guard.py`
- `docs/plans/rpg_phase13_13_output_dir_and_copy_guard.md`
- `docs/plans/rpg_phase13_13_completion_note.md`

Phase 13.13 updated:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Implementation summary

The loader now parses the explicit `--output-dir` and passes it into the post-run artifact hook, so performance artifacts are written to the per-run output directory.

The loader also installs an autoplay-only guarded copy helper before generated fragments load. Normal copy behavior is preserved unless the normal copy raises `RecursionError`; in that case the helper writes a summary and returns a bounded structural clone.

## Boundary confirmation

This slice did not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Copy-guard labels and timing artifacts remain advisory surfaces only and do not decide gameplay truth.

## Remaining risks

- The 100-turn command must be rerun to confirm `RecursionError` lines are gone.
- The per-run `autoplay-performance-summary.json` should now exist and should be reviewed.
- If recursion errors persist, the next slice should use the new guard summary or traceback evidence to identify the exact non-copy source.
- Live/provider 1000-turn execution remains pending.
- Production readiness is not claimable.

## Recommended next slice

Continue with:

- Phase 13.14 — rerun 100-turn evidence review after output-dir hook and guarded copy.
