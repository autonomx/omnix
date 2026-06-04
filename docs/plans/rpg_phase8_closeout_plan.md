# RPG Phase 8 Closeout Plan

Phase 8 has reached closeout planning after Phase 8.30.

Latest completed Phase 8 slice before this plan:

- Phase 8.30 — panel chrome surface metadata.
- Latest source-of-truth SHA before this plan: `66e586addec817ab74fd65f8f2873776a03447f2`.

## Closeout decision

Phase 8 should no longer accept open-ended metadata-only polish slices.

Remaining Phase 8 work is capped at four final slices. After those slices, move to Phase 9 unless a required gate exposes a concrete blocker.

## Final Phase 8 checklist

1. Phase 8.32 — Panel contract inventory and consolidation
   - Produce a compact source-backed inventory of registered panels, shared chrome helpers, and deterministic metadata families.
   - Confirm no duplicate metadata family should continue as a standalone Phase 8 slice.
   - Keep this documentation/source-guard only unless a concrete broken hook is found.

2. Phase 8.33 — Browser smoke coverage for registered panels
   - Add or consolidate provider-free smoke coverage that each registered panel can render with shared chrome and escaped payloads.
   - Do not add gameplay commands, runtime mutation, or provider/LLM calls.

3. Phase 8.34 — UI runtime-authority boundary audit
   - Add a source-backed audit that panel UI hints remain advisory/read-only and command submission still routes through existing runtime validation paths only.
   - Preserve wrapper authority for turn and combat action runtime modules.

4. Phase 8.35 — Phase 8 final closeout note and Phase 9 handoff
   - Mark Phase 8 complete for provider-free PR-gated UI/UX foundations.
   - Summarize remaining product risks honestly.
   - Hand off to Phase 9 — 1000-turn endurance systems.

## Explicit stop conditions

- Do not add more Phase 8 metadata-only families after Phase 8.31.
- Do not expand Phase 8 beyond the four final checklist items above without a concrete failing gate or explicit user instruction.
- Do not claim full visual/gameplay UI completion; Phase 8 is a provider-free foundation pass.
- Do not add provider/LLM calls, gameplay mutation, or new command execution paths in Phase 8 closeout slices.

## Phase 9 entry criteria

Phase 9 can begin once the final closeout note records:

- shared panel/chrome coverage is inventoried;
- registered panels have provider-free smoke coverage;
- UI runtime-authority boundaries are audited;
- remaining UI/product risks are routed forward without blocking endurance work.
