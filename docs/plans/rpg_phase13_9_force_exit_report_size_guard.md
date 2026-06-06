# RPG Phase 13.9 Force-Exit Report Size Guard

Phase 13.9 addresses the follow-up evidence from the 100-turn travel/location progression run after Phase 13.8.

Latest source-of-truth SHA before this Phase 13.9 slice:

- `71ace2fffe1ba593462516c30fe36859f5ac2c59`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(1).zip`
- screenshot showing `autoplay-campaign-report.json` at roughly 971,014 KB

The uploaded rerun evidence still contains an oversized report and does not include `autoplay-report-size-guard-summary.json`. It also lacks the earlier post-run summary artifacts, which indicates the command path can finish through the forced-exit path before optional post-run enrichment runs.

## Bounded target

Phase 13.9 selects this bounded target:

- install a report-size guard before the autoplay runtime starts, so the guard also runs when the harness uses the force-exit path.

## Implementation

This slice adds:

- `src/tests/rpg/autoplay/report_size_guard_hook.py`
- `src/tests/rpg/test_ci_phase13_9_report_size_guard_finalizer.py`
- `docs/plans/rpg_phase13_9_force_exit_report_size_guard.md`
- `docs/plans/rpg_phase13_9_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Behavior

The stable autoplay loader now installs a guard before calling the generated campaign runtime. The guard parses `--output-dir`, finds the latest results ZIP in that directory, and applies the Phase 13.8 report-size cap to both filesystem report artifacts and report members inside the ZIP.

This ensures the size guard is available before forced finalization can bypass the normal post-run hook.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- `--output-dir` is parsed from both supported argument forms;
- explicit output directories are capped correctly;
- oversized report ZIP members are replaced while unrelated members are preserved;
- missing output directories are reported without crashing;
- runtime, gameplay, provider, narration, and artifact semantics remain otherwise unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Report-size labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.9, continue with:

- Phase 13.10 — rerun 100-turn evidence review after force-exit report-size guard.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and verify that `autoplay-report-size-guard-summary.json` is present and the report artifacts are capped.
