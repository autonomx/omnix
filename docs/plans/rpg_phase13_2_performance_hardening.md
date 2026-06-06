# RPG Phase 13.2 Performance Hardening

Phase 13.2 implements the first accepted hardening target from attached operator evidence.

Latest source-of-truth SHA before this Phase 13.2 slice:

- `2f15aba2e4ceefcb29aca0a1e13e8d49842d6c27`

## Accepted evidence

The accepted evidence is the uploaded 5-turn smoke bundle:

- `autoplay-2-n113-smoke.zip`

The smoke evidence showed a completed 5-turn run but highlighted slow per-turn performance:

- average wall time was approximately 18 seconds per turn;
- player-agent action selection took roughly 4 to 6 seconds per turn;
- runtime turn execution took roughly 11 to 13 seconds per turn;
- final drain added several seconds after the turn loop;
- performance triage required manual log inspection.

## Bounded target

Phase 13.2 selects this bounded hardening target:

- emit structured autoplay performance summary artifacts for each operator smoke so slow runs can be triaged from JSON/HTML and ZIP members without manually parsing console logs.

This is the first implementation target because it is low-risk, evidence-backed, and creates the measurement surface needed before larger latency-reduction changes.

## Implementation

This slice adds:

- `src/app/rpg/autoplay_performance_artifacts.py`
- `src/tests/rpg/autoplay/performance_artifacts.py`
- `src/tests/rpg/test_ci_phase13_2_autoplay_performance_artifacts.py`
- post-run hook integration in `src/tests/rpg/autoplay/survival_report_writer_hook.py`

## Acceptance criteria

The implementation is accepted when:

- deterministic tests prove slow 5-turn smoke-shaped rows produce warning classifications;
- JSON and HTML performance artifacts are written beside normal autoplay outputs;
- performance JSON and HTML are appended to the autoplay ZIP under `performance/`;
- the post-run hook attaches performance artifacts without failing the run;
- performance summaries remain advisory-only and do not decide simulation truth;
- runtime, provider, gameplay, UI authority, live provider calls, and package building are unchanged.

## Metrics emitted

The performance summary captures:

- observed turn count;
- average, minimum, and maximum wall seconds;
- average, minimum, and maximum blocking seconds when available;
- average, minimum, and maximum player-agent seconds when available;
- average, minimum, and maximum runtime seconds when available;
- average, minimum, and maximum background seconds when available;
- final drain seconds when available;
- warning classifications for target breaches.

## Deterministic boundary

This slice does not add provider calls, LLM calls, network calls, live 100-turn or 1000-turn CI execution, gameplay mutation, UI authority changes, package building in CI, or external release claims.

Simulation/runtime remains authoritative. Performance labels are advisory evidence surfaces only and must not decide gameplay truth.

## Remaining performance work

The next accepted performance hardening target can reduce latency after the artifact surface is available. Likely candidates are:

- compact player-agent action selection prompts;
- template-first autoplay decisions for obvious actions;
- reduced background prompt payloads;
- skip or defer background LLM work for short smoke runs;
- separate human-blocking latency from final-drain latency in all reports.

## Recommended next slice

After Phase 13.2, continue with:

- Phase 13.3 — production readiness evidence review after first hardening target.
