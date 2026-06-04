# RPG Phase 9.8 Completion Note

Phase 9.8 long-run continuity evidence envelope is complete.

## Implementation

Implementation PR: #310

Implementation head SHA checked:

- `95bffcf9e827f9deec73bc3f8723fef08bc9280f`

Implementation merge SHA:

- `7b4c1a944ecd1e522681c155efe0df0acc689e1f`

Required checks observed passing on the exact implementation head SHA:

- RPG Phase 0 architecture compliance
- RPG deterministic PR gates

## Files added or updated

- `docs/plans/rpg_phase9_8_long_run_continuity_evidence_envelope.md`
- `src/tests/rpg/test_ci_phase9_8_long_run_continuity_evidence_envelope.py`
- `docs/plans/rpg_production_readiness_plan.md`
- `.github/workflows/rpg-phase0-architecture-compliance.yml`

## What Phase 9.8 added

Phase 9.8 added a deterministic, provider-free evidence envelope for long-run continuity review without requiring a live/provider 100-turn or 1000-turn campaign in CI.

The envelope records required continuity evidence categories for:

- combat continuity;
- NPC memory continuity;
- party continuity;
- travel continuity;
- time continuity;
- weather continuity;
- quest continuity;
- reward continuity;
- economy and inventory continuity;
- save/load continuity;
- replay continuity;
- progress-quality continuity;
- provider-boundary continuity;
- runtime-authority continuity;
- taxonomy classification.

It also records drift classification rules mapping continuity drift to `world_continuity_failure`, checkpoint or replay mismatch to `save_load_checkpoint_failure`, malformed artifact references to `artifact_contract_failure`, no-op or false-progress loops to `progress_quality_failure`, and unsupported provider-facing state claims to `provider_boundary_failure` or `runtime_authority_failure`.

Missing transcript evidence, reviewed turn range, save/load checkpoint or replay evidence, continuity category review notes, or artifact bundle references must classify as `operator_evidence_gap`.

## Boundary

Phase 9.8 did not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, or new command execution paths.

Simulation/runtime remains authoritative. Continuity evidence summaries, labels, and transcript reviews are evidence surfaces only and must not decide gameplay truth.

## Remaining risks

- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for live/provider endurance, wall-clock timing, blocking or human-equivalent turn timing, final drain timing, background job drain behavior, production resource limits, and long-run narrative quality review.
- Full package/disk replay evidence remains pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.
- Future targeted hardening must still be selected from concrete evidence.

## Recommended next slice

Phase 9.9 — targeted endurance hardening from concrete evidence.
