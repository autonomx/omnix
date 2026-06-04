# RPG Phase 9.1 Endurance Harness Baseline and Failure Taxonomy

Phase 9 begins the 1000-turn endurance systems track.

Latest source-of-truth SHA before this Phase 9.1 slice:

- `e3105851e4559ae230747aadd2a29af0a1f4a4a4`

## Baseline harness entry point

The current source-backed endurance harness entry point is:

- `src/tests/rpg/autoplay_llm_campaign.py`

The loader preserves the historical script entry point:

- `python src/tests/rpg/autoplay_llm_campaign.py`

The import-time compatibility runner remains:

- `run_autoplay_campaign(args)`

The compatibility runner currently writes:

- `autoplay-summary.json`
- `autoplay-transcript.json`
- `autoplay-campaign-results.zip`

## Endurance target

Phase 9 target:

- 1000-turn endurance run readiness.

Phase 9.1 does not require live/provider execution in CI. It establishes the deterministic baseline and taxonomy used to classify future endurance evidence.

## Failure taxonomy

Endurance failures should be classified into these deterministic categories:

1. `harness_entrypoint_failure`
   - The harness cannot load, cannot find fragments, or cannot expose `main` / `run_autoplay_campaign`.
2. `runtime_authority_failure`
   - Runtime wrapper authority drifts away from `app.rpg.session.runtime_part27` or `app.rpg.session.runtime_part23`.
3. `turn_execution_failure`
   - A turn crashes, returns malformed state, or cannot advance through the canonical runtime path.
4. `save_load_checkpoint_failure`
   - Checkpoint validation fails, saved state cannot reload, or replay baseline state diverges.
5. `artifact_contract_failure`
   - Summary, transcript, or ZIP artifacts are missing, malformed, or incomplete.
6. `progress_quality_failure`
   - Objective/progress checks flag false progress, weak progress, or repeated no-op loops beyond accepted thresholds.
7. `performance_budget_failure`
   - Blocking/human-equivalent turn time or final drain behavior exceeds the current budget.
8. `provider_boundary_failure`
   - Provider/LLM behavior is required for deterministic runtime truth or CI-only endurance gates.
9. `world_continuity_failure`
   - Long-run continuity breaks across combat, NPC memory, party, travel, time, weather, or quest/reward state.
10. `operator_evidence_gap`
    - A result depends on live/manual execution evidence not captured in repo-side artifacts.

## CI-gated versus operator evidence

CI-gated Phase 9 evidence should cover:

- harness entrypoint source contract;
- compatibility runner artifact contract;
- runtime wrapper manifest authority;
- deterministic taxonomy documentation;
- provider-boundary guardrails.

Operator/manual evidence may cover:

- live/provider 100-turn or 1000-turn campaigns;
- wall-clock performance and final drain timings;
- long-run narrative quality review;
- package/disk replay evidence;
- production environment resource limits.

## Phase 9.1 stop condition

Phase 9.1 is complete when the repo records:

- the current endurance harness entry point;
- the failure taxonomy;
- CI-gated versus operator/manual evidence boundaries;
- runtime authority/provider boundary preservation;
- source guards that prevent losing the baseline contract.

## Recommended next slice

After Phase 9.1, continue with:

- Phase 9.2 — deterministic endurance artifact contract guard.
