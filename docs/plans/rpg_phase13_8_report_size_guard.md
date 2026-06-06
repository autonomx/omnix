# RPG Phase 13.8 Autoplay Report Size Guard

Phase 13.8 addresses the production-readiness evidence from the 100-turn travel/location progression run.

Latest source-of-truth SHA before this Phase 13.8 slice:

- `b0b3f0c9d3557babc0406e084e955dc1d4e25886`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression.zip`

The operator reported that `autoplay-campaign-report.json` reached about 970 MB locally. The uploaded ZIP confirms the same class of issue: report JSON/HTML artifacts can become far too large for normal operator review and sharing.

## Bounded target

Phase 13.8 selects this bounded target:

- cap oversized autoplay report JSON/HTML artifacts after the run completes, and replace oversized ZIP members with compact manifests.

This is artifact-size hardening only. It does not change gameplay, runtime state, provider behavior, or narration behavior.

## Implementation

This slice adds:

- `src/app/rpg/autoplay_report_size_guard.py`
- `src/tests/rpg/test_ci_phase13_8_autoplay_report_size_guard.py`
- `docs/plans/rpg_phase13_8_report_size_guard.md`
- `docs/plans/rpg_phase13_8_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay/survival_report_writer_hook.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Behavior

After the campaign finishes, the post-run hook now:

- scans the output directory for oversized `autoplay-campaign-report.json` and report HTML files;
- replaces oversized report files with compact capped manifests;
- rewrites oversized report members inside the latest results ZIP;
- writes `autoplay-report-size-guard-summary.json`;
- leaves transcript and review artifacts available for detailed analysis.

## Defaults

Default limits:

- report JSON: 25 MiB
- report HTML: 15 MiB

Environment overrides:

- `RPG_AUTOPLAY_MAX_REPORT_JSON_BYTES`
- `RPG_AUTOPLAY_MAX_REPORT_HTML_BYTES`

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- oversized report JSON files are replaced with compact manifests;
- oversized report ZIP members are replaced while unrelated ZIP members are preserved;
- a size-guard summary is written;
- the post-run hook returns the size-guard result;
- runtime and gameplay behavior are unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Report-size labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.8, continue with:

- Phase 13.9 — operator evidence package or first validated promotion.

The immediate operator follow-up is to rerun the 100-turn command and confirm that the generated report artifacts remain within manageable size limits.
