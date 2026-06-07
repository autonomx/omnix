# RPG Phase 13.13 Output Directory Hook and Copy Guard

Phase 13.13 addresses the latest 100-turn rerun after Phase 13.12.

Latest source-of-truth SHA before this Phase 13.13 slice:

- `88ae8b7db5736260e5f7e88c9c4e224733124f7b`

## Accepted evidence

Accepted evidence source:

- pasted operator output from the latest 100-turn run

The evidence confirms the run was on latest Phase 13.12 code. It also shows:

- `autoplay-report-size-guard-summary.json` exists;
- `autoplay-performance-summary.json` is missing from the per-run output directory;
- `RecursionError: maximum recursion depth exceeded` still appears from turn 59 through turn 100.

## Bounded targets

Phase 13.13 selects two bounded targets:

1. Pass the explicit `--output-dir` into the post-run report hook so performance artifacts are written into the per-run directory.
2. Install an autoplay-only guarded copy helper before generated runtime fragments import `deepcopy`, so recursive/cyclic diagnostic structures are bounded instead of crashing turn handling.

## Implementation

This slice adds:

- `src/tests/rpg/autoplay/deepcopy_recursion_guard.py`
- `src/tests/rpg/test_ci_phase13_13_output_dir_guard.py`
- `docs/plans/rpg_phase13_13_output_dir_and_copy_guard.md`
- `docs/plans/rpg_phase13_13_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Behavior

The stable autoplay loader now:

- parses `--output-dir` directly;
- passes that directory to `run_autoplay_survival_report_writer_hook`;
- installs the guarded copy helper before loading generated fragments.

The guarded copy helper preserves normal behavior unless the normal copy raises `RecursionError`. When that happens, it writes `autoplay-deepcopy-recursion-guard-summary.json` and returns a bounded structural clone that breaks cycles and truncates extreme depth/width.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- both `--output-dir value` and `--output-dir=value` are parsed correctly;
- the guarded copy helper writes a summary when the normal copy raises `RecursionError`;
- self-referential structures are converted into bounded markers;
- the loader patches copy behavior before generated runtime fragments load;
- runtime authority and gameplay semantics remain unchanged for normal non-recursive values.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Copy-guard labels and timing artifacts are advisory surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.13, continue with:

- Phase 13.14 — rerun 100-turn evidence review after output-dir hook and copy guard.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and verify that `autoplay-performance-summary.json` exists in the per-run directory and that the console log no longer contains `RecursionError` lines.
